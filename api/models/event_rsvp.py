"""Event RSVPs — "I'm going" markers on a calendar_events row.

A check-in is present-tense (I'm here now, expires in 4h). An RSVP is
future-tense (I plan to go). They live in different tables because the
expiry/dedupe rules are different and because a venue check-in doesn't
have to map to a specific scheduled event.

`event_id` is NOT a FK constraint to calendar_events because the
scraper periodically purges + re-inserts rows (e.g. when run_music_scrape
deletes 'html:%' source rows during a parser fix). A CASCADE there
would wipe community RSVPs whenever we touch the scrapers. Stale RSVPs
(event_id no longer exists) are tolerated — they just don't render.

UNIQUE (user_id, event_id) makes the POST endpoint idempotent: clicking
"Going" twice doesn't create two rows.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class EventRsvp(Base):
    __tablename__ = "event_rsvps"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uix_event_rsvp_user_event"),
        Index("ix_event_rsvps_event", "event_id"),
        Index("ix_event_rsvps_user", "user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=False)  # references calendar_events.id; NOT a FK
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
