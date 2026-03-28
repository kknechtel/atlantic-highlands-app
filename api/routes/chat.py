"""
AI Chat - Atlantic Highlands Expert with full document knowledge, history, and RAG.
Not a generic assistant - an expert on AH governance, finances, school district, and all documents.
"""
import logging
import json
import asyncio
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text, desc

from database import get_db
from models.document import Document
from models.financial import FinancialStatement, FinancialLineItem
from models.user import User
from auth import get_current_user
from services.s3_service import S3Service
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    document_id: str | None = None
    scope_type: str = "all"  # all, document, project, category
    scope_id: str | None = None
    model: str = "gemini"


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list


# ─── Knowledge Base Builder ───────────────────────────────────────────

def _build_system_prompt(db: Session, document_id: str = None, query: str = "") -> str:
    """Build a comprehensive system prompt with all AH knowledge."""

    # 1. Core identity and background knowledge
    background = """You are the Atlantic Highlands AI Expert - a deeply knowledgeable analyst specializing in the Borough of Atlantic Highlands, NJ and its school district.

BACKGROUND:
- Atlantic Highlands is a borough in Monmouth County, NJ (pop ~4,400)
- Governed by a Mayor-Council form of government
- School district: Atlantic Highlands Elementary School (AHES), pre-K through 8th grade
- Part of the Henry Hudson Regional School District (Tri-District) with Highlands Borough
- Henry Hudson Regional High School (HHRS) serves both communities

You have access to a comprehensive document library of 728+ indexed documents including:
- Municipal budgets (2004-2026)
- Annual audit reports
- Annual financial statements
- Borough council meeting minutes and agendas
- Ordinances and resolutions
- School board meeting minutes and agendas
- School district budgets, audits, and comprehensive financial reports
- Legal documents, OPRA requests, and more

ALWAYS cite specific documents and figures. Use [source: filename] format for citations.
When discussing finances, show actual dollar amounts and year-over-year changes.
Be specific, authoritative, and analytical. You ARE the expert on this town."""

    # 2. Financial data summary
    financial_context = _build_financial_summary(db)

    # 3. Document search for query-specific context
    doc_context = ""
    if document_id:
        doc_context = _get_document_text(db, document_id)
    elif query:
        doc_context = _search_relevant_docs(db, query)

    # 4. Recent document summaries for general awareness
    recent_awareness = _get_document_awareness(db)

    return f"""{background}

{financial_context}

{doc_context}

{recent_awareness}

INSTRUCTIONS:
- Always use actual data from the documents above
- Cite sources with [source: filename.pdf] format
- Calculate year-over-year changes when comparing periods
- If you don't have specific data, say what document would contain it
- Be analytical and insightful, not just descriptive
- Reference specific resolutions, ordinances, and meeting dates when relevant"""


def _build_financial_summary(db: Session) -> str:
    """Build comprehensive financial data from all extracted statements."""
    stmts = db.query(FinancialStatement).order_by(
        FinancialStatement.entity_type, FinancialStatement.fiscal_year
    ).all()

    if not stmts:
        return ""

    lines = ["\n=== FINANCIAL DATA (Extracted from Official Documents) ==="]

    for entity in ["town", "school"]:
        entity_stmts = [s for s in stmts if s.entity_type == entity]
        if not entity_stmts:
            continue

        name = "BOROUGH OF ATLANTIC HIGHLANDS" if entity == "town" else "ATLANTIC HIGHLANDS SCHOOL DISTRICT (AHES)"
        lines.append(f"\n--- {name} ---")

        for s in sorted(entity_stmts, key=lambda x: x.fiscal_year):
            parts = [f"FY {s.fiscal_year}:"]
            if s.total_revenue and isinstance(s.total_revenue, (int, float)) and s.total_revenue > 100:
                parts.append(f"Revenue=${s.total_revenue:,.0f}")
            if s.total_expenditures and isinstance(s.total_expenditures, (int, float)) and s.total_expenditures > 100:
                parts.append(f"Expenditures=${s.total_expenditures:,.0f}")
            if s.fund_balance and isinstance(s.fund_balance, (int, float)):
                parts.append(f"Fund Balance=${s.fund_balance:,.0f}")
            if s.total_debt and isinstance(s.total_debt, (int, float)):
                parts.append(f"Debt=${s.total_debt:,.0f}")
            if s.total_revenue and s.total_expenditures and isinstance(s.total_revenue, (int, float)):
                surplus = s.total_revenue - s.total_expenditures
                parts.append(f"Surplus/Deficit=${surplus:,.0f}")

            lines.append(", ".join(parts))

            # Add key line items from raw extraction
            if s.raw_extraction and isinstance(s.raw_extraction, dict):
                raw = s.raw_extraction
                details = []
                for section_key in ["current_fund", "general_fund", "income_statement"]:
                    section = raw.get(section_key, {})
                    if not isinstance(section, dict):
                        continue
                    for key, label in [
                        ("property_tax_revenue", "Property Tax"),
                        ("property_tax_levy", "Property Tax Levy"),
                        ("state_aid", "State Aid"),
                        ("salaries_wages", "Salaries"),
                        ("debt_service", "Debt Service"),
                        ("county_taxes", "County Taxes"),
                        ("school_taxes", "School Taxes"),
                        ("instruction_expenditures", "Instruction"),
                        ("transportation", "Transportation"),
                    ]:
                        val = section.get(key)
                        if val and isinstance(val, (int, float)) and val > 100:
                            details.append(f"{label}=${val:,.0f}")

                if details:
                    lines.append(f"  Breakdown: {', '.join(details[:8])}")

    return "\n".join(lines)


def _get_document_text(db: Session, document_id: str) -> str:
    """Get full text of a specific document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return ""

    if doc.extracted_text and len(doc.extracted_text) > 100:
        return f"\n=== ATTACHED DOCUMENT: {doc.filename} (FY: {doc.fiscal_year or '?'}) ===\n{doc.extracted_text[:50000]}"

    # Fallback to S3
    try:
        s3 = S3Service()
        content = s3.download_file(doc.s3_key)
        import pymupdf
        pdf = pymupdf.open(stream=content, filetype="pdf")
        pages = [pdf[p].get_text() for p in range(min(30, pdf.page_count)) if pdf[p].get_text().strip()]
        pdf.close()
        return f"\n=== ATTACHED DOCUMENT: {doc.filename} ===\n" + "\n".join(pages)[:50000]
    except Exception:
        return f"\n=== ATTACHED DOCUMENT: {doc.filename} (text extraction failed) ==="


def _search_relevant_docs(db: Session, query: str) -> str:
    """Search document index for relevant context based on user query."""
    terms = query.split()[:6]
    tsquery = " | ".join(t for t in terms if len(t) > 2)
    if not tsquery:
        return ""

    try:
        results = db.execute(sql_text("""
            SELECT filename, fiscal_year, doc_type, category, notes,
                   substring(extracted_text from 1 for 3000) as text_preview,
                   ts_rank(search_vector, to_tsquery('english', :q)) as score
            FROM documents
            WHERE search_vector @@ to_tsquery('english', :q)
            ORDER BY score DESC LIMIT 5
        """), {"q": tsquery}).fetchall()

        if not results:
            return ""

        context = ["\n=== RELEVANT DOCUMENTS (matched from search) ==="]
        for r in results:
            context.append(f"\n--- [source: {r.filename}] [{r.category}, {r.doc_type}, FY {r.fiscal_year}] ---")
            if r.notes:
                context.append(f"Summary: {r.notes}")
            if r.text_preview:
                context.append(r.text_preview[:2000])

        return "\n".join(context)[:30000]
    except Exception as e:
        logger.warning(f"FTS search failed: {e}")
        return ""


def _get_document_awareness(db: Session) -> str:
    """Get AI summaries of recent/important documents for general awareness."""
    docs = db.query(Document).filter(
        Document.notes.isnot(None),
        Document.doc_type.in_(["resolution", "ordinance", "budget", "audit", "minutes"]),
    ).order_by(desc(Document.fiscal_year)).limit(30).all()

    if not docs:
        return ""

    lines = ["\n=== RECENT DOCUMENT SUMMARIES (for background awareness) ==="]
    for d in docs:
        lines.append(f"[{d.doc_type}] {d.filename}: {d.notes[:200]}")

    return "\n".join(lines)[:10000]


# ─── Chat History ─────────────────────────────────────────────────────

@router.get("/history")
def get_chat_history(
    session_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get chat history for a session."""
    rows = db.execute(sql_text(
        "SELECT role, content, metadata, created_at FROM chat_history WHERE session_id = :sid ORDER BY created_at"
    ), {"sid": session_id}).fetchall()

    return {
        "session_id": session_id,
        "messages": [
            {"role": r.role, "content": r.content, "metadata": r.metadata, "timestamp": r.created_at.isoformat()}
            for r in rows
        ],
    }


@router.get("/sessions")
def list_chat_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all chat sessions with last message preview."""
    rows = db.execute(sql_text("""
        SELECT session_id, scope_type, scope_id,
               count(*) as message_count,
               max(created_at) as last_activity,
               (SELECT content FROM chat_history ch2 WHERE ch2.session_id = ch.session_id AND ch2.role = 'user' ORDER BY created_at DESC LIMIT 1) as last_query
        FROM chat_history ch
        GROUP BY session_id, scope_type, scope_id
        ORDER BY max(created_at) DESC
        LIMIT 20
    """)).fetchall()

    return [
        {
            "session_id": r.session_id,
            "scope_type": r.scope_type,
            "scope_id": r.scope_id,
            "message_count": r.message_count,
            "last_activity": r.last_activity.isoformat() if r.last_activity else None,
            "last_query": r.last_query[:100] if r.last_query else None,
        }
        for r in rows
    ]


def _save_message(db: Session, session_id: str, role: str, content: str, scope_type: str = "all", scope_id: str = None):
    """Save a chat message to history."""
    db.execute(sql_text(
        "INSERT INTO chat_history (id, session_id, scope_type, scope_id, role, content) VALUES (:id, :sid, :st, :si, :role, :content)"
    ), {"id": str(uuid.uuid4()), "sid": session_id, "st": scope_type, "si": scope_id, "role": role, "content": content})
    db.commit()


# ─── Streaming Chat ──────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream a chat response with full AH knowledge context."""
    session_id = req.session_id or str(uuid.uuid4())

    # Build system prompt with full context
    system_prompt = _build_system_prompt(db, req.document_id, req.query)

    # Load chat history for this session
    history = []
    if req.session_id:
        rows = db.execute(sql_text(
            "SELECT role, content FROM chat_history WHERE session_id = :sid ORDER BY created_at"
        ), {"sid": session_id}).fetchall()
        for r in rows:
            history.append({"role": r.role, "content": r.content})

    # Save user message
    _save_message(db, session_id, "user", req.query, req.scope_type, req.scope_id)

    if req.model == "gemini" and GEMINI_API_KEY:
        return StreamingResponse(
            _stream_gemini(system_prompt, req.query, history, db, session_id, req.scope_type, req.scope_id),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id},
        )
    elif ANTHROPIC_API_KEY:
        return StreamingResponse(
            _stream_claude(system_prompt, req.query, history, db, session_id, req.scope_type, req.scope_id),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id},
        )
    else:
        async def no_key():
            msg = "Configure ANTHROPIC_API_KEY or GEMINI_API_KEY in .env to enable AI chat."
            _save_message(db, session_id, "assistant", msg, req.scope_type, req.scope_id)
            yield f"data: {json.dumps({'type': 'delta', 'content': msg, 'session_id': session_id})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        return StreamingResponse(no_key(), media_type="text/event-stream", headers={"X-Session-Id": session_id})


async def _stream_claude(system_prompt, query, history, db, session_id, scope_type, scope_id):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = history[-10:]  # Last 10 messages for context
    messages.append({"role": "user", "content": query})

    full_response = ""
    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514", max_tokens=4096,
            system=system_prompt, messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield f"data: {json.dumps({'type': 'delta', 'content': text, 'session_id': session_id})}\n\n"

        _save_message(db, session_id, "assistant", full_response, scope_type, scope_id)
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
    except Exception as e:
        logger.error(f"Claude error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


async def _stream_gemini(system_prompt, query, history, db, session_id, scope_type, scope_id):
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Build conversation with history
        conv_parts = [system_prompt + "\n\n"]
        for msg in history[-10:]:
            prefix = "User: " if msg["role"] == "user" else "Assistant: "
            conv_parts.append(f"{prefix}{msg['content']}\n\n")
        conv_parts.append(f"User: {query}")

        full_prompt = "".join(conv_parts)
        config = types.GenerateContentConfig(temperature=0.3, max_output_tokens=8192)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash", contents=full_prompt, config=config,
            ),
        )

        full_response = ""
        if response and response.text:
            text = response.text
            chunk_size = 25
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                full_response += chunk
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk, 'session_id': session_id})}\n\n"
                await asyncio.sleep(0.01)

        _save_message(db, session_id, "assistant", full_response, scope_type, scope_id)
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
