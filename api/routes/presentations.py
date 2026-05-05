"""
Presentations & analytical decks.

  GET    /api/presentations
  POST   /api/presentations
  GET    /api/presentations/{id}
  PUT    /api/presentations/{id}
  DELETE /api/presentations/{id}
  PATCH  /api/presentations/{id}/section/{section_id}
  POST   /api/presentations/{id}/section
  DELETE /api/presentations/{id}/section/{section_id}
  POST   /api/presentations/{id}/attachments
  DELETE /api/presentations/{id}/attachments/{att_id}
  POST   /api/presentations/{id}/publish
  POST   /api/presentations/{id}/unpublish
  POST   /api/presentations/{id}/password         body: {password: str}
  POST   /api/presentations/{id}/ai-chat          SSE stream — propose_section, search_chunks
  POST   /api/presentations/{id}/fact-check       run citation entailment
  GET    /api/presentations/public/{slug}/meta    public, no auth
  GET    /api/presentations/public/{slug}         public, header X-Deck-Password if protected
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, SessionLocal
from models.presentation import Presentation
from models.user import User
from services.deck_chat_service import build_sections_summary, stream_deck_chat
from services.fact_check_service import fact_check_presentation

router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────────────────────

class CreatePresentation(BaseModel):
    title: str
    sections: Optional[list] = None
    theme: Optional[dict] = None


class UpdatePresentation(BaseModel):
    title: Optional[str] = None
    sections: Optional[list] = None
    attachments: Optional[list] = None
    theme: Optional[dict] = None


class SectionPatch(BaseModel):
    """Partial update to a single section. Any provided field overwrites."""
    title: Optional[str] = None
    body: Optional[str] = None
    kind: Optional[str] = None
    headers: Optional[list[str]] = None
    rows: Optional[list[list[str]]] = None
    caption: Optional[str] = None
    attachment_id: Optional[str] = None
    tsx: Optional[str] = None
    data: Optional[object] = None


class NewSection(BaseModel):
    kind: str  # narrative, table, attachment, react_component
    title: str = ""
    body: Optional[str] = None
    headers: Optional[list[str]] = None
    rows: Optional[list[list[str]]] = None
    caption: Optional[str] = None
    attachment_id: Optional[str] = None
    tsx: Optional[str] = None
    data: Optional[object] = None
    after_section_id: Optional[str] = None


class AttachmentBody(BaseModel):
    document_id: str
    caption: Optional[str] = None


class AIChatBody(BaseModel):
    message: str
    history: Optional[list[dict]] = None


class PasswordBody(BaseModel):
    password: str  # empty string clears the password


# ─── Helpers ────────────────────────────────────────────────────────────────

def _serialize(p: Presentation) -> dict:
    return {
        "id": str(p.id),
        "title": p.title,
        "slug": p.slug,
        "public_slug": p.public_slug,
        "status": p.status,
        "sections": p.sections or [],
        "attachments": p.attachments or [],
        "theme": p.theme or {},
        "last_fact_check": p.last_fact_check,
        "has_password": bool(p.public_password_hash),
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _get_or_404(db: Session, presentation_id: str) -> Presentation:
    p = db.query(Presentation).filter(Presentation.id == presentation_id).first()
    if not p:
        raise HTTPException(404, "Presentation not found")
    return p


def _ensure_section_ids(sections: list) -> list:
    """Every section needs a stable id so the editor can target it."""
    out = []
    for s in sections or []:
        s = dict(s)
        if not s.get("id"):
            s["id"] = f"sec_{uuid.uuid4().hex[:10]}"
        out.append(s)
    return out


# ─── CRUD ───────────────────────────────────────────────────────────────────

@router.get("")
def list_presentations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Presentation).order_by(Presentation.updated_at.desc()).limit(200).all()
    return [_serialize(p) for p in rows]


@router.post("")
def create_presentation(
    body: CreatePresentation,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = Presentation(
        title=body.title,
        sections=_ensure_section_ids(body.sections or []),
        theme=body.theme or {},
        created_by=user.id,
    )
    db.add(p); db.commit(); db.refresh(p)
    return _serialize(p)


@router.get("/{presentation_id}")
def get_presentation(presentation_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return _serialize(_get_or_404(db, presentation_id))


@router.put("/{presentation_id}")
def update_presentation(presentation_id: str, body: UpdatePresentation,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    if body.title is not None:
        p.title = body.title
    if body.sections is not None:
        p.sections = _ensure_section_ids(body.sections)
    if body.attachments is not None:
        p.attachments = body.attachments
    if body.theme is not None:
        p.theme = body.theme
    db.commit(); db.refresh(p)
    return _serialize(p)


@router.delete("/{presentation_id}")
def delete_presentation(presentation_id: str, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    db.delete(p); db.commit()
    return {"ok": True}


# ─── Sections ────────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/section")
def add_section(presentation_id: str, body: NewSection, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    new_sec = {
        "id": f"sec_{uuid.uuid4().hex[:10]}",
        "kind": body.kind,
        "title": body.title,
    }
    for k in ("body", "headers", "rows", "caption", "attachment_id", "tsx", "data"):
        v = getattr(body, k)
        if v is not None:
            new_sec[k] = v

    sections = list(p.sections or [])
    if body.after_section_id:
        idx = next((i for i, s in enumerate(sections) if s.get("id") == body.after_section_id), -1)
        sections.insert(idx + 1 if idx >= 0 else len(sections), new_sec)
    else:
        sections.append(new_sec)
    p.sections = sections
    db.commit(); db.refresh(p)
    return _serialize(p)


@router.patch("/{presentation_id}/section/{section_id}")
def patch_section(presentation_id: str, section_id: str, body: SectionPatch,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    sections = list(p.sections or [])
    for i, s in enumerate(sections):
        if s.get("id") == section_id:
            updated = dict(s)
            for k in ("title", "body", "kind", "headers", "rows", "caption", "attachment_id", "tsx", "data"):
                v = getattr(body, k)
                if v is not None:
                    updated[k] = v
            sections[i] = updated
            p.sections = sections
            db.commit(); db.refresh(p)
            return _serialize(p)
    raise HTTPException(404, "Section not found")


@router.delete("/{presentation_id}/section/{section_id}")
def delete_section(presentation_id: str, section_id: str,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    p.sections = [s for s in (p.sections or []) if s.get("id") != section_id]
    db.commit(); db.refresh(p)
    return _serialize(p)


# ─── Attachments ────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/attachments")
def add_attachment(presentation_id: str, body: AttachmentBody,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    from models.document import Document
    doc = db.query(Document).filter(Document.id == body.document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    att = {
        "id": f"att_{uuid.uuid4().hex[:10]}",
        "document_id": str(doc.id),
        "filename": doc.filename,
        "caption": body.caption,
    }
    p.attachments = [*(p.attachments or []), att]
    db.commit(); db.refresh(p)
    return _serialize(p)


@router.delete("/{presentation_id}/attachments/{att_id}")
def remove_attachment(presentation_id: str, att_id: str,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    p.attachments = [a for a in (p.attachments or []) if a.get("id") != att_id]
    db.commit(); db.refresh(p)
    return _serialize(p)


# ─── Publish / password ─────────────────────────────────────────────────────

@router.post("/{presentation_id}/publish")
def publish(presentation_id: str, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    if not p.public_slug:
        # short slugs are easier to share; collisions are negligible at this scale
        p.public_slug = secrets.token_urlsafe(9).replace("_", "").replace("-", "")[:12].lower()
    p.status = "published"
    p.published_at = datetime.utcnow()
    db.commit(); db.refresh(p)
    return _serialize(p)


@router.post("/{presentation_id}/unpublish")
def unpublish(presentation_id: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    p.public_slug = None
    p.status = "draft"
    p.published_at = None
    db.commit(); db.refresh(p)
    return _serialize(p)


@router.post("/{presentation_id}/password")
def set_password(presentation_id: str, body: PasswordBody,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    if not body.password:
        p.public_password_hash = None
        p.public_password_set_at = None
    else:
        p.public_password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
        p.public_password_set_at = datetime.utcnow()
    db.commit(); db.refresh(p)
    return _serialize(p)


# ─── AI chat ────────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/ai-chat")
async def ai_chat(presentation_id: str, body: AIChatBody, request: Request,
                  user: User = Depends(get_current_user)):
    """Stream a deck-aware AI chat. Emits SSE events: delta, tool_use, tool_result, proposal, done, error."""
    setup_db = SessionLocal()
    try:
        p = setup_db.query(Presentation).filter(Presentation.id == presentation_id).first()
        if not p:
            raise HTTPException(404, "Presentation not found")
        sections_summary = build_sections_summary(p.sections or [])
    finally:
        setup_db.close()

    return StreamingResponse(
        stream_deck_chat(body.message, sections_summary, body.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─── Fact-check ─────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/fact-check")
def fact_check(presentation_id: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    result = fact_check_presentation(db, p.sections or [])
    p.last_fact_check = result
    db.commit()
    return result


# ─── Public viewer ──────────────────────────────────────────────────────────

@router.get("/public/{slug}/meta")
def public_meta(slug: str, db: Session = Depends(get_db)):
    p = db.query(Presentation).filter(Presentation.public_slug == slug).first()
    if not p or p.status != "published":
        raise HTTPException(404, "Not found")
    return {
        "title": p.title,
        "has_password": bool(p.public_password_hash),
    }


@router.get("/public/{slug}")
def public_view(slug: str,
                x_deck_password: Optional[str] = Header(None, alias="X-Deck-Password"),
                db: Session = Depends(get_db)):
    p = db.query(Presentation).filter(Presentation.public_slug == slug).first()
    if not p or p.status != "published":
        raise HTTPException(404, "Not found")
    if p.public_password_hash:
        if not x_deck_password or not bcrypt.checkpw(
            x_deck_password.encode(), p.public_password_hash.encode()
        ):
            raise HTTPException(401, "Password required or incorrect")

    return {
        "title": p.title,
        "sections": p.sections or [],
        "attachments": p.attachments or [],
        "theme": p.theme or {},
        "published_at": p.published_at.isoformat() if p.published_at else None,
    }
