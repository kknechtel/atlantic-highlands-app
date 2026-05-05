"""
Atlantic Highlands AI Chat — Claude Sonnet 4.6 with hybrid pgvector RAG,
extended thinking, agentic tool loop, and SSE streaming.

Replaces the prior single-shot tsvector-only retrieval. Claude can now
iteratively call:

  - search_documents(query, fiscal_year?, category?)
  - search_chunks(query, fiscal_year?, category?)        ← passage-level
  - read_document(document_id, max_chars?)
  - get_financial_summary(entity?, fiscal_year?)
  - list_recent_documents(doc_type?)
  - web_search(query)                                    ← when enabled

Three modes (request body):
  - report_mode:   structured executive-style markdown report
  - deep_thinking: extended thinking + 60K thinking budget + opus-4-7
  - (default)      sonnet-4-6, no thinking, fast streaming

Routes:
  POST /api/chat/stream             — SSE chat (text + thinking + tool_use events)
  GET  /api/chat/history?session_id — full message thread
  GET  /api/chat/sessions           — recent sessions
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, text as sql_text
from sqlalchemy.orm import Session

from auth import get_current_user
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY
from database import SessionLocal, get_db
from models.financial import FinancialStatement
from models.user import User
from services.rag_search import (
    get_document_excerpt,
    list_recent_documents,
    search_chunks,
    search_documents,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Models ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    document_id: Optional[str] = None
    scope_type: str = "all"
    scope_id: Optional[str] = None
    model: str = "claude"
    web_search: bool = False
    deep_thinking: bool = False
    report_mode: bool = False


# ─── System prompts ──────────────────────────────────────────────────────────

BACKGROUND = """You are the Atlantic Highlands AI Expert — a deeply knowledgeable municipal analyst specializing in the Borough of Atlantic Highlands, NJ and its school districts.

BOROUGH FACTS:
- Atlantic Highlands is a borough in Monmouth County, NJ (pop ~4,318, 2025 est)
- Borough form (weak mayor / strong council) under New Jersey's Faulkner Act
- Mayor: Lori Hohenleitner (D, term ends Dec 2027). 6-member council, staggered 3-year terms
- Borough Hall: 100 First Avenue. ZIP: 07716. Bayshore Region on Raritan Bay
- Notable: Mount Mitchill (highest point on eastern seaboard south of Maine), SeaStreak ferry to Manhattan
- Municipal harbor: 715 watercraft capacity, largest on East Coast
- Key boards: Planning, Zoning, Environmental Commission, Historic Preservation, Harbor Commission
- Volunteer Fire: Hook & Ladder Co. No. 1, AH Hose Co. No. 1, Robert B. Mantell Hose Co. No. 2

SCHOOL DISTRICT (major restructuring 2022-2024):
- Pre-July 2024 "Tri-District": AH School District (AHES, PreK-6), Highlands SD (PreK-6), Henry Hudson Regional HS (7-12). Shared superintendent since June 2021.
- January 2022: Governor Murphy signed S-3488. Kean University feasibility estimated $270K one-time savings.
- September 2023: AH and Highlands voters approved consolidation referendum.
- July 1, 2024: New Henry Hudson Regional School District operational (PreK-12).
- Schools: AHES (282), Highlands Elementary (153), HHRS (278). ~725 students total, 8.4:1 ratio.
- Superintendent: Dr. Tara Beams. Business Admin: Janet Sherlock. 9-member board (5 Highlands, 4 AH).
- Sea Bright dispute (2024-present): Sea Bright seeking to leave Oceanport/Shore Regional and join Henry Hudson. NJ Supreme Court ruled Sea Bright has standing.

KEY HISTORICAL EVENTS IN DOCUMENTS:
- 2012-2018: Superstorm Sandy — AH received $17.2M in federal aid (largest of any NJ municipality). FEMA STEP, RREM grants.
- 2022-2024: School regionalization — S-3488, Kean study, voter referendum, district consolidation.
- 2024 election: $500K wrongdoing allegations investigated and found unfounded (Two River Times).
- Waterfront development: Brant Point project (16 upscale homes, starting $2.8M).
- 2024 tax rate: 1.665 general rate. Municipal rate decreased 2020-2024 while property values rose.

DOCUMENT LIBRARY: 860+ indexed documents (2004-present): budgets, audits, financial statements, council minutes/agendas, ordinances, resolutions, school board minutes, CAFRs, legal documents."""


WORKING_INSTRUCTIONS = """## How to answer

You have powerful tools. USE THEM. Do not say "I cannot find" without calling at least two tools first.

For every non-trivial question:
1. Call `search_chunks` with the user's question (verbatim or rephrased) — this returns the most relevant passages from across the entire document corpus.
2. If the chunks point to a document worth reading in full, call `read_document` with that document's ID.
3. If the question concerns budgets, taxes, debt, or fund balances:
   - For HEADLINE figures, call `get_financial_summary`.
   - For ANALYSIS (revenue composition, expenditure breakdown, fund-balance health, debt position, red flags), call `get_drill_results` for the relevant statement_id. The drill is far richer than the summary — use it.
   - For SPECIFIC line items ("show me transportation costs", "salaries vs benefits"), call `get_line_items` with section/fund/function_code/object_code filters.
   - To surface FINANCIAL CONCERNS proactively, call `get_anomalies` — pre-computed rule-based flags.
4. For VENDOR / CONTRACT questions, call `search_contracts` and/or `get_vendor_summary`.
5. NJ-SPECIFIC AWARENESS:
   - NJ schools use GAAP/GASB; NJ municipalities use REGULATORY BASIS — they are NOT directly comparable.
   - Atlantic Highlands borough = calendar year; Henry Hudson Regional School District = July-June school year.
   - HHRSD is a 7/1/2024 consolidation of three predecessor districts (AHSD, HSD, HHRS-HS). Pre-7/1/2024 figures are from the predecessors and CANNOT be summed naively.
   - NJ school surplus is statutorily capped at greater of 2% of expenditures or $250K (N.J.S.A. 18A:7F-7) — do NOT apply GFOA's 16% benchmark to schools.
   - For FY26+, CMPTRA is FULLY consolidated into ETR for municipalities — expect $0 CMPTRA, not a decline.
6. Cite every fact with `[source: filename.pdf]` — these become clickable links.

## Output style

- ALWAYS extract concrete numbers, dates, names from the documents. Never tell the user to "consult the document" — you have its text.
- Show year-over-year deltas, percentages, and trends when comparing periods.
- When presenting numerical data with 3+ data points, embed a chart in this exact format:

  ```chart
  {"type":"bar","data":{"labels":["FY2022","FY2023","FY2024"],"datasets":[{"label":"Revenue","data":[100,200,300],"backgroundColor":"#385854"}]},"options":{"responsive":true}}
  ```

  Supported types: bar, line, pie. Use `#385854` (AH brand) for the primary series.
- For tabular data, use proper markdown tables.
- Reference specific resolutions, ordinances, meeting dates.
- If you genuinely cannot find something after searching, say so plainly and suggest which doc types might contain it.
"""


REPORT_MODE_SUFFIX = """

## REPORT MODE ACTIVE

Structure your response as a formal analytical report:

**# Title**
One-line headline that captures the answer.

**## Executive Summary**
3-5 bullets. The decision-relevant takeaways.

**## Findings**
Numbered findings, each with:
- A clear claim
- Supporting numbers/citations
- Year-over-year context where relevant

**## Data**
Tables and charts. Always include at least one chart for any trend.

**## Sources**
Bulleted list of every document cited, in `[source: filename.pdf]` format.

Tone: authoritative, measured, evidence-driven. Lead with findings, not process."""


DEEP_THINKING_SUFFIX = """

## DEEP THINKING ACTIVE

You have extended reasoning enabled. Use it to:
- Cross-reference figures across multiple years/documents
- Detect inconsistencies between budgets and actuals
- Reason about the implications of policy changes
- Build the strongest analytical chain you can before writing the response.

After thinking, the user only sees your final response — make it crisp."""


# ─── Tool definitions ────────────────────────────────────────────────────────

def _tool_defs() -> list[dict]:
    return [
        {
            "name": "search_documents",
            "description": "Search the document library by topic. Returns ranked documents with metadata and AI summaries. Use this when you need to know which documents exist on a topic.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic, question, or keywords."},
                    "fiscal_year": {"type": "string", "description": "Optional FY filter (e.g., '2024')."},
                    "category": {"type": "string", "enum": ["town", "school"], "description": "Optional category filter."},
                    "top_k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_chunks",
            "description": "Search PASSAGES across all documents. Use this for fact-finding ('what did the 2023 budget allocate to roads?'). Returns the most relevant chunks with their source documents. Almost always the right first call.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "fiscal_year": {"type": "string"},
                    "category": {"type": "string", "enum": ["town", "school"]},
                    "top_k": {"type": "integer", "default": 12, "minimum": 1, "maximum": 30},
                },
                "required": ["query"],
            },
        },
        {
            "name": "read_document",
            "description": "Read a specific document by ID. Use this AFTER search_documents/search_chunks identifies a document you need to inspect more carefully.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 12000, "maximum": 30000},
                },
                "required": ["document_id"],
            },
        },
        {
            "name": "get_financial_summary",
            "description": "Get extracted financial figures (revenue, expenditures, fund balance, debt, key line items) for the borough or school district across fiscal years. Use this for any tax/budget/debt question.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "enum": ["town", "school", "all"], "default": "all"},
                    "fiscal_year": {"type": "string", "description": "Optional FY filter."},
                },
            },
        },
        {
            "name": "list_recent_documents",
            "description": "List recent documents, optionally filtered by doc_type (budget, audit, minutes, resolution, ordinance). Use for browsing-style questions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doc_type": {"type": "string"},
                    "limit": {"type": "integer", "default": 20, "maximum": 50},
                },
            },
        },
        {
            "name": "get_drill_results",
            "description": "Get the deep-drill analysis results for a specific financial statement: revenue composition, expenditure breakdown by function/object, debt analysis, fund-balance analysis, and an executive synthesis with red flags. Use this when the user asks for ANALYSIS rather than raw figures.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "statement_id": {"type": "string"},
                    "drill_type": {"type": "string", "enum": ["revenue", "expenditure", "debt", "fund_balance", "synthesis", "all"], "default": "all"},
                },
                "required": ["statement_id"],
            },
        },
        {
            "name": "get_anomalies",
            "description": "Get rule-based anomaly flags (operating deficit, fund balance over/under benchmark, large YoY swings, budget variances, debt/revenue ratio, salary concentration) for a statement, or across all statements if no ID given. Each flag has a severity (info|warn|high).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "statement_id": {"type": "string"},
                    "entity_type": {"type": "string", "enum": ["town", "school"]},
                    "min_severity": {"type": "string", "enum": ["info", "warn", "high"], "default": "info"},
                },
            },
        },
        {
            "name": "get_line_items",
            "description": "Fetch detailed extracted line items for a statement, optionally filtered by section (Revenue/Expenditures/Debt Service/...) or by NJ school account-code segments (program/function/object). Use this when the user wants to drill into a specific spending category like 'show me transportation costs' or 'how much was spent on salaries vs benefits'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "statement_id": {"type": "string"},
                    "section": {"type": "string"},
                    "fund": {"type": "string", "enum": ["general", "capital", "capital_projects", "debt_service", "special_revenue", "enterprise", "trust"]},
                    "function_code": {"type": "string", "description": "NJ school function code, e.g. '230' for Basic Skills"},
                    "object_code": {"type": "string", "description": "NJ object code, e.g. '100' for Salaries"},
                    "min_amount": {"type": "number"},
                    "limit": {"type": "integer", "default": 50, "maximum": 200},
                },
                "required": ["statement_id"],
            },
        },
        {
            "name": "search_contracts",
            "description": "Search municipal/school contracts by vendor, fiscal year, minimum amount, or entity. Returns contract title, amount, vendor, awarded date, authorizing resolution.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "entity_type": {"type": "string", "enum": ["town", "school"]},
                    "fiscal_year": {"type": "string"},
                    "min_amount": {"type": "number"},
                    "limit": {"type": "integer", "default": 30, "maximum": 100},
                },
            },
        },
        {
            "name": "get_vendor_summary",
            "description": "Summarize all activity for a single vendor — total contracts, total payments, fiscal years active, contract types. Use for 'How much has the borough paid X over the last 5 years?' style questions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "vendor_name": {"type": "string"},
                    "entity_type": {"type": "string", "enum": ["town", "school"]},
                },
                "required": ["vendor_name"],
            },
        },
    ]


def _web_search_tool() -> dict:
    return {
        "name": "web_search",
        "description": "Search the public web. Use for current events, recent appointments, news after the document index was last updated, or topics not covered in the document library.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


# ─── Tool execution ──────────────────────────────────────────────────────────

def _exec_search_documents(db: Session, args: dict) -> dict:
    rows = search_documents(
        db,
        query=args["query"],
        top_k=int(args.get("top_k", 8)),
        fiscal_year=args.get("fiscal_year"),
        category=args.get("category"),
    )
    return {
        "count": len(rows),
        "results": [
            {
                "document_id": str(r["id"]),
                "filename": r["filename"],
                "doc_type": r.get("doc_type"),
                "category": r.get("category"),
                "fiscal_year": r.get("fiscal_year"),
                "summary": (r.get("notes") or "")[:600],
                "page_count": r.get("page_count"),
                "score": float(r.get("score") or 0),
            }
            for r in rows
        ],
    }


def _exec_search_chunks(db: Session, args: dict) -> dict:
    rows = search_chunks(
        db,
        query=args["query"],
        top_k=int(args.get("top_k", 12)),
        fiscal_year=args.get("fiscal_year"),
        category=args.get("category"),
    )
    return {
        "count": len(rows),
        "chunks": [
            {
                "document_id": str(r["document_id"]),
                "filename": r["filename"],
                "doc_type": r.get("doc_type"),
                "fiscal_year": r.get("fiscal_year"),
                "page_start": r.get("page_start"),
                "page_end": r.get("page_end"),
                "content": (r.get("content") or "")[:2500],
                "score": float(r.get("score") or 0),
            }
            for r in rows
        ],
    }


def _exec_read_document(db: Session, args: dict) -> dict:
    doc = get_document_excerpt(db, args["document_id"], max_chars=int(args.get("max_chars", 12000)))
    if not doc:
        return {"error": "not_found"}
    return {
        "document_id": str(doc["id"]),
        "filename": doc["filename"],
        "doc_type": doc.get("doc_type"),
        "fiscal_year": doc.get("fiscal_year"),
        "category": doc.get("category"),
        "page_count": doc.get("page_count"),
        "summary": doc.get("notes"),
        "excerpt": doc.get("excerpt") or "",
    }


def _exec_get_financial_summary(db: Session, args: dict) -> dict:
    entity = args.get("entity", "all")
    fy = args.get("fiscal_year")
    q = db.query(FinancialStatement)
    if entity != "all":
        q = q.filter(FinancialStatement.entity_type == entity)
    if fy:
        q = q.filter(FinancialStatement.fiscal_year == fy)
    q = q.order_by(FinancialStatement.entity_type, FinancialStatement.fiscal_year)

    out: list[dict] = []
    for s in q.all():
        d: dict = {
            "entity": s.entity_type,
            "fiscal_year": s.fiscal_year,
            "total_revenue": float(s.total_revenue) if s.total_revenue else None,
            "total_expenditures": float(s.total_expenditures) if s.total_expenditures else None,
            "fund_balance": float(s.fund_balance) if s.fund_balance else None,
            "total_debt": float(s.total_debt) if s.total_debt else None,
        }
        if s.total_revenue and s.total_expenditures:
            d["surplus_deficit"] = float(s.total_revenue) - float(s.total_expenditures)
        # Include selected raw-extraction line items for granularity.
        if isinstance(s.raw_extraction, dict):
            details: dict = {}
            for section in ("current_fund", "general_fund", "income_statement"):
                section_data = s.raw_extraction.get(section)
                if not isinstance(section_data, dict):
                    continue
                for k in ("property_tax_revenue", "property_tax_levy", "state_aid",
                         "salaries_wages", "debt_service", "county_taxes",
                         "school_taxes", "instruction_expenditures", "transportation"):
                    v = section_data.get(k)
                    if isinstance(v, (int, float)) and v > 100:
                        details[k] = float(v)
            if details:
                d["line_items"] = details
        out.append(d)

    return {"count": len(out), "statements": out}


def _exec_list_recent_documents(db: Session, args: dict) -> dict:
    rows = list_recent_documents(db, doc_type=args.get("doc_type"), limit=int(args.get("limit", 20)))
    return {
        "count": len(rows),
        "documents": [
            {
                "document_id": str(r["id"]),
                "filename": r["filename"],
                "doc_type": r.get("doc_type"),
                "category": r.get("category"),
                "fiscal_year": r.get("fiscal_year"),
                "summary": (r.get("notes") or "")[:400],
            }
            for r in rows
        ],
    }


def _exec_get_drill_results(db: Session, args: dict) -> dict:
    from models.financial import FinancialStatement
    sid = args.get("statement_id")
    if not sid:
        return {"error": "statement_id required"}
    stmt = db.query(FinancialStatement).filter(FinancialStatement.id == sid).first()
    if not stmt:
        return {"error": "statement_not_found"}
    drills = stmt.drill_results or {}
    drill_type = args.get("drill_type", "all")
    if drill_type != "all" and drill_type in drills:
        return {
            "statement_id": str(stmt.id), "fiscal_year": stmt.fiscal_year,
            "entity_type": stmt.entity_type, "drill_type": drill_type,
            "result": drills.get(drill_type),
        }
    return {
        "statement_id": str(stmt.id), "fiscal_year": stmt.fiscal_year,
        "entity_type": stmt.entity_type,
        "accounting_basis": stmt.accounting_basis,
        "reconcile_status": stmt.reconcile_status,
        "drills": drills,
    }


def _exec_get_anomalies(db: Session, args: dict) -> dict:
    from models.financial import FinancialStatement
    sid = args.get("statement_id")
    entity_type = args.get("entity_type")
    severity_rank = {"info": 0, "warn": 1, "high": 2}
    min_sev = severity_rank.get(args.get("min_severity", "info"), 0)

    q = db.query(FinancialStatement)
    if sid:
        q = q.filter(FinancialStatement.id == sid)
    if entity_type:
        q = q.filter(FinancialStatement.entity_type == entity_type)

    rows = []
    for s in q.all():
        flags = [f for f in (s.anomaly_flags or [])
                 if severity_rank.get(f.get("severity", "info"), 0) >= min_sev]
        if not flags:
            continue
        rows.append({
            "statement_id": str(s.id), "entity_type": s.entity_type,
            "fiscal_year": s.fiscal_year, "statement_type": s.statement_type,
            "flags": flags,
        })
    return {"count": len(rows), "statements": rows}


def _exec_get_line_items(db: Session, args: dict) -> dict:
    from models.financial import FinancialLineItem
    sid = args.get("statement_id")
    if not sid:
        return {"error": "statement_id required"}
    q = db.query(FinancialLineItem).filter(FinancialLineItem.statement_id == sid)
    if args.get("section"):
        q = q.filter(FinancialLineItem.section == args["section"])
    if args.get("fund"):
        q = q.filter(FinancialLineItem.fund == args["fund"])
    if args.get("function_code"):
        q = q.filter(FinancialLineItem.function_code == args["function_code"])
    if args.get("object_code"):
        q = q.filter(FinancialLineItem.object_code == args["object_code"])
    if args.get("min_amount") is not None:
        q = q.filter(FinancialLineItem.amount >= float(args["min_amount"]))
    items = q.order_by(FinancialLineItem.amount.desc().nullslast()).limit(int(args.get("limit", 50))).all()
    return {
        "count": len(items),
        "items": [
            {
                "line_name": it.line_name, "section": it.section, "subsection": it.subsection,
                "amount": it.amount, "prior_year_amount": it.prior_year_amount,
                "yoy_change_pct": it.yoy_change_pct, "variance_pct": it.variance_pct,
                "fund": it.fund, "account_code": it.account_code,
                "is_total_row": it.is_total_row,
            } for it in items
        ],
    }


def _exec_search_contracts(db: Session, args: dict) -> dict:
    from models.contract import Contract, Vendor
    q = db.query(Contract).join(Vendor)
    if args.get("entity_type"):
        q = q.filter(Contract.entity_type == args["entity_type"])
    if args.get("fiscal_year"):
        q = q.filter(Contract.fiscal_year == args["fiscal_year"])
    if args.get("vendor"):
        norm = " ".join(str(args["vendor"]).lower().split())
        q = q.filter(Vendor.normalized_name.ilike(f"%{norm}%"))
    if args.get("min_amount") is not None:
        q = q.filter(Contract.amount >= float(args["min_amount"]))
    rows = q.order_by(Contract.awarded_date.desc().nullslast()).limit(int(args.get("limit", 30))).all()
    return {
        "count": len(rows),
        "contracts": [
            {
                "id": str(c.id), "vendor_name": c.vendor.name, "title": c.title,
                "amount": c.amount, "fiscal_year": c.fiscal_year,
                "contract_type": c.contract_type, "entity_type": c.entity_type,
                "awarded_date": c.awarded_date.isoformat() if c.awarded_date else None,
                "authorizing_resolution": c.authorizing_resolution,
            } for c in rows
        ],
    }


def _exec_get_vendor_summary(db: Session, args: dict) -> dict:
    from sqlalchemy import func
    from models.contract import Vendor, Contract, Payment
    name = args.get("vendor_name", "")
    norm = " ".join(name.lower().split())
    if not norm:
        return {"error": "vendor_name required"}
    vendor = db.query(Vendor).filter(Vendor.normalized_name.ilike(f"%{norm}%")).first()
    if not vendor:
        return {"error": "vendor_not_found", "searched": name}

    contract_q = db.query(Contract).filter(Contract.vendor_id == vendor.id)
    if args.get("entity_type"):
        contract_q = contract_q.filter(Contract.entity_type == args["entity_type"])
    contracts = contract_q.order_by(Contract.awarded_date.desc().nullslast()).all()

    payment_q = db.query(Payment).filter(Payment.vendor_id == vendor.id)
    if args.get("entity_type"):
        payment_q = payment_q.filter(Payment.entity_type == args["entity_type"])

    total_contracts = sum(float(c.amount or 0) for c in contracts)
    payment_total = float(
        payment_q.with_entities(func.coalesce(func.sum(Payment.amount), 0.0)).scalar() or 0.0
    )

    fy_set = sorted({c.fiscal_year for c in contracts if c.fiscal_year}, reverse=True)
    return {
        "vendor": {"id": str(vendor.id), "name": vendor.name, "category": vendor.category},
        "contract_count": len(contracts),
        "total_contracts_awarded": total_contracts,
        "total_paid": payment_total,
        "fiscal_years_active": fy_set[:10],
        "recent_contracts": [
            {
                "title": c.title, "amount": c.amount, "fiscal_year": c.fiscal_year,
                "awarded_date": c.awarded_date.isoformat() if c.awarded_date else None,
                "contract_type": c.contract_type,
            } for c in contracts[:10]
        ],
    }


def _exec_web_search(args: dict) -> dict:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {"error": "web_search_not_installed"}
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(args["query"], max_results=int(args.get("max_results", 5))))
    except Exception as exc:
        logger.warning("web_search failed: %s", exc)
        return {"error": str(exc)}
    return {
        "count": len(results),
        "results": [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in results
        ],
    }


def _execute_tool(name: str, args: dict, db: Session) -> dict:
    try:
        if name == "search_documents":
            return _exec_search_documents(db, args)
        if name == "search_chunks":
            return _exec_search_chunks(db, args)
        if name == "read_document":
            return _exec_read_document(db, args)
        if name == "get_financial_summary":
            return _exec_get_financial_summary(db, args)
        if name == "list_recent_documents":
            return _exec_list_recent_documents(db, args)
        if name == "get_drill_results":
            return _exec_get_drill_results(db, args)
        if name == "get_anomalies":
            return _exec_get_anomalies(db, args)
        if name == "get_line_items":
            return _exec_get_line_items(db, args)
        if name == "search_contracts":
            return _exec_search_contracts(db, args)
        if name == "get_vendor_summary":
            return _exec_get_vendor_summary(db, args)
        if name == "web_search":
            return _exec_web_search(args)
        return {"error": f"unknown_tool:{name}"}
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return {"error": str(exc)[:300]}


# ─── Chat history ────────────────────────────────────────────────────────────

@router.get("/history")
def get_chat_history(
    session_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.execute(sql_text(
        "SELECT role, content, metadata, created_at FROM chat_history "
        "WHERE session_id = :sid ORDER BY created_at"
    ), {"sid": session_id}).fetchall()
    return {
        "session_id": session_id,
        "messages": [
            {"role": r.role, "content": r.content, "metadata": r.metadata,
             "timestamp": r.created_at.isoformat()}
            for r in rows
        ],
    }


@router.get("/sessions")
def list_chat_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.execute(sql_text("""
        SELECT session_id, scope_type, scope_id,
               count(*) AS message_count,
               max(created_at) AS last_activity,
               (SELECT content FROM chat_history ch2
                WHERE ch2.session_id = ch.session_id AND ch2.role = 'user'
                ORDER BY created_at DESC LIMIT 1) AS last_query
        FROM chat_history ch
        GROUP BY session_id, scope_type, scope_id
        ORDER BY max(created_at) DESC
        LIMIT 30
    """)).fetchall()
    return [
        {
            "session_id": r.session_id,
            "scope_type": r.scope_type,
            "scope_id": r.scope_id,
            "message_count": r.message_count,
            "last_activity": r.last_activity.isoformat() if r.last_activity else None,
            "last_query": (r.last_query[:120] if r.last_query else None),
        }
        for r in rows
    ]


def _save_message(db: Session, session_id: str, role: str, content: str,
                  scope_type: str = "all", scope_id: Optional[str] = None) -> None:
    db.execute(sql_text(
        "INSERT INTO chat_history (id, session_id, scope_type, scope_id, role, content) "
        "VALUES (:id, :sid, :st, :si, :role, :content)"
    ), {"id": str(uuid.uuid4()), "sid": session_id, "st": scope_type,
        "si": scope_id, "role": role, "content": content})
    db.commit()


# ─── Streaming chat ─────────────────────────────────────────────────────────

def _build_system_prompt(req: ChatRequest, doc_context: str) -> str:
    parts = [BACKGROUND, WORKING_INSTRUCTIONS]
    if req.report_mode:
        parts.append(REPORT_MODE_SUFFIX)
    if req.deep_thinking:
        parts.append(DEEP_THINKING_SUFFIX)
    if doc_context:
        parts.append(doc_context)
    return "\n\n".join(parts)


def _attached_doc_context(db: Session, document_id: Optional[str]) -> str:
    """When the user attaches a single document, inline its first 30K chars
    so Claude doesn't need to call `read_document` first."""
    if not document_id:
        return ""
    doc = get_document_excerpt(db, document_id, max_chars=30000)
    if not doc:
        return ""
    return (
        f"## ATTACHED DOCUMENT (inline)\n\n"
        f"**{doc['filename']}** (FY {doc.get('fiscal_year') or '?'}, "
        f"{doc.get('doc_type') or 'document'})\n\n"
        f"{doc.get('excerpt') or ''}\n"
    )


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event with both the event name and JSON payload.
    The frontend listens by event name AND reads the type field (we send both
    so older clients that only parse `data:` frames keep working)."""
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """SSE streaming chat with thinking + tool use + RAG.

    NOTE: this endpoint deliberately does NOT take `db: Session = Depends(get_db)`.
    A request-scoped session held across an SSE stream causes Postgres connection
    leaks: any auto-BEGUN transaction will sit "idle in transaction" if the
    request task is killed mid-stream. Each DB op below opens a short-lived
    SessionLocal() and closes it immediately.
    """
    if not ANTHROPIC_API_KEY and not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="No LLM API key configured")

    session_id = req.session_id or str(uuid.uuid4())

    # Build the prompt with attached-doc context (small, opens/closes its own session).
    setup_db = SessionLocal()
    try:
        doc_context = _attached_doc_context(setup_db, req.document_id)
        history_rows = setup_db.execute(sql_text(
            "SELECT role, content FROM chat_history WHERE session_id = :sid ORDER BY created_at"
        ), {"sid": session_id}).fetchall() if req.session_id else []
        # Save the user message before streaming so it's persisted even if the
        # client disconnects mid-stream.
        setup_db.execute(sql_text(
            "INSERT INTO chat_history (id, session_id, scope_type, scope_id, role, content) "
            "VALUES (:id, :sid, :st, :si, :role, :content)"
        ), {"id": str(uuid.uuid4()), "sid": session_id, "st": req.scope_type,
            "si": req.scope_id, "role": "user", "content": req.query})
        setup_db.commit()
    finally:
        setup_db.close()

    history = [{"role": r.role, "content": r.content} for r in history_rows]
    system_prompt = _build_system_prompt(req, doc_context)

    # If only Gemini is configured, fall through to a simpler streamer (no tools).
    if not ANTHROPIC_API_KEY and GEMINI_API_KEY:
        return StreamingResponse(
            _stream_gemini(system_prompt, req.query, history, session_id, req.scope_type, req.scope_id),
            media_type="text/event-stream",
            headers={"X-Session-Id": session_id, "Cache-Control": "no-cache",
                     "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _stream_claude(req, system_prompt, history, session_id, request),
        media_type="text/event-stream",
        headers={"X-Session-Id": session_id, "Cache-Control": "no-cache",
                 "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


async def _stream_claude(
    req: ChatRequest,
    system_prompt: str,
    history: list[dict],
    session_id: str,
    request: Request,
):
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    tools = _tool_defs()
    if req.web_search:
        tools.append(_web_search_tool())

    messages: list[dict] = list(history[-30:])
    messages.append({"role": "user", "content": req.query})

    accumulated_text = ""
    tool_calls_made = 0

    # Deep thinking pumps the budget/model up; cheap mode keeps sonnet-4-6 fast.
    if req.deep_thinking:
        model = "claude-opus-4-7"
        max_tokens = 32000
        thinking_cfg: Optional[dict] = {"type": "enabled", "budget_tokens": 16000}
    else:
        model = "claude-sonnet-4-6"
        max_tokens = 16000
        thinking_cfg = None

    try:
        yield _sse("session", {"session_id": session_id})

        for iteration in range(8):
            if await request.is_disconnected():
                return

            api_kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "tools": tools,
                "messages": messages,
            }
            if thinking_cfg:
                api_kwargs["thinking"] = thinking_cfg

            iter_text = ""
            thinking_active = False
            last_keepalive = asyncio.get_event_loop().time()

            async with client.messages.stream(**api_kwargs) as stream:
                async for event in stream:
                    if await request.is_disconnected():
                        return

                    et = getattr(event, "type", None)
                    if et == "content_block_start":
                        block = event.content_block
                        bt = getattr(block, "type", None)
                        if bt == "thinking":
                            thinking_active = True
                            yield _sse("thinking", {"status": "started"})
                        elif bt == "text" and thinking_active:
                            thinking_active = False
                            yield _sse("thinking", {"status": "done"})
                        elif bt == "tool_use":
                            yield _sse("tool_use", {
                                "name": getattr(block, "name", ""),
                                "id": getattr(block, "id", ""),
                            })
                    elif et == "content_block_delta":
                        delta = event.delta
                        dt = getattr(delta, "type", None)
                        if dt == "thinking_delta":
                            now = asyncio.get_event_loop().time()
                            if now - last_keepalive >= 20.0:
                                yield ": keepalive\n\n"
                                last_keepalive = now
                        elif dt == "text_delta":
                            chunk = getattr(delta, "text", "")
                            iter_text += chunk
                            accumulated_text += chunk
                            yield _sse("delta", {"content": chunk, "session_id": session_id})

                final_message = await stream.get_final_message()
                if thinking_active:
                    yield _sse("thinking", {"status": "done"})

                stop_reason = final_message.stop_reason
                tool_blocks = [b for b in final_message.content if getattr(b, "type", None) == "tool_use"]

                if not tool_blocks or stop_reason != "tool_use":
                    # Final answer reached.
                    save_db = SessionLocal()
                    try:
                        _save_message(save_db, session_id, "assistant", accumulated_text,
                                      req.scope_type, req.scope_id)
                    finally:
                        save_db.close()
                    yield _sse("done", {"session_id": session_id,
                                        "tool_calls_made": tool_calls_made,
                                        "stop_reason": stop_reason})
                    return

                tool_calls_made += len(tool_blocks)

                # Run tools (each in its own short-lived session, in a thread).
                def run_tool(name: str, args: dict) -> dict:
                    s = SessionLocal()
                    try:
                        return _execute_tool(name, args, s)
                    finally:
                        s.close()

                results = []
                for tb in tool_blocks:
                    yield _sse("tool_call", {
                        "name": tb.name,
                        "input": tb.input,
                    })
                    res = await asyncio.to_thread(run_tool, tb.name, tb.input)
                    summary = _summarize_tool_result(tb.name, res)
                    yield _sse("tool_result", {"name": tb.name, "summary": summary})
                    payload = json.dumps(res)
                    if len(payload) > 30000:
                        payload = payload[:30000] + '"}'
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": payload,
                    })

                messages.append({"role": "assistant", "content": final_message.content})
                messages.append({"role": "user", "content": results})

        # Hit the iteration cap — emit what we have.
        save_db = SessionLocal()
        try:
            _save_message(save_db, session_id, "assistant", accumulated_text,
                          req.scope_type, req.scope_id)
        finally:
            save_db.close()
        yield _sse("done", {"session_id": session_id,
                            "tool_calls_made": tool_calls_made,
                            "stop_reason": "iteration_limit"})

    except anthropic.APIStatusError as exc:
        logger.error("Anthropic API error: %s", exc)
        msg = "AI service error. "
        if getattr(exc, "status_code", 0) == 429:
            msg += "Rate limit reached, try again in a moment."
        elif getattr(exc, "status_code", 0) >= 500:
            msg += "Service temporarily unavailable."
        else:
            msg += getattr(exc, "message", str(exc))
        yield _sse("error", {"content": msg})
    except Exception as exc:
        logger.exception("chat_stream failed")
        yield _sse("error", {"content": str(exc)[:300]})


def _summarize_tool_result(name: str, res: dict) -> str:
    if "error" in res:
        return f"error: {res['error']}"
    if name in ("search_documents", "list_recent_documents"):
        n = res.get("count", 0)
        return f"Found {n} document{'s' if n != 1 else ''}"
    if name == "search_chunks":
        return f"Found {res.get('count', 0)} matching passages"
    if name == "read_document":
        return f"Read {res.get('filename', 'document')}"
    if name == "get_financial_summary":
        return f"Loaded {res.get('count', 0)} financial statement(s)"
    if name == "get_drill_results":
        if "drill_type" in res:
            return f"Loaded {res['drill_type']} drill"
        return f"Loaded full drill ({len(res.get('drills', {}))} sections)"
    if name == "get_anomalies":
        return f"Found anomalies in {res.get('count', 0)} statement(s)"
    if name == "get_line_items":
        return f"Loaded {res.get('count', 0)} line item(s)"
    if name == "search_contracts":
        return f"Found {res.get('count', 0)} contract(s)"
    if name == "get_vendor_summary":
        v = res.get("vendor") or {}
        return f"Loaded vendor: {v.get('name', '?')}"
    if name == "web_search":
        return f"Found {res.get('count', 0)} web results"
    return "ok"


async def _stream_gemini(system_prompt, query, history, session_id, scope_type, scope_id):
    """Fallback streamer when only Gemini is configured. No tool use — single shot."""
    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=GEMINI_API_KEY)
        conv = [system_prompt + "\n\n"]
        for msg in history[-10:]:
            conv.append(("User: " if msg["role"] == "user" else "Assistant: ") + msg["content"] + "\n\n")
        conv.append(f"User: {query}")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents="".join(conv),
                config=gtypes.GenerateContentConfig(temperature=0.3, max_output_tokens=8192),
            ),
        )
        full = response.text or "" if response else ""
        yield _sse("session", {"session_id": session_id})
        for i in range(0, len(full), 30):
            yield _sse("delta", {"content": full[i:i + 30], "session_id": session_id})
            await asyncio.sleep(0.005)

        save_db = SessionLocal()
        try:
            _save_message(save_db, session_id, "assistant", full, scope_type, scope_id)
        finally:
            save_db.close()
        yield _sse("done", {"session_id": session_id})
    except Exception as exc:
        logger.exception("gemini stream failed")
        yield _sse("error", {"content": str(exc)[:300]})
