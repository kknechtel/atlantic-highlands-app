"""AI Chat routes - context-aware chat that pulls from documents and financial data."""
import logging
import json
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    document_id: str | None = None
    project_id: str | None = None
    model: str = "gemini"


def _build_financial_context(db: Session) -> str:
    """Build a rich context string from all extracted financial data."""
    statements = db.query(FinancialStatement).order_by(
        FinancialStatement.entity_type, FinancialStatement.fiscal_year
    ).all()

    if not statements:
        return ""

    lines = ["=== EXTRACTED FINANCIAL DATA ===\n"]

    for entity in ["town", "school"]:
        entity_stmts = [s for s in statements if s.entity_type == entity]
        if not entity_stmts:
            continue

        name = "Borough of Atlantic Highlands" if entity == "town" else "Atlantic Highlands School District (AHES)"
        lines.append(f"\n--- {name} ---")

        for s in sorted(entity_stmts, key=lambda x: x.fiscal_year):
            rev = f"${s.total_revenue:,.0f}" if s.total_revenue else "N/A"
            exp = f"${s.total_expenditures:,.0f}" if s.total_expenditures else "N/A"
            fb = f"${s.fund_balance:,.0f}" if s.fund_balance else "N/A"
            debt = f"${s.total_debt:,.0f}" if s.total_debt else "N/A"
            surplus = ""
            if s.total_revenue and s.total_expenditures:
                diff = s.total_revenue - s.total_expenditures
                surplus = f", Surplus/Deficit: ${diff:,.0f}"

            lines.append(f"FY {s.fiscal_year}: Revenue={rev}, Expenditures={exp}, Fund Balance={fb}, Debt={debt}{surplus}")

            # Include detailed line items from raw extraction
            if s.raw_extraction:
                raw = s.raw_extraction if isinstance(s.raw_extraction, dict) else {}
                inc = raw.get("income_statement", {})
                bs_data = raw.get("balance_sheet", {})
                tax = raw.get("tax_info", {})
                budget = raw.get("budget_comparison", {})

                details = []
                for key, label in [
                    ("property_tax_revenue", "Property Tax"),
                    ("state_aid", "State Aid"),
                    ("salaries_wages", "Salaries & Wages"),
                    ("debt_service", "Debt Service"),
                    ("county_taxes", "County Taxes"),
                    ("school_taxes", "School Taxes"),
                ]:
                    val = inc.get(key)
                    if val:
                        details.append(f"{label}: ${val:,.0f}")

                if tax.get("tax_rate_per_100"):
                    details.append(f"Tax Rate: ${tax['tax_rate_per_100']}/100")
                if tax.get("assessed_valuation"):
                    details.append(f"Assessed Value: ${tax['assessed_valuation']:,.0f}")
                if bs_data.get("cash_and_investments"):
                    details.append(f"Cash: ${bs_data['cash_and_investments']:,.0f}")
                if budget.get("budgeted_expenditures") and budget.get("actual_expenditures"):
                    var = budget["actual_expenditures"] - budget["budgeted_expenditures"]
                    details.append(f"Budget Variance: ${var:,.0f}")

                if details:
                    lines.append(f"  Details: {', '.join(details)}")

    return "\n".join(lines)


def _build_document_context(db: Session, document_id: str = None, query: str = "") -> str:
    """Build context from specific document, or search for relevant docs."""
    from sqlalchemy import text as sql_text

    if document_id:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc and doc.extracted_text:
            return f"=== DOCUMENT: {doc.filename} (FY: {doc.fiscal_year or 'unknown'}) ===\n{doc.extracted_text[:50000]}"
        elif doc:
            # Fallback to S3 extraction
            s3 = S3Service()
            try:
                content = s3.download_file(doc.s3_key)
                import pymupdf
                pdf = pymupdf.open(stream=content, filetype="pdf")
                pages = [pdf[i].get_text() for i in range(min(30, pdf.page_count)) if pdf[i].get_text().strip()]
                pdf.close()
                return f"=== DOCUMENT: {doc.filename} ===\n" + "\n\n".join(pages)[:50000]
            except Exception as e:
                return f"Document: {doc.filename} (could not extract text: {e})"

    # Search for relevant documents using FTS
    if query:
        terms = query.split()[:5]
        tsquery = " | ".join(terms)  # OR search for broader results
        try:
            results = db.execute(sql_text("""
                SELECT id, filename, fiscal_year, doc_type, category,
                       substring(extracted_text from 1 for 5000) as text_preview,
                       ts_rank(search_vector, to_tsquery('english', :q)) as score
                FROM documents
                WHERE search_vector @@ to_tsquery('english', :q)
                ORDER BY score DESC LIMIT 3
            """), {"q": tsquery}).fetchall()

            if results:
                context = ["=== RELEVANT DOCUMENTS (from search) ==="]
                for r in results:
                    context.append(f"\n--- {r.filename} [{r.category}, {r.doc_type}, FY {r.fiscal_year}] ---")
                    context.append(r.text_preview or "")
                return "\n".join(context)[:40000]
        except Exception as e:
            logger.warning(f"FTS search failed: {e}")

    # Fallback: document inventory
    docs = db.query(Document).filter(
        Document.doc_type.in_(["budget", "audit", "financial_statement"])
    ).order_by(Document.fiscal_year.desc()).limit(50).all()

    inventory = ["=== AVAILABLE FINANCIAL DOCUMENTS ==="]
    for d in docs:
        inventory.append(f"- {d.filename} [{d.category}, {d.doc_type}, FY {d.fiscal_year or '?'}]")
    return "\n".join(inventory)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream a chat response with full financial context."""

    # Build rich context
    financial_context = _build_financial_context(db)
    document_context = _build_document_context(db, req.document_id, req.query)

    system_prompt = f"""You are a financial analyst AI for Atlantic Highlands, New Jersey.
You have access to REAL financial data extracted from official municipal and school district documents.
ALWAYS use the actual data provided below to answer questions. NEVER say you don't have data if it's in the context below.
Cite specific figures with dollar amounts. Reference the fiscal year and source document.
When comparing years, calculate actual differences and percentages.
If asked about spending per student, use expenditure data and note that enrollment data may need to be sourced separately.

{financial_context}

{document_context}

When referencing documents, use this format: [source: exact_filename.pdf]
The frontend will turn these into clickable links.
Be specific with numbers. Show calculations. Provide insights and analysis.
Always cite which document or fiscal year your data comes from."""

    if req.model == "gemini" and GEMINI_API_KEY:
        return StreamingResponse(
            _stream_gemini(system_prompt, req.query),
            media_type="text/event-stream",
        )
    elif ANTHROPIC_API_KEY:
        return StreamingResponse(
            _stream_claude(system_prompt, req.query),
            media_type="text/event-stream",
        )
    else:
        async def no_key():
            yield f"data: {json.dumps({'type': 'delta', 'content': 'Configure ANTHROPIC_API_KEY or GEMINI_API_KEY in .env'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(no_key(), media_type="text/event-stream")


async def _stream_claude(system_prompt: str, query: str):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514", max_tokens=4096,
            system=system_prompt, messages=[{"role": "user", "content": query}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'delta', 'content': text})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.error(f"Claude error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


async def _stream_gemini(system_prompt: str, query: str):
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        full_prompt = f"{system_prompt}\n\nUser question: {query}"
        config = types.GenerateContentConfig(temperature=0.3, max_output_tokens=8192)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash", contents=full_prompt, config=config,
            ),
        )

        if response and response.text:
            text = response.text
            chunk_size = 30
            for i in range(0, len(text), chunk_size):
                yield f"data: {json.dumps({'type': 'delta', 'content': text[i:i+chunk_size]})}\n\n"
                await asyncio.sleep(0.01)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
