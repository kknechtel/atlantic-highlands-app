"""Calendar events API - serves scraped borough events and document-derived dates."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from database import get_db
from models.event_rsvp import EventRsvp
from models.user import User
from auth import get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/events")
def get_calendar_events(
    year: int = Query(None),
    month: int = Query(None),
    event_type: str = Query(None, description="'general' (borough) or 'live_music'"),
    city: str = Query(None),
    venue: str = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Get calendar events from the scraped borough calendar + live-music
    venue scrapers. Filterable by year/month and by event_type/city/venue."""
    query = (
        "SELECT id, date, title, time, end_time, location, description, "
        "source, source_url, venue, city, event_type, ticket_url, created_at "
        "FROM calendar_events"
    )
    params = {}
    conditions = []

    if year:
        conditions.append("EXTRACT(YEAR FROM date) = :year")
        params["year"] = year
    if month:
        conditions.append("EXTRACT(MONTH FROM date) = :month")
        params["month"] = month
    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type
    if city:
        conditions.append("city = :city")
        params["city"] = city
    if venue:
        conditions.append("venue = :venue")
        params["venue"] = venue

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date ASC, time ASC NULLS LAST"

    try:
        rows = db.execute(sql_text(query), params).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Calendar events query failed (table may not exist): {e}")
        return []


def _row_to_dict(r) -> dict:
    return {
        "id": str(r.id),
        "date": r.date.isoformat(),
        "title": r.title,
        "time": r.time,
        "end_time": getattr(r, "end_time", None),
        "location": r.location,
        "description": r.description,
        "source": r.source,
        "source_url": r.source_url,
        "venue": getattr(r, "venue", None),
        "city": getattr(r, "city", None),
        "event_type": getattr(r, "event_type", None) or "general",
        "ticket_url": getattr(r, "ticket_url", None),
    }


@router.get("/events/{event_id}")
def get_calendar_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Single event lookup for the events-app /calendar/[id] detail page."""
    try:
        row = db.execute(sql_text(
            "SELECT id, date, title, time, end_time, location, description, "
            "source, source_url, venue, city, event_type, ticket_url, created_at "
            "FROM calendar_events WHERE id = CAST(:id AS uuid)"
        ), {"id": event_id}).fetchone()
    except Exception as e:
        logger.warning(f"Calendar event lookup failed: {e}")
        raise HTTPException(status_code=404, detail="Event not found")
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return _row_to_dict(row)


# ── RSVPs ────────────────────────────────────────────────────────────

class RsvpUser(BaseModel):
    user_id: str
    display_name: str | None
    picture_url: str | None


class RsvpSummary(BaseModel):
    event_id: str
    count: int
    is_going: bool
    sample_users: list[RsvpUser]  # up to 12 most recent


def _display_for(u: User) -> str | None:
    return u.display_name or u.full_name or ((u.email or "").split("@", 1)[0] or None)


@router.get("/events/{event_id}/rsvp", response_model=RsvpSummary)
def get_event_rsvp(
    event_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    total = db.query(func.count(EventRsvp.id)).filter(EventRsvp.event_id == event_id).scalar() or 0
    mine = db.query(EventRsvp).filter(
        EventRsvp.event_id == event_id, EventRsvp.user_id == user.id,
    ).first() if user else None
    sample_rows = (db.query(EventRsvp, User)
                     .join(User, User.id == EventRsvp.user_id)
                     .filter(EventRsvp.event_id == event_id)
                     .order_by(EventRsvp.created_at.desc())
                     .limit(12).all())
    return RsvpSummary(
        event_id=event_id,
        count=int(total),
        is_going=mine is not None,
        sample_users=[
            RsvpUser(user_id=str(u.id),
                     display_name=_display_for(u),
                     picture_url=u.picture_url)
            for _, u in sample_rows
        ],
    )


@router.post("/events/{event_id}/rsvp", response_model=RsvpSummary, status_code=status.HTTP_201_CREATED)
def rsvp_to_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify the event exists before letting users RSVP to a typo.
    row = db.execute(sql_text(
        "SELECT 1 FROM calendar_events WHERE id = CAST(:id AS uuid)"
    ), {"id": event_id}).fetchone()
    if not row:
        raise HTTPException(404, "Event not found")
    existing = db.query(EventRsvp).filter(
        EventRsvp.user_id == user.id, EventRsvp.event_id == event_id,
    ).first()
    if not existing:
        db.add(EventRsvp(user_id=user.id, event_id=event_id))
        db.commit()
    return get_event_rsvp(event_id, db, user)


@router.delete("/events/{event_id}/rsvp", response_model=RsvpSummary)
def unrsvp_from_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = db.query(EventRsvp).filter(
        EventRsvp.user_id == user.id, EventRsvp.event_id == event_id,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
    return get_event_rsvp(event_id, db, user)
