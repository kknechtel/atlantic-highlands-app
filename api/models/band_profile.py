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
from sqlalchemy import Column, String, DateTime, Float, Integer, Text, Index
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

    # Genre + rating, populated by scripts/enrich_band_genres.py or by an
    # admin. Both carry a source URL because everything here describes a
    # real working musician: we only store a genre a band states in its own
    # copy, and only a rating a page actually publishes. Nothing is
    # inferred from the act's name, and ratings are never computed by us —
    # the UI attributes them to the source.
    genres = Column(String, nullable=True)              # "Classic Rock, Blues"
    genre_source_url = Column(String, nullable=True)
    rating = Column(Float, nullable=True)               # 0-5, as published
    rating_count = Column(Integer, nullable=True)
    rating_source_url = Column(String, nullable=True)

    # A YouTube URL for the act, embedded on the band page. Populated by
    # enrich_band_genres.py from a video the band embeds on its own site,
    # or set by an admin. Stored as the original URL; the frontend derives
    # the embed form (see youtubeEmbed in web/lib/youtube.ts).
    video_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
