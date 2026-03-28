"""Search routes - full-text and semantic search across documents."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

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


@router.post("/", response_model=List[SearchResult])
def search_documents(
    req: SearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search documents by filename, type, category, and metadata."""
    query_lower = req.query.lower()
    terms = query_lower.split()

    base_query = db.query(Document)

    if req.project_id:
        base_query = base_query.filter(Document.project_id == req.project_id)
    if req.category:
        base_query = base_query.filter(Document.category == req.category)
    if req.doc_type:
        base_query = base_query.filter(Document.doc_type == req.doc_type)

    docs = base_query.all()

    # Score each document based on search terms
    results = []
    for doc in docs:
        score = 0.0
        searchable = " ".join([
            doc.filename.lower(),
            (doc.doc_type or "").lower(),
            (doc.category or "").lower(),
            (doc.department or "").lower(),
            (doc.fiscal_year or "").lower(),
            (doc.notes or "").lower(),
        ])

        for term in terms:
            if term in doc.filename.lower():
                score += 2.0  # filename match is strongest
            if term in (doc.doc_type or "").lower():
                score += 1.5
            if term in (doc.category or "").lower():
                score += 1.0
            if term in (doc.notes or "").lower():
                score += 0.5
            if term in searchable:
                score += 0.3

        if score > 0:
            # Generate snippet
            snippet = None
            if doc.notes:
                snippet = doc.notes[:150]

            results.append(SearchResult(
                id=str(doc.id),
                filename=doc.filename,
                doc_type=doc.doc_type,
                category=doc.category,
                fiscal_year=doc.fiscal_year,
                status=doc.status,
                score=round(score, 2),
                snippet=snippet,
            ))

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results[: req.limit]


@router.get("/facets")
def get_facets(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get facets (counts by doc_type, category, fiscal_year) for filtering."""
    base = db.query(Document)
    if project_id:
        base = base.filter(Document.project_id == project_id)

    doc_types = (
        base.with_entities(Document.doc_type, func.count(Document.id))
        .group_by(Document.doc_type)
        .all()
    )
    categories = (
        base.with_entities(Document.category, func.count(Document.id))
        .group_by(Document.category)
        .all()
    )
    fiscal_years = (
        base.with_entities(Document.fiscal_year, func.count(Document.id))
        .group_by(Document.fiscal_year)
        .order_by(Document.fiscal_year.desc())
        .all()
    )

    return {
        "doc_types": {k or "unclassified": v for k, v in doc_types},
        "categories": {k or "uncategorized": v for k, v in categories},
        "fiscal_years": {k or "unknown": v for k, v in fiscal_years},
    }
