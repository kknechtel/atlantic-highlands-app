"""Admin-curated band profile routes.

Endpoints (mounted at /api/bands):
  GET  /profile/{name}    public — returns the profile or 404
  PUT  /profile/{name}    admin only — upsert (creates if missing)
  DELETE /profile/{name}  admin only

Name matching is case-insensitive (we normalize to name_lower at write +
read). Display name preserves whatever the admin typed.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user, get_current_user_optional
from database import get_db
from models.band_profile import BandProfile
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class ProfilePayload(BaseModel):
    facebook_url: str | None = Field(default=None, max_length=500)
    instagram_url: str | None = Field(default=None, max_length=500)
    website_url: str | None = Field(default=None, max_length=500)
    bandsintown_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=2000)
    photo_url: str | None = Field(default=None, max_length=500)
    # Comma-separated ("Classic Rock, Blues"). The source URL is required
    # alongside a rating — see ProfileOut.
    genres: str | None = Field(default=None, max_length=300)
    genre_source_url: str | None = Field(default=None, max_length=500)
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)
    rating_source_url: str | None = Field(default=None, max_length=500)


class ProfileOut(BaseModel):
    name: str
    facebook_url: str | None
    instagram_url: str | None
    website_url: str | None
    bandsintown_url: str | None
    bio: str | None
    photo_url: str | None
    genres: str | None
    genre_source_url: str | None
    rating: float | None
    rating_count: int | None
    rating_source_url: str | None


def _to_out(p: BandProfile) -> ProfileOut:
    return ProfileOut(
        name=p.name,
        facebook_url=p.facebook_url,
        instagram_url=p.instagram_url,
        website_url=p.website_url,
        bandsintown_url=p.bandsintown_url,
        bio=p.bio,
        photo_url=p.photo_url,
        genres=p.genres,
        genre_source_url=p.genre_source_url,
        # A rating with no source URL is not shown by the band page, so
        # don't hand one out — see the rating block in bands/[name].
        rating=p.rating if p.rating_source_url else None,
        rating_count=p.rating_count if p.rating_source_url else None,
        rating_source_url=p.rating_source_url,
    )


def _require_admin(user: User) -> None:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")


@router.get("/profile/{name}", response_model=ProfileOut)
def get_profile(
    name: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    key = (name or "").strip().lower()
    if not key:
        raise HTTPException(404, "Not found")
    p = db.query(BandProfile).filter(BandProfile.name_lower == key).first()
    if not p:
        raise HTTPException(404, "Profile not yet curated")
    return _to_out(p)


@router.put("/profile/{name}", response_model=ProfileOut)
def upsert_profile(
    name: str,
    payload: ProfilePayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    display = (name or "").strip()
    if not display:
        raise HTTPException(400, "Band name required")
    key = display.lower()
    p = db.query(BandProfile).filter(BandProfile.name_lower == key).first()
    if not p:
        p = BandProfile(name=display, name_lower=key)
        db.add(p)
    else:
        p.name = display  # admin can re-cap on update
    # Trim empties → None so the frontend treats blanks consistently.
    def _norm(v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    p.facebook_url = _norm(payload.facebook_url)
    p.instagram_url = _norm(payload.instagram_url)
    p.website_url = _norm(payload.website_url)
    p.bandsintown_url = _norm(payload.bandsintown_url)
    p.bio = _norm(payload.bio)
    p.photo_url = _norm(payload.photo_url)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/profile/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    name: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    key = (name or "").strip().lower()
    p = db.query(BandProfile).filter(BandProfile.name_lower == key).first()
    if p:
        db.delete(p)
        db.commit()
    return None
