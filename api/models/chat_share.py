"""ChatShare — a public, read-only link to one chat answer.

The question and answer are copied at share time, so later edits or
deletions in the chat don't change what the link shows. Revoke by setting
revoked_at; expired or revoked links return 404.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class ChatShare(Base):
    __tablename__ = "chat_shares"

    token = Column(String(64), primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, nullable=False, default=0)
