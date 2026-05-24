"""Check-ins — "I'm at X right now" markers for the events.ahnj.info app.

A check-in is intentionally lightweight:
  - venue_name + city are FREE TEXT (no FK to a venues table — we don't
    have one yet, and the universe of casual neighborhood places is
    bigger than our calendar_events `.venue` list).
  - checked_in_at defaults to NOW(); we never let clients set it.
  - "Currently here" is computed as `checked_in_at > NOW() - 4 hours`,
    which matches a typical evening-out duration. No background expiry
    job — the API filter does it.
  - One user can have multiple active check-ins (they could be at the
    Proving Ground, then walk to Donovan's an hour later).
  - `message` is a 200-char optional note ("we're at the back patio").
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (
        # Hottest query: SELECT * FROM checkins WHERE checked_in_at > NOW()-4h
        Index("ix_checkins_recent", "checked_in_at"),
        Index("ix_checkins_venue_recent", "venue_name", "checked_in_at"),
        Index("ix_checkins_user", "user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    venue_name = Column(String, nullable=False)
    city = Column(String, nullable=True)  # 'Atlantic Highlands' | 'Highlands' | 'Sea Bright' | other
    message = Column(String, nullable=True)  # capped to 200 chars in the route
    checked_in_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
