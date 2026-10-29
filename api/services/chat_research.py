"""Chat tools that make their own model calls: multi-part research and
reading a scanned page as an image.

Both bill to the user asking the question (CURRENT_USER is set by the chat
stream; asyncio.to_thread copies it into the tool thread), so they count
against that user's monthly budget like the chat itself.
"""
from __future__ import annotations

import base64
import contextvars
import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import api_key

log = logging.getLogger(__name__)

CURRENT_USER: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("chat_user", default=None)

MAX_SUBQUESTIONS = 5
PASSAGES_PER_SUBQUESTION = 6
PASSAGE_CHARS = 1500
MAX_PAGES_PER_CALL = 3


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=api_key("ANTHROPIC_API_KEY"))


def _text_of(msg) -> str:
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()


def _record(db: Session, source: str, model: str, msg) -> None:
    from services.usage import estimate_cost, record_usage
    u = msg.usage
    record_usage(
        db, source=source, model=model,
        input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
        estimated_cost_usd=estimate_cost(
            model, u.input_tokens or 0, u.output_tokens or 0,
            getattr(u, "cache_read_input_tokens", 0) or 0,
            getattr(u, "cache_creation_input_tokens", 0) or 0),
        user_id=CURRENT_USER.get(),
    )


# ── research_topic ──────────────────────────────────────────────────────

def _plan(db: Session, model: str, question: str) -> list[str]:
    msg = _client().messages.create(
        model=model, max_tokens=1500,
        messages=[{"role": "user", "content": (
            "Split this question about a town's public records into at most "
            f"{MAX_SUBQUESTIONS} specific search questions that together answer it "
            "(e.g. one per year, document type or sub-topic). Reply with only a JSON "
            f"array of strings.\n\nQuestion: {question}"
        )}],
    )
    _record(db, "research_topic", model, msg)
    raw = _text_of(msg)
    try:
        items = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except ValueError:
        return [question]
    subs = [str(q).strip() for q in items if str(q).strip()]
    return subs[:MAX_SUBQUESTIONS] or [question]


def research_topic(db: Session, args: dict, model: str) -> dict:
    """Break a broad question into sub-questions, search each, and return
    sourced findings. The main chat writes the final answer from these."""
    from routes.search import rank_chunks

    question = (args.get("question") or "").strip()
    if not question:
        return {"error": "question required"}
    subs = _plan(db, model, question)

    passages, docs, seen = [], {}, set()
    for sq in subs:
        rows, _, _, _ = rank_chunks(db, sq, municipality=args.get("municipality"),
                                    pool_size=30)
        for r in rows[:PASSAGES_PER_SUBQUESTION]:
            key = (str(r["document_id"]), r.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            passages.append(f"### {r['filename']} ({r.get('doc_date') or r.get('fiscal_year') or 'undated'})\n"
                            f"{(r.get('content') or '')[:PASSAGE_CHARS]}")
            docs.setdefault(str(r["document_id"]), {
                "document_id": str(r["document_id"]), "filename": r["filename"],
                "title": r.get("title"), "doc_date": r.get("doc_date"),
            })
    if not passages:
        return {"sub_questions": subs, "findings": "No passages found for any sub-question.", "documents": []}

    msg = _client().messages.create(
        model=model, max_tokens=4000,
        messages=[{"role": "user", "content": (
            f"Main question: {question}\nSub-questions:\n" + "\n".join(f"- {s}" for s in subs)
            + "\n\nUsing ONLY the passages below, write findings under each sub-question as short "
            "bullets. End every bullet with [source: <exact filename from the ### heading>]. "
            "Copy figures exactly. If the passages don't answer a sub-question, say 'Not found in "
            "the passages.'\n\n" + "\n\n".join(passages)
        )}],
    )
    _record(db, "research_topic", model, msg)
    return {"sub_questions": subs, "findings": _text_of(msg), "documents": list(docs.values())}


# ── view_document_page ──────────────────────────────────────────────────

def view_document_page(db: Session, args: dict, model: str) -> dict:
    """Render up to 3 PDF pages and have the model read them as images —
    for tables whose columns were lost in text extraction."""
    import fitz  # PyMuPDF
    from services.gemini_ocr import _page_png
    from services.s3_service import S3Service

    row = db.execute(text(
        "SELECT id, filename, s3_key, page_count FROM documents WHERE id = CAST(:id AS uuid)"
    ), {"id": str(args.get("document_id"))}).fetchone()
    if not row:
        return {"error": "not_found"}
    if not row.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF pages can be viewed; use read_document for this file."}
    pages = [int(p) for p in (args.get("pages") or []) if str(p).isdigit()][:MAX_PAGES_PER_CALL]
    if not pages:
        return {"error": "pages required (1-based page numbers, up to 3)"}

    pdf = fitz.open(stream=S3Service().download_file(row.s3_key), filetype="pdf")
    try:
        images = []
        for p in pages:
            if 1 <= p <= len(pdf):
                images.append((p, base64.b64encode(_page_png(pdf, p - 1)).decode()))
    finally:
        pdf.close()
    if not images:
        return {"error": f"page out of range (document has {row.page_count or '?'} pages)"}

    content: list[dict] = []
    for p, b64 in images:
        content.append({"type": "text", "text": f"Page {p}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    content.append({"type": "text", "text": (
        f"Question: {args.get('question') or 'Transcribe the tables on these pages.'}\n\n"
        "Report ONLY what is printed on these pages that bears on the question. Transcribe "
        "relevant table rows with their column headings (years, funds) so each figure's column "
        "is unambiguous. Copy numbers exactly. Do not calculate or infer; say if something is "
        "illegible or not on these pages."
    )})
    msg = _client().messages.create(model=model, max_tokens=3000,
                                    messages=[{"role": "user", "content": content}])
    _record(db, "page_view", model, msg)
    return {
        "document_id": str(row.id),
        "filename": row.filename,
        "pages": [p for p, _ in images],
        "reading": _text_of(msg),
    }
