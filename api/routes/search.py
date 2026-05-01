"""Search routes - full-text search across OCR'd document content."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text, func, or_

from database import get_db
from models.document import Document
from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchResult(BaseModel):
    id: str
    filename: str
    doc_type: str | None
    category: str | None
    fiscal_year: str | None
    status: str
    score: float
    snippet: str | None


class SearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    category: str | None = None
    doc_type: str | None = None
    limit: int = 50


@router.post("", response_model=List[SearchResult], include_in_schema=False)
@router.post("/", response_model=List[SearchResult])
def search_documents(
    req: SearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full-text search across document content using PostgreSQL tsvector."""
    query = req.query.strip()
    if not query:
        return []

    # Build the tsquery
    terms = query.split()
    tsquery = " & ".join(terms)

    # Use PostgreSQL full-text search with ranking
    sql = """
        SELECT id, filename, doc_type, category, fiscal_year, status,
               ts_rank(search_vector, to_tsquery('english', :query)) as score,
               ts_headline('english', coalesce(extracted_text, ''), to_tsquery('english', :query),
                   'MaxWords=30, MinWords=10, MaxFragments=2') as snippet
        FROM documents
        WHERE search_vector @@ to_tsquery('english', :query)
          AND lower(filename) NOT LIKE '%.xlsx'
          AND lower(filename) NOT LIKE '%.xls'
          AND lower(filename) NOT LIKE 'document_summaries%'
    """
    params = {"query": tsquery}

    if req.project_id:
        sql += " AND project_id = :pid"
        params["pid"] = req.project_id
    if req.category:
        sql += " AND category = :cat"
        params["cat"] = req.category
    if req.doc_type:
        sql += " AND doc_type = :dt"
        params["dt"] = req.doc_type

    sql += " ORDER BY score DESC LIMIT :lim"
    params["lim"] = req.limit

    results = db.execute(sql_text(sql), params).fetchall()

    # Fallback to filename search if FTS returns nothing
    if not results:
        like_query = f"%{query}%"
        docs = db.query(Document).filter(
            or_(
                Document.filename.ilike(like_query),
                Document.notes.ilike(like_query),
                Document.doc_type.ilike(like_query),
            ),
            ~Document.filename.ilike('%.xlsx'),
            ~Document.filename.ilike('%.xls'),
            ~Document.filename.ilike('document_summaries%'),
        ).limit(req.limit).all()

        return [
            SearchResult(
                id=str(d.id), filename=d.filename, doc_type=d.doc_type,
                category=d.category, fiscal_year=d.fiscal_year, status=d.status,
                score=1.0, snippet=d.notes[:150] if d.notes else None,
            )
            for d in docs
        ]

    return [
        SearchResult(
            id=str(r.id), filename=r.filename, doc_type=r.doc_type,
            category=r.category, fiscal_year=r.fiscal_year, status=r.status,
            score=round(float(r.score), 4), snippet=r.snippet,
        )
        for r in results
    ]


@router.get("/facets")
def get_facets(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get facets for filtering."""
    base = db.query(Document)
    if project_id:
        base = base.filter(Document.project_id == project_id)

    doc_types = base.with_entities(Document.doc_type, func.count(Document.id)).group_by(Document.doc_type).all()
    categories = base.with_entities(Document.category, func.count(Document.id)).group_by(Document.category).all()
    fiscal_years = base.with_entities(Document.fiscal_year, func.count(Document.id)).group_by(Document.fiscal_year).order_by(Document.fiscal_year.desc()).all()

    return {
        "doc_types": {k or "unclassified": v for k, v in doc_types},
        "categories": {k or "uncategorized": v for k, v in categories},
        "fiscal_years": {k or "unknown": v for k, v in fiscal_years},
    }
