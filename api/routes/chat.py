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
    web_search: bool = False


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list


# ─── Knowledge Base Builder ───────────────────────────────────────────

def _build_system_prompt(db: Session, document_id: str = None, query: str = "") -> str:
    """Build a comprehensive system prompt with all AH knowledge."""

    # 1. Core identity and background knowledge
    background = """You are the Atlantic Highlands AI Expert - a deeply knowledgeable municipal analyst specializing in the Borough of Atlantic Highlands, NJ and its school districts.

BOROUGH FACTS:
- Atlantic Highlands is a borough in Monmouth County, NJ (pop ~4,318, 2025 est)
- Governed by a Borough form (weak mayor / strong council) under New Jersey's Faulkner Act
- Mayor: Lori Hohenleitner (D, term ends Dec 2027). 6-member council, staggered 3-year terms
- Borough Hall: 100 First Avenue. ZIP: 07716. Bayshore Region on Raritan Bay
- Notable: Mount Mitchill (highest point on eastern seaboard south of Maine), SeaStreak ferry to Manhattan
- Municipal harbor: 715 watercraft capacity, largest on East Coast
- Key boards: Planning Board, Zoning Board, Environmental Commission, Historic Preservation Commission, Harbor Commission
- Volunteer Fire Department: Hook & Ladder Co. No. 1, AH Hose Co. No. 1, Robert B. Mantell Hose Co. No. 2

SCHOOL DISTRICT (major restructuring 2022-2024):
- Pre-July 2024: "Tri-District" — Atlantic Highlands School District (AHES, PreK-6), Highlands School District (PreK-6), Henry Hudson Regional High School (7-12). Shared superintendent since June 2021.
- January 2022: Governor Murphy signed S-3488 providing regionalization incentives. Kean University feasibility study estimated $270K one-time savings.
- September 2023: Voters in both AH and Highlands approved referendum to consolidate all three into single PK-12 district.
- July 1, 2024: New **Henry Hudson Regional School District** became operational.
- Current schools: AHES (PreK-6, 282 students), Highlands Elementary (PreK-6, 153), HHRS (7-12, 278). Total ~725 students, 8.4:1 ratio.
- Superintendent: Dr. Tara Beams. Business Administrator: Janet Sherlock. Board: 9 members (5 Highlands, 4 AH).
- Sea Bright dispute (2024-present): Sea Bright seeking to leave Oceanport/Shore Regional and join Henry Hudson. NJ Supreme Court ruled Sea Bright has standing. Litigation ongoing.

KEY HISTORICAL EVENTS IN DOCUMENTS:
- 2012-2018: Superstorm Sandy — AH received $17.2M in federal aid (largest of any NJ municipality). FEMA STEP program, RREM grants.
- 2022-2024: School regionalization — S-3488 legislation, Kean study, voter referendum, district consolidation.
- 2024 election: Allegations of $500K financial wrongdoing investigated and found unfounded (Two River Times).
- Waterfront development: Brant Point project (16 upscale homes, starting $2.8M).
- 2024 tax rate: 1.665 general rate. Municipal rate decreased 2020-2024 while property values rose.

DOCUMENT LIBRARY:
You have access to 860+ indexed documents (2004-present) including budgets, audits, financial statements, council meeting minutes/agendas, ordinances, resolutions, school board minutes, CAFRs, legal documents, and more.

ALWAYS cite specific documents and figures. Use [source: filename] format for citations.
When discussing finances, show actual dollar amounts, percentages, and year-over-year changes.
Be specific, authoritative, and analytical. Present information in well-structured markdown with headers, bullet points, and tables where appropriate. You ARE the expert on this town."""

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

    chart_example = '{"type":"bar","data":{"labels":["FY2022","FY2023","FY2024"],"datasets":[{"label":"Revenue","data":[100,200,300],"backgroundColor":"#385854"},{"label":"Expenses","data":[90,180,280],"backgroundColor":"#ef4444"}]},"options":{"responsive":true}}'

    instructions = f"""INSTRUCTIONS:
- ALWAYS extract and present actual data from the documents above — dollar amounts, dates, names, specifics
- NEVER tell the user to "consult" or "review" a document — YOU have the document text, so read it and answer
- If a document is referenced, extract the relevant data from it and present it directly
- Cite sources with [source: filename.pdf] format — these become clickable links for the user
- Calculate year-over-year changes, percentages, and trends when comparing periods
- Be analytical and insightful, not just descriptive
- Reference specific resolutions, ordinances, and meeting dates when relevant
- Present financial data in markdown tables when comparing multiple periods
- When presenting numerical data with 3+ data points, include a chart using this format:
  ```chart
  {chart_example}
  ```
  Supported chart types: bar, line, pie. Use brand color #385854 for primary data.
- For tabular data, always use proper markdown tables with headers
- If you truly cannot find specific data in the provided context, say so clearly but suggest which document types might contain it"""

    return f"""{background}

{financial_context}

{doc_context}

{recent_awareness}

{instructions}"""


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
                   substring(extracted_text from 1 for 8000) as text_preview,
                   ts_rank(search_vector, to_tsquery('english', :q)) as score
            FROM documents
            WHERE search_vector @@ to_tsquery('english', :q)
            ORDER BY score DESC LIMIT 10
        """), {"q": tsquery}).fetchall()

        if not results:
            return ""

        context = ["\n=== RELEVANT DOCUMENTS (matched from search) ==="]
        for r in results:
            context.append(f"\n--- [source: {r.filename}] [{r.category}, {r.doc_type}, FY {r.fiscal_year}] ---")
            if r.notes:
                context.append(f"Summary: {r.notes}")
            if r.text_preview:
                context.append(r.text_preview[:6000])

        return "\n".join(context)[:60000]
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

    # When web search is enabled, add explicit instruction
    if req.web_search:
        system_prompt += """

WEB SEARCH ENABLED: The user has enabled web search. You MUST use the web_search tool for EVERY query to supplement your document knowledge with current information from the internet. Always search first, then combine web results with your document knowledge to give the most complete answer. Do not skip web search — the user explicitly requested it."""

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

    if req.model == "gemini" and GEMINI_API_KEY and not req.web_search:
        return StreamingResponse(
            _stream_gemini(system_prompt, req.query, history, db, session_id, req.scope_type, req.scope_id),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id},
        )
    elif ANTHROPIC_API_KEY:
        return StreamingResponse(
            _stream_claude(system_prompt, req.query, history, db, session_id, req.scope_type, req.scope_id, req.web_search),
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


def _web_search(query: str, max_results: int = 5) -> str:
    """Execute a web search using DuckDuckGo and return formatted results."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No web results found."
        lines = []
        for r in results:
            lines.append(f"**{r.get('title', '')}**")
            lines.append(f"{r.get('body', '')}")
            lines.append(f"Source: {r.get('href', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return f"Web search failed: {e}"


WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Search the web for current information about Atlantic Highlands, NJ municipal affairs, school district news, property taxes, government decisions, or any topic the user asks about that may need up-to-date information beyond the indexed documents. Use this when the user asks about recent events, current officials, news, or anything that may have changed after the documents were indexed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find relevant web information"
            }
        },
        "required": ["query"]
    }
}


async def _stream_claude(system_prompt, query, history, db, session_id, scope_type, scope_id, web_search=False):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = history[-10:]
    messages.append({"role": "user", "content": query})

    tools = [WEB_SEARCH_TOOL] if web_search else []

    full_response = ""
    try:
        # First call - may request tool use if web_search enabled
        create_kwargs = dict(
            model="claude-sonnet-4-20250514", max_tokens=4096,
            system=system_prompt, messages=messages,
        )
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = {"type": "any"}  # Force tool use on first call when web search enabled
        logger.info(f"Claude call: web_search={web_search}, tools={len(tools)}, stop_reason will follow...")
        response = client.messages.create(**create_kwargs)
        logger.info(f"Claude response: stop_reason={response.stop_reason}, content_types={[b.type for b in response.content]}")

        # Handle tool use loop
        while response.stop_reason == "tool_use":
            # Find the tool use block
            tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
            if not tool_use_block:
                break

            # Stream any text before tool use
            for block in response.content:
                if block.type == "text" and block.text:
                    full_response += block.text
                    yield f"data: {json.dumps({'type': 'delta', 'content': block.text, 'session_id': session_id})}\n\n"

            # Signal searching
            search_msg = "\n\n*Searching the web...*\n\n"
            yield f"data: {json.dumps({'type': 'delta', 'content': search_msg, 'session_id': session_id})}\n\n"
            full_response += search_msg

            # Execute web search
            search_query = tool_use_block.input.get("query", query)
            logger.info(f"Claude requesting web search: {search_query}")

            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(None, lambda: _web_search(search_query))

            # Send tool result back to Claude
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": search_results,
                }],
            })

            # Get next response - switch to auto so Claude can give final text answer
            follow_kwargs = {**create_kwargs, "messages": messages, "tool_choice": {"type": "auto"}}
            response = client.messages.create(**follow_kwargs)

        # Stream the final text response
        for block in response.content:
            if block.type == "text" and block.text:
                chunk_size = 30
                text = block.text
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i + chunk_size]
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'delta', 'content': chunk, 'session_id': session_id})}\n\n"
                    await asyncio.sleep(0.01)

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
