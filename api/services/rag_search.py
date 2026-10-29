"""
Hybrid RAG search: pgvector semantic + Postgres tsvector keyword.

Two search surfaces:
  - search_chunks(): chunk-level retrieval. Used by the chat tool loop when
    Claude needs precise passages from long documents.
  - search_documents(): document-level retrieval. Used when Claude wants
    to know which documents exist on a topic and grab their summaries.

If pgvector isn't installed (or rows haven't been embedded yet), both
functions degrade to keyword-only via tsvector — the chat still works,
just with worse recall.
"""
import logging
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.embeddings import embed_query, to_pgvector_literal

log = logging.getLogger(__name__)


def _has_vector_column(db: Session, table: str) -> bool:
    """Detect whether the embedding column was successfully added on startup."""
    return bool(db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = 'embedding'"
    ), {"t": table}).fetchone())


# ── Chunk-level hybrid search ───────────────────────────────────────────

def search_chunks(
    db: Session,
    query: str,
    top_k: int = 12,
    semantic_weight: float = 1.0,
    keyword_weight: float = 1.0,
    fiscal_year: Optional[str] = None,
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
    document_id: Optional[str] = None,
    project_id: Optional[str] = None,
    department: Optional[str] = None,
    use_websearch: bool = False,
    municipality: Optional[str] = None,
    embed_text: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Return up to top_k chunks ranked by combined semantic + keyword score.

    Each result includes:
      - chunk_id, document_id, filename, fiscal_year, category, doc_type,
        department, created_at, status
      - content (the chunk text — already trimmed)
      - chunk_index, page_start, page_end
      - score (float, higher is better)

    Optional filters:
      - fiscal_year/category/doc_type/department: scalar equality
      - document_id: restrict to one document (for in-doc search)
      - project_id: restrict to docs in a project
      - use_websearch: parse `query` with websearch_to_tsquery — enables
        "quoted phrases", OR, -exclude. Falls back to plainto on malformed.
      - municipality: atlantic_highlands | highlands | hhrsd | regional | state
      - embed_text: text to embed for the semantic side when `query` carries
        keyword syntax (OR-expansions, operators) that would muddy the vector.
      - date_from/date_to: YYYY, YYYY-MM or YYYY-MM-DD. Applied inside both
        retrieval lists (not after ranking). Undated docs match on fiscal-year
        overlap instead of being dropped.

    Ranking is reciprocal rank fusion of the semantic and keyword lists,
    scaled so a doc ranked #1 in both scores 1.0 (#1 in one list ≈ 0.5).
    """
    has_vec = _has_vector_column(db, "document_chunks")
    dates = date_bounds(date_from, date_to)

    if has_vec:
        try:
            return _hybrid_chunk_search(
                db, query, top_k, semantic_weight, keyword_weight,
                fiscal_year, category, doc_type, document_id,
                project_id, department, use_websearch,
                municipality, embed_text or query, dates,
            )
        except Exception as exc:
            log.warning("Hybrid chunk search failed, falling back to keyword: %s", exc)
            db.rollback()

    return _keyword_chunk_search(
        db, query, top_k, fiscal_year, category, doc_type,
        document_id, project_id, department, use_websearch, municipality, dates,
    )


_NO_DATES = {"date_from": None, "date_to": None, "year_from": None, "year_to": None}


def date_bounds(date_from: Optional[str], date_to: Optional[str]) -> dict:
    """Normalize YYYY / YYYY-MM / YYYY-MM-DD bounds to strings that compare
    correctly against ISO `documents.doc_date`, plus year bounds for the
    fiscal-year fallback on undated docs. Unparseable bounds are ignored."""
    def year(v: str) -> Optional[int]:
        return int(v[:4]) if re.match(r"^\d{4}(-\d{2}){0,2}$", v) else None

    out = dict(_NO_DATES)
    if date_from and (y := year(date_from.strip())):
        v = date_from.strip()
        out["date_from"] = v if len(v) == 10 else (v + "-01-01")[:10]
        out["year_from"] = y
    if date_to and (y := year(date_to.strip())):
        v = date_to.strip()
        # "2024" -> "2024-99-99": sorts after every real 2024 date.
        out["date_to"] = v if len(v) == 10 else (v + "-99-99")[:10]
        out["year_to"] = y
    return out


# Shared WHERE fragment for the date window (alias d = documents). Dated
# docs compare doc_date; undated docs fall back to fiscal-year overlap — a
# school year "2024-25" spans into 2025.
_DATE_FILTER = """
              AND ((:date_from IS NULL AND :date_to IS NULL)
                   OR (d.doc_date IS NOT NULL
                       AND (:date_from IS NULL OR d.doc_date >= :date_from)
                       AND (:date_to IS NULL OR d.doc_date <= :date_to))
                   OR (d.doc_date IS NULL AND d.fiscal_year ~ '^[0-9]{4}'
                       AND (:year_from IS NULL OR CAST(left(d.fiscal_year, 4) AS int)
                            + CASE WHEN d.fiscal_year LIKE '%-%' THEN 1 ELSE 0 END >= :year_from)
                       AND (:year_to IS NULL OR CAST(left(d.fiscal_year, 4) AS int) <= :year_to)))"""


# RRF constant (Cormack et al.). With k=60, 1/(k+1) is the top-rank term;
# RRF_SCALE maps "#1 in both lists" to 1.0 so downstream boosts keep their scale.
RRF_K = 60
RRF_SCALE = (RRF_K + 1) / 2


def _hybrid_chunk_search(
    db, query, top_k, sem_w, kw_w, fiscal_year, category,
    doc_type, document_id, project_id, department, use_websearch,
    municipality, embed_text, dates=_NO_DATES,
):
    embedding = to_pgvector_literal(embed_query(embed_text))
    tsq_fn = "websearch_to_tsquery" if use_websearch else "plainto_tsquery"

    sql = text(f"""
        WITH semantic AS (
            SELECT c.id, c.document_id, c.content, c.context, c.chunk_index, c.page_start, c.page_end,
                   ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:embedding AS vector)) AS sem_rank
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND (:fiscal_year IS NULL OR d.fiscal_year = :fiscal_year)
              AND (:category IS NULL OR d.category = :category)
              AND (:doc_type IS NULL OR d.doc_type = :doc_type)
              AND (:document_id IS NULL OR c.document_id = CAST(:document_id AS uuid))
              AND (:project_id IS NULL OR d.project_id = CAST(:project_id AS uuid))
              AND (:department IS NULL OR lower(d.department) = lower(:department))
              AND (:municipality IS NULL OR d.municipality = :municipality){_DATE_FILTER}
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :pool
        ),
        keyword AS (
            SELECT c.id, c.document_id, c.content, c.context, c.chunk_index, c.page_start, c.page_end,
                   ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.fts_vector, COALESCE({tsq_fn}('english', :query),
                                                     plainto_tsquery('english', :query))) DESC) AS kw_rank
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.fts_vector @@ COALESCE({tsq_fn}('english', :query),
                                            plainto_tsquery('english', :query))
              AND (:fiscal_year IS NULL OR d.fiscal_year = :fiscal_year)
              AND (:category IS NULL OR d.category = :category)
              AND (:doc_type IS NULL OR d.doc_type = :doc_type)
              AND (:document_id IS NULL OR c.document_id = CAST(:document_id AS uuid))
              AND (:project_id IS NULL OR d.project_id = CAST(:project_id AS uuid))
              AND (:department IS NULL OR lower(d.department) = lower(:department))
              AND (:municipality IS NULL OR d.municipality = :municipality){_DATE_FILTER}
            ORDER BY kw_rank
            LIMIT :pool
        ),
        combined AS (
            SELECT
                COALESCE(s.id, k.id)            AS chunk_id,
                COALESCE(s.document_id, k.document_id) AS document_id,
                COALESCE(s.content, k.content)  AS content,
                COALESCE(s.context, k.context)  AS context,
                COALESCE(s.chunk_index, k.chunk_index) AS chunk_index,
                COALESCE(s.page_start, k.page_start)   AS page_start,
                COALESCE(s.page_end,   k.page_end)     AS page_end,
                (COALESCE(:sem_w / (:rrf_k + s.sem_rank), 0)
                  + COALESCE(:kw_w / (:rrf_k + k.kw_rank), 0)) * :rrf_scale AS score
            FROM semantic s
            FULL OUTER JOIN keyword k ON s.id = k.id
        )
        SELECT c.chunk_id, c.document_id, c.content, c.context, c.chunk_index,
               c.page_start, c.page_end, c.score,
               d.filename, d.fiscal_year, d.category, d.doc_type,
               d.department, d.created_at, d.status,
               d.title, d.doc_date, d.notes, d.municipality
        FROM combined c
        JOIN documents d ON d.id = c.document_id
        ORDER BY c.score DESC
        LIMIT :top_k
    """)

    rows = db.execute(sql, {
        "embedding": embedding,
        "query": query,
        "fiscal_year": fiscal_year,
        "category": category,
        "doc_type": doc_type,
        "document_id": str(document_id) if document_id else None,
        "project_id": str(project_id) if project_id else None,
        "department": department,
        "pool": top_k * 4,
        "top_k": top_k,
        "sem_w": sem_w,
        "kw_w": kw_w,
        "rrf_k": RRF_K,
        "rrf_scale": RRF_SCALE,
        "municipality": municipality,
        **dates,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


def _keyword_chunk_search(
    db, query, top_k, fiscal_year, category, doc_type,
    document_id, project_id, department, use_websearch, municipality=None,
    dates=_NO_DATES,
):
    """tsvector-only fallback. Works without pgvector or embeddings."""
    tsq_fn = "websearch_to_tsquery" if use_websearch else "plainto_tsquery"
    sql = text(f"""
        SELECT c.id AS chunk_id, c.document_id, c.content, c.context, c.chunk_index,
               c.page_start, c.page_end,
               ts_rank_cd(c.fts_vector, COALESCE({tsq_fn}('english', :query),
                                                  plainto_tsquery('english', :query))) AS score,
               d.filename, d.fiscal_year, d.category, d.doc_type,
               d.department, d.created_at, d.status,
               d.title, d.doc_date, d.notes, d.municipality
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.fts_vector @@ COALESCE({tsq_fn}('english', :query),
                                        plainto_tsquery('english', :query))
          AND (:fiscal_year IS NULL OR d.fiscal_year = :fiscal_year)
          AND (:category IS NULL OR d.category = :category)
          AND (:doc_type IS NULL OR d.doc_type = :doc_type)
          AND (:document_id IS NULL OR c.document_id = CAST(:document_id AS uuid))
          AND (:project_id IS NULL OR d.project_id = CAST(:project_id AS uuid))
          AND (:department IS NULL OR lower(d.department) = lower(:department))
          AND (:municipality IS NULL OR d.municipality = :municipality){_DATE_FILTER}
        ORDER BY score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "query": query, "fiscal_year": fiscal_year,
        "category": category, "doc_type": doc_type,
        "document_id": str(document_id) if document_id else None,
        "project_id": str(project_id) if project_id else None,
        "department": department,
        "municipality": municipality,
        "top_k": top_k,
        **dates,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Document-level search (summaries + metadata) ───────────────────────

def search_documents(
    db: Session,
    query: str,
    top_k: int = 10,
    fiscal_year: Optional[str] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Return ranked documents with their summaries — for "what documents
    exist on X" questions. Hybrid when possible, keyword-only otherwise."""
    has_vec = _has_vector_column(db, "documents")

    if has_vec:
        try:
            return _hybrid_doc_search(db, query, top_k, fiscal_year, category)
        except Exception as exc:
            log.warning("Hybrid doc search failed, falling back to keyword: %s", exc)

    return _keyword_doc_search(db, query, top_k, fiscal_year, category)


def _hybrid_doc_search(db, query, top_k, fiscal_year, category):
    embedding = to_pgvector_literal(embed_query(query))
    sql = text("""
        WITH semantic AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS sem_rank
            FROM documents
            WHERE embedding IS NOT NULL
              AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
              AND (:category IS NULL OR category = :category)
              AND lower(filename) NOT LIKE '%.xlsx'
              AND lower(filename) NOT LIKE '%.xls'
              AND lower(filename) NOT LIKE '%.csv'
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :pool
        ),
        keyword AS (
            SELECT id, ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(fts_vector, plainto_tsquery('english', :query)) DESC) AS kw_rank
            FROM documents
            WHERE fts_vector @@ plainto_tsquery('english', :query)
              AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
              AND (:category IS NULL OR category = :category)
              AND lower(filename) NOT LIKE '%.xlsx'
              AND lower(filename) NOT LIKE '%.xls'
              AND lower(filename) NOT LIKE '%.csv'
            ORDER BY kw_rank
            LIMIT :pool
        ),
        combined AS (
            SELECT COALESCE(s.id, k.id) AS id,
                   (COALESCE(1.0 / (:rrf_k + s.sem_rank), 0)
                     + COALESCE(1.0 / (:rrf_k + k.kw_rank), 0)) * :rrf_scale AS score
            FROM semantic s
            FULL OUTER JOIN keyword k ON s.id = k.id
        )
        SELECT d.id, d.filename, d.title, d.doc_date, d.municipality, d.doc_type,
               d.category, d.fiscal_year, d.notes, d.page_count, c.score
        FROM combined c
        JOIN documents d ON d.id = c.id
        ORDER BY c.score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "embedding": embedding, "query": query,
        "fiscal_year": fiscal_year, "category": category,
        "pool": top_k * 4, "top_k": top_k,
        "rrf_k": RRF_K, "rrf_scale": RRF_SCALE,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


def _keyword_doc_search(db, query, top_k, fiscal_year, category):
    sql = text("""
        SELECT id, filename, title, doc_date, municipality, doc_type, category,
               fiscal_year, notes, page_count,
               ts_rank_cd(fts_vector, plainto_tsquery('english', :query)) AS score
        FROM documents
        WHERE fts_vector @@ plainto_tsquery('english', :query)
          AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
          AND (:category IS NULL OR category = :category)
          AND lower(filename) NOT LIKE '%.xlsx'
          AND lower(filename) NOT LIKE '%.xls'
          AND lower(filename) NOT LIKE '%.csv'
        ORDER BY score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "query": query, "fiscal_year": fiscal_year,
        "category": category, "top_k": top_k,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Direct lookups used by chat tools ──────────────────────────────────

def get_document_excerpt(db: Session, document_id: str, max_chars: int = 12000) -> Optional[dict]:
    """Fetch a document's metadata + first N chars of extracted text. Used by
    the `read_document` tool when Claude wants to actually look at a file."""
    row = db.execute(text("""
        SELECT id, filename, doc_type, category, fiscal_year, notes, page_count,
               substring(extracted_text from 1 for :n) AS excerpt
        FROM documents WHERE id = CAST(:id AS uuid)
    """), {"id": str(document_id), "n": max_chars}).fetchone()
    return dict(row._mapping) if row else None


def get_document_text(db: Session, document_id: str) -> Optional[dict]:
    """Metadata + the full extracted text, for paging and in-document find."""
    row = db.execute(text("""
        SELECT id, filename, title, doc_date, doc_type, category, fiscal_year,
               notes, page_count, COALESCE(extracted_text, '') AS body
        FROM documents WHERE id = CAST(:id AS uuid)
    """), {"id": str(document_id)}).fetchone()
    return dict(row._mapping) if row else None


def list_recent_documents(db: Session, doc_type: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Surface recent documents for browsing-style queries ('what's the latest budget?')."""
    sql = """
        SELECT id, filename, doc_type, category, fiscal_year, notes,
               page_count, created_at
        FROM documents
        WHERE lower(filename) NOT LIKE '%.xlsx'
          AND lower(filename) NOT LIKE '%.csv'
    """
    params: dict = {"limit": limit}
    if doc_type:
        sql += " AND doc_type = :doc_type"
        params["doc_type"] = doc_type
    sql += " ORDER BY fiscal_year DESC NULLS LAST, created_at DESC LIMIT :limit"
    rows = db.execute(text(sql), params).fetchall()
    return [dict(r._mapping) for r in rows]
