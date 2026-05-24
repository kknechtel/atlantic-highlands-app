"""Community chat — one global feed for events.ahnj.info.

Endpoints (mounted at /api/community/chat):
  GET    /messages                list newest N (default 50), or after a cursor
  POST   /messages                create a message (optionally ref'd to event/checkin)
  DELETE /messages/{id}           own or admin

Polling-based — the frontend hits GET /messages every ~10s with the
`after=<iso>` cursor to pull only new rows. Borough scale (~4500 people)
won't need WebSockets; if traffic ever justifies it we can swap to SSE
later without changing the client API surface much.

Embeds: each message can carry one `ref_type` + `ref_id`. The GET
response inlines a small snapshot of the referenced thing (event title /
checkin venue) so the frontend doesn't fan out 50 lookups per refresh.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.checkin import Checkin
from models.community_message import CommunityMessage, CommunityMessageRefType
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BODY_CHARS = 1000


# ── Schemas ──────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)
    ref_type: Optional[CommunityMessageRefType] = None
    ref_id: Optional[str] = None


class RefSnapshot(BaseModel):
    kind: CommunityMessageRefType
    id: str
    title: str
    subtitle: Optional[str]  # venue/city/time context


class MessageOut(BaseModel):
    id: str
    user_id: str
    user_display_name: Optional[str]
    user_picture_url: Optional[str]
    body: str
    ref: Optional[RefSnapshot]
    created_at: datetime


def _display_name_for(u: User) -> str:
    if u.display_name:
        return u.display_name
    if u.full_name:
        return u.full_name.split(" ", 1)[0]
    return (u.email or "").split("@", 1)[0] or "Someone"


def _snapshot_for_ref(
    db: Session,
    ref_type: Optional[CommunityMessageRefType],
    ref_id: Optional[str],
) -> Optional[RefSnapshot]:
    """Resolve a ref_type + ref_id into a small display snapshot.
    Returns None when the referenced row no longer exists — the message
    still renders, just without the embed."""
    if not ref_type or not ref_id:
        return None
    if ref_type == CommunityMessageRefType.event:
        row = db.execute(text(
            "SELECT id, title, time, venue, city, date "
            "FROM calendar_events WHERE id = CAST(:id AS uuid)"
        ), {"id": ref_id}).fetchone()
        if not row:
            return None
        sub_parts = []
        if row.time:
            sub_parts.append(row.time)
        if row.venue:
            sub_parts.append(row.venue)
        if row.city:
            sub_parts.append(row.city)
        return RefSnapshot(
            kind=ref_type, id=str(row.id), title=row.title,
            subtitle=" · ".join(sub_parts) or row.date.isoformat() if row.date else None,
        )
    if ref_type == CommunityMessageRefType.checkin:
        c = db.query(Checkin).filter(Checkin.id == ref_id).first()
        if not c:
            return None
        sub = c.city if c.city else None
        return RefSnapshot(
            kind=ref_type, id=str(c.id), title=c.venue_name, subtitle=sub,
        )
    return None


def _to_out(m: CommunityMessage, user: User, ref: Optional[RefSnapshot]) -> MessageOut:
    return MessageOut(
        id=str(m.id),
        user_id=str(m.user_id),
        user_display_name=_display_name_for(user),
        user_picture_url=getattr(user, "picture_url", None),
        body=m.body,
        ref=ref,
        created_at=m.created_at,
    )


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    after: Optional[datetime] = Query(None, description="Return only messages newer than this ISO timestamp"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Newest-first list. With `after`, returns only rows strictly newer
    than the cursor (polling). Without, returns the newest `limit`."""
    q = (db.query(CommunityMessage, User)
           .join(User, User.id == CommunityMessage.user_id))
    if after:
        q = q.filter(CommunityMessage.created_at > after)
    rows = q.order_by(desc(CommunityMessage.created_at)).limit(limit).all()
    return [_to_out(m, u, _snapshot_for_ref(db, m.ref_type, str(m.ref_id) if m.ref_id else None))
            for m, u in rows]


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(
    payload: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Validate ref pair — both or neither
    if (payload.ref_type is None) ^ (payload.ref_id is None):
        raise HTTPException(400, "ref_type and ref_id must both be set or both omitted")

    if payload.ref_id:
        ref_check = _snapshot_for_ref(db, payload.ref_type, payload.ref_id)
        if ref_check is None:
            raise HTTPException(400, "Referenced event or check-in does not exist")

    import uuid as _uuid
    m = CommunityMessage(
        user_id=user.id,
        body=payload.body.strip(),
        ref_type=payload.ref_type,
        ref_id=_uuid.UUID(payload.ref_id) if payload.ref_id else None,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    snap = _snapshot_for_ref(db, m.ref_type, str(m.ref_id) if m.ref_id else None)
    return _to_out(m, user, snap)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = db.query(CommunityMessage).filter(CommunityMessage.id == message_id).first()
    if not m:
        raise HTTPException(404, "Message not found")
    if m.user_id != user.id and not getattr(user, "is_admin", False):
        raise HTTPException(403, "You can only delete your own messages")
    db.delete(m)
    db.commit()
    return None
