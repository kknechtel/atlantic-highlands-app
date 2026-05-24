"""Admin-curated band profiles — overrides for the static bandGuide.ts.

The Edgewater band guide gives us 45 known Jersey Shore bands with
ratings + tags. But:
  - Many bands we scrape (Carl Gentry, Liam Davis Band, etc.) aren't
    in that guide
  - Even guide entries' `socialMedia` is sometimes just "@handle" with
    no inferable platform

This table lets admins fill in real Facebook / Instagram / website
URLs per band, plus a short bio. The band detail page reads from here
FIRST, falls back to the static guide, falls back to platform-search
links.

Name is canonical-case (user-friendly) but matched case-insensitively.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class BandProfile(Base):
    __tablename__ = "band_profiles"
    __table_args__ = (
        Index("ix_band_profiles_name_lower", "name_lower", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # `name` is the display string ("The Cliffs"); `name_lower` is the
    # lookup key (lowercased, unique). Both stored so a future "rename"
    # operation doesn't require recomputing the lookup index.
    name = Column(String, nullable=False)
    name_lower = Column(String, nullable=False, unique=True)

    facebook_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    website_url = Column(String, nullable=True)
    bandsintown_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
