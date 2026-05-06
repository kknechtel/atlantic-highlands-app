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
  POST   /api/presentations/{id}/ai-edit          rewrite/expand/tighten one section
  GET    /api/presentations/{id}/export?format=pptx|docx   download office file
  POST   /api/presentations/from-chat             create deck from chat transcript
  GET    /api/presentations/public/{slug}/meta    public, no auth
  GET    /api/presentations/public/{slug}         public, header X-Deck-Password if protected
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime
from typing import List, Literal, Optional

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, text as sql_text
from sqlalchemy.orm import Session

from auth import (
    get_current_user,
    require_edit,
    require_owner_or_admin,
    require_view,
    shared_resource_ids,
    user_share_role,
)
from config import ANTHROPIC_API_KEY
from database import get_db, SessionLocal
from models.presentation import Presentation
from models.user import User
from services.deck_chat_service import build_sections_summary, stream_deck_chat
from services.deck_export import export_docx, export_pptx
from services.fact_check_service import fact_check_presentation

logger = logging.getLogger(__name__)

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

def _serialize(p: Presentation, user: Optional[User] = None,
               role: Optional[str] = None) -> dict:
    is_owner = bool(user and str(p.created_by) == str(user.id))
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
        "is_owner": is_owner,
        "share_role": None if is_owner else role,
    }


def _get_or_404(db: Session, presentation_id: str) -> Presentation:
    p = db.query(Presentation).filter(Presentation.id == presentation_id).first()
    if not p:
        raise HTTPException(404, "Presentation not found")
    return p


def _get_viewable_or_404(db: Session, presentation_id: str, user: User) -> Presentation:
    p = _get_or_404(db, presentation_id)
    require_view(db, "presentations", p.created_by, p.id, user)
    return p


def _get_editable_or_404(db: Session, presentation_id: str, user: User) -> Presentation:
    p = _get_or_404(db, presentation_id)
    require_edit(db, "presentations", p.created_by, p.id, user)
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
    q = db.query(Presentation)
    if not user.is_admin:
        shared_ids = shared_resource_ids(db, "presentations", user.id)
        if shared_ids:
            q = q.filter(or_(
                Presentation.created_by == user.id,
                Presentation.id.in_(shared_ids),
            ))
        else:
            q = q.filter(Presentation.created_by == user.id)
    rows = q.order_by(Presentation.updated_at.desc()).limit(200).all()

    role_by_id: dict[str, str] = {}
    if not user.is_admin:
        share_rows = db.execute(sql_text(
            "SELECT presentation_id, role FROM presentation_shares WHERE user_id = :uid"
        ), {"uid": str(user.id)}).fetchall()
        role_by_id = {str(r[0]): r[1] for r in share_rows}
    return [_serialize(p, user, role_by_id.get(str(p.id))) for p in rows]


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
    return _serialize(p, user)


@router.get("/{presentation_id}")
def get_presentation(presentation_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    p = _get_viewable_or_404(db, presentation_id, user)
    role = user_share_role(db, "presentations", p.id, user.id)
    return _serialize(p, user, role)


@router.put("/{presentation_id}")
def update_presentation(presentation_id: str, body: UpdatePresentation,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
    if body.title is not None:
        p.title = body.title
    if body.sections is not None:
        p.sections = _ensure_section_ids(body.sections)
    if body.attachments is not None:
        p.attachments = body.attachments
    if body.theme is not None:
        p.theme = body.theme
    db.commit(); db.refresh(p)
    return _serialize(p, user)


@router.delete("/{presentation_id}")
def delete_presentation(presentation_id: str, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    require_owner_or_admin(p.created_by, user)
    db.delete(p); db.commit()
    return {"ok": True}


# ─── Sections ────────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/section")
def add_section(presentation_id: str, body: NewSection, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
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
    return _serialize(p, user)


@router.patch("/{presentation_id}/section/{section_id}")
def patch_section(presentation_id: str, section_id: str, body: SectionPatch,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
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
            return _serialize(p, user)
    raise HTTPException(404, "Section not found")


@router.delete("/{presentation_id}/section/{section_id}")
def delete_section(presentation_id: str, section_id: str,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
    p.sections = [s for s in (p.sections or []) if s.get("id") != section_id]
    db.commit(); db.refresh(p)
    return _serialize(p, user)


# ─── Attachments ────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/attachments")
def add_attachment(presentation_id: str, body: AttachmentBody,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
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
    return _serialize(p, user)


@router.delete("/{presentation_id}/attachments/{att_id}")
def remove_attachment(presentation_id: str, att_id: str,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
    p.attachments = [a for a in (p.attachments or []) if a.get("id") != att_id]
    db.commit(); db.refresh(p)
    return _serialize(p, user)


# ─── Publish / password ─────────────────────────────────────────────────────
# Publishing/password = owner-only — sharing read access is what the share
# endpoints are for; making a deck public is a different decision that
# only the owner should be able to make.

@router.post("/{presentation_id}/publish")
def publish(presentation_id: str, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    require_owner_or_admin(p.created_by, user)
    if not p.public_slug:
        # short slugs are easier to share; collisions are negligible at this scale
        p.public_slug = secrets.token_urlsafe(9).replace("_", "").replace("-", "")[:12].lower()
    p.status = "published"
    p.published_at = datetime.utcnow()
    db.commit(); db.refresh(p)
    return _serialize(p, user)


@router.post("/{presentation_id}/unpublish")
def unpublish(presentation_id: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    require_owner_or_admin(p.created_by, user)
    p.public_slug = None
    p.status = "draft"
    p.published_at = None
    db.commit(); db.refresh(p)
    return _serialize(p, user)


@router.post("/{presentation_id}/password")
def set_password(presentation_id: str, body: PasswordBody,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    require_owner_or_admin(p.created_by, user)
    if not body.password:
        p.public_password_hash = None
        p.public_password_set_at = None
    else:
        p.public_password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
        p.public_password_set_at = datetime.utcnow()
    db.commit(); db.refresh(p)
    return _serialize(p, user)


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
        require_view(setup_db, "presentations", p.created_by, p.id, user)
        sections_summary = build_sections_summary(p.sections or [])
    finally:
        setup_db.close()

    return StreamingResponse(
        stream_deck_chat(
            body.message, sections_summary, body.history,
            user_id=str(user.id), presentation_id=presentation_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─── Fact-check ─────────────────────────────────────────────────────────────

@router.post("/{presentation_id}/fact-check")
def fact_check(presentation_id: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    p = _get_editable_or_404(db, presentation_id, user)
    result = fact_check_presentation(
        db, p.sections or [],
        user_id=str(user.id), presentation_id=str(p.id),
    )
    p.last_fact_check = result
    db.commit()
    return result


# ─── Export (PPTX / DOCX) ───────────────────────────────────────────────────

@router.get("/{presentation_id}/export")
def export_deck(
    presentation_id: str,
    format: Literal["pptx", "docx"] = Query("pptx"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream a generated PPTX or DOCX of the presentation."""
    p = _get_viewable_or_404(db, presentation_id, user)

    if format == "pptx":
        data, filename = export_pptx(p)
        media = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        data, filename = export_docx(p)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── AI-edit (rewrite / expand / tighten / fact-check one section) ──────────

class AIEditBody(BaseModel):
    section_id: str
    action: Literal["rewrite_tighter", "expand", "fact_polish", "translate_plain", "summarize"]
    instructions: Optional[str] = None  # extra freeform guidance for the AI


_AI_EDIT_GUIDANCE = {
    "rewrite_tighter":
        "Rewrite the section to be tighter and more direct. Cut filler. Keep all "
        "facts, numbers, and citations. Aim for ~30-40% fewer words.",
    "expand":
        "Expand the section with additional detail, context, and supporting facts. "
        "If the original cites documents, weave in additional related citations from "
        "the same documents where useful. Do not invent facts.",
    "fact_polish":
        "Tighten any imprecise claims. Where the original says approximations, replace "
        "with the actual figures from cited sources if you can verify them. Flag any "
        "unverifiable claims with [unverified]. Keep all citations.",
    "translate_plain":
        "Rewrite the section in plain English suitable for a resident with no government "
        "or finance background. Preserve all numbers and citations. Avoid jargon.",
    "summarize":
        "Replace the section body with a 3-5 bullet executive summary. Keep all "
        "[source: ...] citations associated with their facts.",
}


@router.post("/{presentation_id}/ai-edit")
def ai_edit_section(
    presentation_id: str,
    body: AIEditBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply an AI-powered transformation to a single section's body. Returns
    the updated presentation (the section's `body` is replaced in place).

    Synchronous (no SSE) — these are usually fast (<10s) on Sonnet."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
    p = _get_editable_or_404(db, presentation_id, user)

    sections = list(p.sections or [])
    target_idx = next((i for i, s in enumerate(sections) if s.get("id") == body.section_id), -1)
    if target_idx < 0:
        raise HTTPException(404, "Section not found")
    section = dict(sections[target_idx])
    if section.get("kind") != "narrative":
        raise HTTPException(400, "ai-edit currently only works on narrative sections")

    original_body = section.get("body") or ""
    if not original_body.strip():
        raise HTTPException(400, "Section is empty — nothing to edit")

    guidance = _AI_EDIT_GUIDANCE[body.action]
    if body.instructions:
        guidance += "\n\nAdditional instructions from the operator:\n" + body.instructions

    prompt = (
        f"You are editing one section of a presentation about Atlantic Highlands, NJ municipal affairs.\n\n"
        f"## Action: {body.action}\n{guidance}\n\n"
        f"## Section title: {section.get('title') or '(untitled)'}\n\n"
        f"## Current body:\n{original_body}\n\n"
        f"Output ONLY the new markdown body (no commentary, no fences, no preamble)."
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        new_body = ""
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                new_body += block.text or ""
        new_body = new_body.strip()
        # Drop accidental code-fence wrappers some models emit
        new_body = new_body.removeprefix("```markdown").removeprefix("```md").removeprefix("```").strip()
        new_body = new_body.removesuffix("```").strip()
        if not new_body:
            raise HTTPException(502, "AI returned empty body")
        from services.usage import record_usage
        record_usage(
            db, source="ai_edit", model="claude-sonnet-4-6",
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
            user_id=str(user.id),
            resource_type="presentation", resource_id=str(p.id),
            metadata={"action": body.action, "section_id": body.section_id},
        )
    except anthropic.APIStatusError as exc:
        logger.error("ai-edit Anthropic error: %s", exc)
        raise HTTPException(502, f"AI service error: {getattr(exc, 'message', str(exc))}")
    except Exception as exc:
        logger.exception("ai-edit failed")
        raise HTTPException(500, str(exc)[:300])

    section["body"] = new_body
    sections[target_idx] = section
    p.sections = sections
    db.commit(); db.refresh(p)
    return _serialize(p, user)


# ─── From-chat: turn a chat transcript into a draft deck ────────────────────

class FromChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class FromChatBody(BaseModel):
    messages: List[FromChatMessage]
    title_hint: Optional[str] = None


_FROM_CHAT_PROMPT = """You are converting a chat transcript about Atlantic Highlands, NJ into a structured presentation.

Output ONLY a JSON object of this shape:
{{
  "title": "<concise deck title>",
  "sections": [
    {{ "kind": "narrative", "title": "<heading>", "body": "<markdown body with citations and embedded chart fences>" }},
    ...
  ]
}}

RULES:
- 6-10 sections. Group related findings together. Don't make one section per chat turn.
- Each narrative body should be 2-6 paragraphs of substantive content.
- PRESERVE every [source: filename.pdf] citation from the assistant turns — do not drop them.
- The transcript contains tokens like [[CHART_PLACEHOLDER_0]], [[CHART_PLACEHOLDER_1]], etc.
  These represent live Chart.js charts the user will see in the deck. Keep the EXACT token
  text in the narrative body it belongs to. Do NOT replace, paraphrase, expand, or remove it
  — the backend swaps the token back to the original chart after you respond. If a section
  references a chart, just include the [[CHART_PLACEHOLDER_N]] token on its own line
  inside the markdown body.
- PRESERVE every markdown table inside the narrative body. Don't convert to "table" sections
  unless the table is the entire point of a section — narrative sections render markdown
  tables natively, including the chart fences.
- DO NOT paraphrase or round numbers. Copy figures, dollar amounts, percentages, dates,
  and proper nouns verbatim from the assistant's output.
- DO NOT summarize away findings. If the chat covered 8 topics, the deck should cover all 8.
- If the user typed a clear prompt at the top, weave it into a section 1 "Background" or "Question".
- title_hint, if provided, is a strong suggestion for the deck title.

Output ONLY valid JSON — no fences, no commentary."""


def _structure_chat_with_claude(messages: list[dict], title_hint: Optional[str]) -> tuple[dict, int, int]:
    """Returns (deck_json, input_tokens, output_tokens) so the caller can
    record usage."""
    import anthropic
    import re as _re
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Belt-and-suspenders: extract every ```chart fence from the transcript and
    # replace with an opaque placeholder before sending to Claude. The model
    # would otherwise paraphrase or drop the JSON. We restore the original
    # fences after Claude returns the structured deck.
    chart_blocks: list[str] = []
    def _stash_chart(m):
        idx = len(chart_blocks)
        chart_blocks.append(m.group(0))
        return f"[[CHART_PLACEHOLDER_{idx}]]"

    # Trim each turn to a sane size — full chat transcripts often run 300K+
    # tokens once tool results bloat the assistant turns. The structurer doesn't
    # need every intermediate "Now let me check…" line, just the final content.
    PER_TURN_CHARS = 12000
    transcript_lines = []
    for m in messages:
        role = (m.get("role") or "user").upper()
        body = (m.get("content") or "")
        # Extract chart blocks BEFORE trimming so a fence that straddles the cut
        # still gets preserved in full.
        body = _re.sub(r"```chart\s*\n[\s\S]*?\n```", _stash_chart, body)
        if len(body) > PER_TURN_CHARS:
            body = body[:PER_TURN_CHARS] + "\n\n[... truncated ...]"
        transcript_lines.append(f"## {role}\n\n{body}")
    transcript = "\n\n---\n\n".join(transcript_lines)

    prompt = _FROM_CHAT_PROMPT
    if title_hint:
        prompt += f"\n\ntitle_hint: {title_hint}"

    # Use Haiku 4.5 — structuring a transcript into JSON sections is a
    # straightforward reformatting task; Sonnet's ~5x latency isn't worth it.
    # 1M-context beta still useful when transcripts are large after trimming.
    # Anthropic SDK refuses non-streaming for long requests, so we stream.
    text = ""
    in_t = out_t = 0
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=12000,
        system=prompt,
        messages=[{"role": "user", "content": f"TRANSCRIPT:\n\n{transcript}"}],
        extra_headers={"anthropic-beta": "context-1m-2025-08-07"},
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
        try:
            final_msg = stream.get_final_message()
            in_t = getattr(final_msg.usage, "input_tokens", 0) or 0
            out_t = getattr(final_msg.usage, "output_tokens", 0) or 0
        except Exception:
            pass
    text = text.strip().removeprefix("```json").removeprefix("```").strip().removesuffix("```").strip()

    def _restore_charts(obj):
        """Walk the parsed deck JSON and substitute placeholders back to
        their original ```chart``` fences. Operates on dict/list/str."""
        if isinstance(obj, str):
            def repl(m):
                idx = int(m.group(1))
                return chart_blocks[idx] if 0 <= idx < len(chart_blocks) else m.group(0)
            return _re.sub(r"\[\[CHART_PLACEHOLDER_(\d+)\]\]", repl, obj)
        if isinstance(obj, list):
            return [_restore_charts(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _restore_charts(v) for k, v in obj.items()}
        return obj

    try:
        return _restore_charts(json.loads(text)), in_t, out_t
    except json.JSONDecodeError:
        # Best-effort: salvage the largest JSON object substring
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return _restore_charts(json.loads(text[start:end + 1])), in_t, out_t
            except Exception:
                pass
        raise HTTPException(502, "AI returned invalid JSON for the deck structure")


@router.post("/from-chat")
def create_from_chat(
    body: FromChatBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Convert a chat conversation into a draft presentation. The assistant
    structures the messages into 4-8 sections, preserving citations."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
    if not body.messages:
        raise HTTPException(400, "messages cannot be empty")

    msg_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
    structured, in_t, out_t = _structure_chat_with_claude(msg_dicts, body.title_hint)

    title = (structured.get("title") or body.title_hint or "Untitled Presentation").strip()
    raw_sections = structured.get("sections") or []
    sections = _ensure_section_ids([
        s for s in raw_sections
        if isinstance(s, dict) and s.get("kind") in ("narrative", "table")
    ])

    p = Presentation(
        title=title,
        sections=sections,
        theme={},
        created_by=user.id,
    )
    db.add(p); db.commit(); db.refresh(p)

    from services.usage import record_usage
    record_usage(
        db, source="deck_from_chat", model="claude-haiku-4-5-20251001",
        input_tokens=in_t, output_tokens=out_t,
        user_id=str(user.id),
        resource_type="presentation", resource_id=str(p.id),
        metadata={"message_count": len(msg_dicts)},
    )

    return _serialize(p, user)


# ─── Comments (threaded review) ─────────────────────────────────────────────

class CommentBody(BaseModel):
    section_id: Optional[str] = None
    body: str
    parent_comment_id: Optional[str] = None


def _serialize_comment(c) -> dict:
    return {
        "id": str(c.id),
        "presentation_id": str(c.presentation_id),
        "section_id": c.section_id,
        "parent_comment_id": str(c.parent_comment_id) if c.parent_comment_id else None,
        "author_email": c.author_email,
        "author_name": c.author_name,
        "body": c.body,
        "resolved": c.resolved,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/{presentation_id}/comments")
def list_comments(presentation_id: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    from models.presentation import PresentationComment
    _get_viewable_or_404(db, presentation_id, user)
    rows = (
        db.query(PresentationComment)
        .filter(PresentationComment.presentation_id == presentation_id)
        .order_by(PresentationComment.created_at)
        .all()
    )
    return [_serialize_comment(c) for c in rows]


@router.post("/{presentation_id}/comments")
def add_comment(presentation_id: str, body: CommentBody,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from models.presentation import PresentationComment
    if not body.body.strip():
        raise HTTPException(400, "body cannot be empty")
    _get_viewable_or_404(db, presentation_id, user)
    c = PresentationComment(
        presentation_id=presentation_id,
        section_id=body.section_id,
        parent_comment_id=body.parent_comment_id,
        author_email=user.email,
        author_name=getattr(user, "full_name", None) or user.email,
        body=body.body.strip(),
    )
    db.add(c); db.commit(); db.refresh(c)
    return _serialize_comment(c)


@router.patch("/{presentation_id}/comments/{comment_id}/resolve")
def toggle_resolve(presentation_id: str, comment_id: str,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from models.presentation import PresentationComment
    _get_viewable_or_404(db, presentation_id, user)
    c = (
        db.query(PresentationComment)
        .filter(PresentationComment.id == comment_id,
                PresentationComment.presentation_id == presentation_id)
        .first()
    )
    if not c:
        raise HTTPException(404, "Comment not found")
    c.resolved = not c.resolved
    c.resolved_by_email = user.email if c.resolved else None
    db.commit(); db.refresh(c)
    return _serialize_comment(c)


@router.delete("/{presentation_id}/comments/{comment_id}")
def delete_comment(presentation_id: str, comment_id: str,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from models.presentation import PresentationComment
    p = _get_viewable_or_404(db, presentation_id, user)
    c = (
        db.query(PresentationComment)
        .filter(PresentationComment.id == comment_id,
                PresentationComment.presentation_id == presentation_id)
        .first()
    )
    if not c:
        raise HTTPException(404, "Comment not found")
    # Only the comment author, the presentation owner, or an admin can delete.
    is_author = c.author_email and user.email and c.author_email.lower() == user.email.lower()
    is_owner = str(p.created_by) == str(user.id)
    if not (is_author or is_owner or user.is_admin):
        raise HTTPException(403, "You can only delete your own comments")
    db.delete(c); db.commit()
    return {"ok": True}


# ─── Sharing ────────────────────────────────────────────────────────────────

class ShareCreateBody(BaseModel):
    user_id: str
    role: Literal["viewer", "editor"] = "viewer"


@router.get("/{presentation_id}/shares")
def list_presentation_shares(presentation_id: str, db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    p = _get_viewable_or_404(db, presentation_id, user)
    rows = db.execute(sql_text("""
        SELECT u.id, u.email, u.full_name, ps.role
        FROM presentation_shares ps
        JOIN users u ON u.id = ps.user_id
        WHERE ps.presentation_id = :pid
        ORDER BY u.email
    """), {"pid": str(p.id)}).fetchall()
    return [
        {"user_id": str(r[0]), "email": r[1], "full_name": r[2], "role": r[3]}
        for r in rows
    ]


@router.post("/{presentation_id}/shares")
def add_presentation_share(presentation_id: str, body: ShareCreateBody,
                           db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    require_owner_or_admin(p.created_by, user)
    if str(body.user_id) == str(p.created_by):
        raise HTTPException(400, "Owner already has full access")
    target = db.query(User).filter(User.id == body.user_id).first()
    if not target:
        raise HTTPException(404, "User not found")
    db.execute(sql_text("""
        INSERT INTO presentation_shares (presentation_id, user_id, role)
        VALUES (:pid, :uid, :role)
        ON CONFLICT (presentation_id, user_id) DO UPDATE SET role = EXCLUDED.role
    """), {"pid": str(p.id), "uid": str(body.user_id), "role": body.role})
    db.commit()
    return {
        "user_id": str(target.id),
        "email": target.email,
        "full_name": target.full_name,
        "role": body.role,
    }


@router.delete("/{presentation_id}/shares/{user_id}")
def remove_presentation_share(presentation_id: str, user_id: str,
                              db: Session = Depends(get_db),
                              user: User = Depends(get_current_user)):
    p = _get_or_404(db, presentation_id)
    require_owner_or_admin(p.created_by, user)
    db.execute(sql_text(
        "DELETE FROM presentation_shares "
        "WHERE presentation_id = :pid AND user_id = :uid"
    ), {"pid": str(p.id), "uid": str(user_id)})
    db.commit()
    return {"ok": True}


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


@router.get("/public/{slug}/citation")
def public_citation_view(
    slug: str,
    filename: str = Query(...),
    x_deck_password: Optional[str] = Header(None, alias="X-Deck-Password"),
    db: Session = Depends(get_db),
):
    """Resolve a [source: filename.pdf] citation in a published deck to a
    short-lived signed S3 URL. Only documents whose filename appears as a
    citation in this deck (or as an attachment) can be resolved — the slug
    acts as the access token."""
    from models.document import Document
    from services.s3_service import S3Service
    import re as _re

    p = db.query(Presentation).filter(Presentation.public_slug == slug).first()
    if not p or p.status != "published":
        raise HTTPException(404, "Not found")
    if p.public_password_hash:
        if not x_deck_password or not bcrypt.checkpw(
            x_deck_password.encode(), p.public_password_hash.encode()
        ):
            raise HTTPException(401, "Password required or incorrect")

    # Build the set of filenames cited anywhere in the deck (sections + attachments).
    allowed: set[str] = set()
    for s in (p.sections or []):
        body = (s.get("body") or "")
        for m in _re.findall(r"\[source:\s*([^\]]+)\]", body):
            for fn in _re.split(r"\s*[,|;]\s*", m):
                fn = fn.strip()
                if fn:
                    allowed.add(fn)
    for att in (p.attachments or []):
        if att.get("filename"):
            allowed.add(att["filename"])

    if filename not in allowed:
        raise HTTPException(404, "Citation not in this deck")

    doc = db.query(Document).filter(Document.filename == filename).first()
    if not doc or not doc.s3_key:
        raise HTTPException(404, "Document not found")

    s3 = S3Service()
    url = s3.get_presigned_url(doc.s3_key, expires_in=900)
    return {"url": url, "filename": doc.filename}
