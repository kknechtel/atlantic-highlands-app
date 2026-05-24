"""Check-in routes for the Around Town (events.ahnj.info) app.

Endpoints:
  POST   /api/checkins                     create a check-in (auth)
  GET    /api/checkins                     list active check-ins (last 4h)
  GET    /api/checkins/venues              distinct venue names + last-seen
  GET    /api/checkins/by-venue/{name}     check-ins at a specific venue (active only)
  DELETE /api/checkins/{id}                remove your own check-in

"Active" = checked_in_at > NOW() - 4 hours. No background cleanup job —
the time filter does it. Stale rows linger in the table for analytics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.checkin import Checkin
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# How long a check-in counts as "currently here". Matches a typical
# evening out + a buffer for slow-finishing dinners.
ACTIVE_WINDOW = timedelta(hours=4)


# ── Schemas ──────────────────────────────────────────────────────────────

class CheckinCreate(BaseModel):
    venue_name: str = Field(min_length=1, max_length=120)
    city: Optional[str] = Field(default=None, max_length=60)
    message: Optional[str] = Field(default=None, max_length=200)


class CheckinOut(BaseModel):
    id: str
    user_id: str
    user_display_name: Optional[str]
    user_picture_url: Optional[str]
    venue_name: str
    city: Optional[str]
    message: Optional[str]
    checked_in_at: datetime


class VenueSummary(BaseModel):
    venue_name: str
    city: Optional[str]
    active_count: int
    last_checked_in_at: datetime


def _display_name_for(u: User) -> str:
    # Order of preference: display_name (set by Google or chosen) →
    # first part of full_name → first part of email. Username is internal
    # and not user-friendly enough.
    if u.display_name:
        return u.display_name
    if u.full_name:
        return u.full_name.split(" ", 1)[0]
    return (u.email or "").split("@", 1)[0] or "Someone"


def _to_out(c: Checkin, user: Optional[User]) -> CheckinOut:
    return CheckinOut(
        id=str(c.id),
        user_id=str(c.user_id),
        user_display_name=_display_name_for(user) if user else None,
        user_picture_url=getattr(user, "picture_url", None) if user else None,
        venue_name=c.venue_name,
        city=c.city,
        message=c.message,
        checked_in_at=c.checked_in_at,
    )


def _active_cutoff() -> datetime:
    return datetime.utcnow() - ACTIVE_WINDOW


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("/", response_model=CheckinOut, status_code=status.HTTP_201_CREATED)
def create_checkin(
    payload: CheckinCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Dedupe: a second check-in at the same venue within 30 min returns
    # the existing one rather than spamming the feed.
    recent_cutoff = datetime.utcnow() - timedelta(minutes=30)
    existing = (db.query(Checkin)
                  .filter(Checkin.user_id == user.id,
                          Checkin.venue_name == payload.venue_name.strip(),
                          Checkin.checked_in_at > recent_cutoff)
                  .order_by(desc(Checkin.checked_in_at))
                  .first())
    if existing:
        return _to_out(existing, user)

    c = Checkin(
        user_id=user.id,
        venue_name=payload.venue_name.strip(),
        city=(payload.city or "").strip() or None,
        message=(payload.message or "").strip() or None,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_out(c, user)


@router.get("/", response_model=list[CheckinOut])
def list_active_checkins(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """All active check-ins across all venues — feeds the Around Town
    "who's out tonight" pane on the home page."""
    cutoff = _active_cutoff()
    rows = (db.query(Checkin, User)
              .join(User, User.id == Checkin.user_id)
              .filter(Checkin.checked_in_at > cutoff)
              .order_by(desc(Checkin.checked_in_at))
              .limit(limit)
              .all())
    return [_to_out(c, u) for c, u in rows]


@router.get("/venues", response_model=list[VenueSummary])
def list_venues_with_checkins(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Distinct venues that have at least one ACTIVE check-in, with
    per-venue counts. Used by the /checkin page to surface "places
    people are right now"."""
    cutoff = _active_cutoff()
    rows = (db.query(
                Checkin.venue_name,
                Checkin.city,
                func.count(Checkin.id).label("n"),
                func.max(Checkin.checked_in_at).label("last_at"),
              )
              .filter(Checkin.checked_in_at > cutoff)
              .group_by(Checkin.venue_name, Checkin.city)
              .order_by(desc("n"))
              .all())
    return [VenueSummary(
        venue_name=r.venue_name,
        city=r.city,
        active_count=int(r.n),
        last_checked_in_at=r.last_at,
    ) for r in rows]


@router.get("/by-venue/{venue_name}", response_model=list[CheckinOut])
def list_checkins_at_venue(
    venue_name: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cutoff = _active_cutoff()
    rows = (db.query(Checkin, User)
              .join(User, User.id == Checkin.user_id)
              .filter(Checkin.venue_name == venue_name,
                      Checkin.checked_in_at > cutoff)
              .order_by(desc(Checkin.checked_in_at))
              .all())
    return [_to_out(c, u) for c, u in rows]


@router.delete("/{checkin_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_checkin(
    checkin_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = (db.query(Checkin)
           .filter(Checkin.id == checkin_id, Checkin.user_id == user.id)
           .first())
    if not c:
        raise HTTPException(404, "Check-in not found")
    db.delete(c)
    db.commit()
    return None
