"""Community chat messages — one global feed for events.ahnj.info.

Intentionally simple: a single global room, no DMs, no per-venue rooms,
no per-event threads. Each message can OPTIONALLY reference one external
thing (an event row or a check-in) so users can post "going to this
show tonight" with a clickable embed below the text.

Why no rooms: user explicitly scoped this as "one general group chat,
small scale thing" for a 4500-person borough. Adding rooms makes the
v1 feel empty (everyone scattered across channels with 2 users each).
We can add rooms later when message volume justifies it.

Why DELETE allowed only on own messages or by admins: standard
community-moderation baseline. Hard delete, not soft — keeps the table
trim and matches user expectation when they regret a post.
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class CommunityMessageRefType(str, enum.Enum):
    event = "event"      # ref_id = calendar_events.id
    checkin = "checkin"  # ref_id = checkins.id


class CommunityMessage(Base):
    __tablename__ = "community_messages"
    __table_args__ = (
        # Feed query: ORDER BY created_at DESC LIMIT 50
        Index("ix_community_messages_created", "created_at"),
        Index("ix_community_messages_user", "user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = Column(Text, nullable=False)  # 1000-char cap enforced in the route

    # Optional reference to an event or check-in. The FK is NOT enforced
    # at the DB level (no ForeignKey here) because the referenced row may
    # be deleted later (check-ins expire visually, events get rescraped)
    # and we don't want a CASCADE wiping community history.
    ref_type = Column(Enum(
        CommunityMessageRefType,
        name="community_message_ref_type",
        values_callable=lambda e: [m.value for m in e],
    ), nullable=True)
    ref_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
