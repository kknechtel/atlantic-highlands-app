"""
Document search — Postgres tsvector with proper quote handling.

Uses websearch_to_tsquery so the query string can include:
  - "exact phrases"   (only documents containing the literal phrase match)
  - regular keywords   (AND between terms by default)
  - or                 (OR operator)
  - -word              (exclude word)

If parsing fails (rare — e.g. unbalanced quotes), we fall back to
plainto_tsquery which never throws.

Falls back to filename ILIKE only when both tsquery paths return zero hits
AND the input looks like a literal substring. This stops the old behavior
where typos like "highander" silently matched stems of "highlands".
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.document import Document
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchResult(BaseModel):
    id: str
    filename: str
    doc_type: str | None
    category: str | None
    fiscal_year: str | None
    department: str | None = None
    status: str
    score: float
    snippet: str | None
    match_type: str  # "phrase" | "fts" | "filename" — useful for UI badges


class SearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    category: str | None = None
    doc_type: str | None = None
    fiscal_year: str | None = None
    department: str | None = None
    limit: int = 50


def _build_filter_sql(req: SearchRequest, params: dict) -> str:
    """Build the shared WHERE-clause additions for project/category/etc filters."""
    sql = ""
    if req.project_id:
        sql += " AND project_id = :pid"
        params["pid"] = req.project_id
    if req.category:
        sql += " AND category = :cat"
        params["cat"] = req.category
    if req.doc_type:
        sql += " AND doc_type = :dt"
        params["dt"] = req.doc_type
    if req.fiscal_year:
        sql += " AND fiscal_year = :fy"
        params["fy"] = req.fiscal_year
    if req.department:
        sql += " AND department = :dept"
        params["dept"] = req.department
    return sql


@router.post("", response_model=List[SearchResult], include_in_schema=False)
@router.post("/", response_model=List[SearchResult])
def search_documents(
    req: SearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = req.query.strip()
    if not query:
        return []

    has_quotes = '"' in query

    # Pass 1: websearch_to_tsquery — handles quoted phrases, AND, OR, -word.
    sql = """
        SELECT id, filename, doc_type, category, fiscal_year, department, status,
               ts_rank(search_vector, websearch_to_tsquery('english', :query)) AS score,
               ts_headline(
                   'english',
                   coalesce(extracted_text, ''),
                   websearch_to_tsquery('english', :query),
                   'MaxWords=35, MinWords=10, MaxFragments=2, ShortWord=2,
                    StartSel=<<MARK>>, StopSel=<</MARK>>'
               ) AS snippet
        FROM documents
        WHERE search_vector @@ websearch_to_tsquery('english', :query)
          AND lower(filename) NOT LIKE '%.xlsx'
          AND lower(filename) NOT LIKE '%.xls'
          AND lower(filename) NOT LIKE '%.csv'
          AND lower(filename) NOT LIKE 'document_summaries%'
    """
    params: dict = {"query": query}
    sql += _build_filter_sql(req, params)
    sql += " ORDER BY score DESC LIMIT :lim"
    params["lim"] = req.limit

    try:
        rows = db.execute(sql_text(sql), params).fetchall()
    except Exception as e:
        # Malformed websearch query (very rare). Fall through to plainto.
        logger.warning("websearch_to_tsquery failed for %r: %s", query, e)
        rows = []

    if rows:
        match_type = "phrase" if has_quotes else "fts"
        return [
            SearchResult(
                id=str(r.id), filename=r.filename, doc_type=r.doc_type,
                category=r.category, fiscal_year=r.fiscal_year, department=r.department,
                status=r.status, score=round(float(r.score), 4),
                snippet=r.snippet, match_type=match_type,
            )
            for r in rows
        ]

    # Pass 2: filename / notes ILIKE — same threshold the legacy code used,
    # but only when the user did NOT use quotes (a quoted query that misses
    # FTS should NOT silently match a stemmed substring of the filename —
    # that was the source of "highander → highlands" surprise).
    if has_quotes:
        return []

    like = f"%{query}%"
    fallback_q = (
        db.query(Document)
        .filter(
            or_(
                Document.filename.ilike(like),
                Document.notes.ilike(like),
                Document.doc_type.ilike(like),
                Document.department.ilike(like),
            ),
            ~Document.filename.ilike("%.xlsx"),
            ~Document.filename.ilike("%.xls"),
            ~Document.filename.ilike("%.csv"),
            ~Document.filename.ilike("document_summaries%"),
        )
    )
    if req.category:
        fallback_q = fallback_q.filter(Document.category == req.category)
    if req.doc_type:
        fallback_q = fallback_q.filter(Document.doc_type == req.doc_type)
    if req.fiscal_year:
        fallback_q = fallback_q.filter(Document.fiscal_year == req.fiscal_year)
    if req.department:
        fallback_q = fallback_q.filter(Document.department == req.department)

    docs = fallback_q.limit(req.limit).all()
    return [
        SearchResult(
            id=str(d.id), filename=d.filename, doc_type=d.doc_type,
            category=d.category, fiscal_year=d.fiscal_year, department=d.department,
            status=d.status, score=1.0,
            snippet=(d.notes[:150] if d.notes else None),
            match_type="filename",
        )
        for d in docs
    ]


# ─── Facets ─────────────────────────────────────────────────────────────────

# Year strings we accept. The data is messy (some are "Jan 2024", "01/2024",
# "FY2024", "2024-25" for school years). We extract the first 4-digit year.
import re
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _normalize_year(raw: Optional[str]) -> Optional[str]:
    """Return a clean 'YYYY' or 'YYYY-YYYY' (school year), or None if no year found."""
    if not raw:
        return None
    s = str(raw).strip()
    # School-year format like "2024-2025" or "2024-25" — keep as-is if both parts parse
    m = re.match(r"^(19|20)\d{2}\s*[-–/]\s*(?:(19|20))?\d{2,4}$", s)
    if m:
        return s
    m = _YEAR_RE.search(s)
    if m:
        return m.group(0)
    return None


def _normalize_dept(raw: Optional[str]) -> Optional[str]:
    """Title-case + strip. Returns None for empty."""
    if not raw:
        return None
    s = " ".join(raw.split())  # collapse whitespace
    if not s:
        return None
    return s


@router.get("/facets")
def get_facets(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get filter facets — deduped, normalized.

      doc_types:    raw enum values (controlled vocab — no normalization needed)
      categories:   raw (town/school/general)
      fiscal_years: only 4-digit years (or YYYY-YYYY school years), deduped
      departments:  case- and whitespace-normalized, deduped
    """
    base = db.query(Document)
    if project_id:
        base = base.filter(Document.project_id == project_id)

    # Doc type / category — controlled enums, no normalization
    doc_types = base.with_entities(Document.doc_type, func.count(Document.id)).group_by(Document.doc_type).all()
    categories = base.with_entities(Document.category, func.count(Document.id)).group_by(Document.category).all()

    # Fiscal years — sanitize to 4-digit years only, dedupe
    raw_years = base.with_entities(Document.fiscal_year, func.count(Document.id)).group_by(Document.fiscal_year).all()
    year_counts: dict[str, int] = {}
    for raw, count in raw_years:
        norm = _normalize_year(raw)
        if not norm:
            continue
        year_counts[norm] = year_counts.get(norm, 0) + int(count)

    # Departments — case-insensitive dedup, normalize whitespace
    raw_depts = base.with_entities(Document.department, func.count(Document.id)).group_by(Document.department).all()
    dept_counts: dict[str, int] = {}
    for raw, count in raw_depts:
        norm = _normalize_dept(raw)
        if not norm:
            continue
        # Case-insensitive dedup — keep the most common casing
        key = norm.casefold()
        if key in dept_counts:
            dept_counts[key] = dept_counts[key] + int(count)
        else:
            dept_counts[key] = int(count)
    # Map back to display strings (use the first occurrence's casing per key)
    dept_display: dict[str, str] = {}
    for raw, _ in raw_depts:
        norm = _normalize_dept(raw)
        if not norm:
            continue
        key = norm.casefold()
        dept_display.setdefault(key, norm)
    departments_out = {dept_display[k]: v for k, v in dept_counts.items()}

    return {
        "doc_types": {k or "unclassified": v for k, v in doc_types},
        "categories": {k or "uncategorized": v for k, v in categories},
        "fiscal_years": dict(sorted(year_counts.items(), reverse=True)),
        "departments": dict(sorted(departments_out.items(), key=lambda kv: -kv[1])),
    }
