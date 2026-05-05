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
    semantic_weight: float = 0.6,
    keyword_weight: float = 0.4,
    fiscal_year: Optional[str] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Return up to top_k chunks ranked by combined semantic + keyword score.

    Each result includes:
      - chunk_id, document_id, filename, fiscal_year, category, doc_type
      - content (the chunk text — already trimmed)
      - chunk_index, page_start, page_end
      - score (float, higher is better)
    """
    has_vec = _has_vector_column(db, "document_chunks")

    if has_vec:
        try:
            return _hybrid_chunk_search(db, query, top_k, semantic_weight, keyword_weight, fiscal_year, category)
        except Exception as exc:
            log.warning("Hybrid chunk search failed, falling back to keyword: %s", exc)

    return _keyword_chunk_search(db, query, top_k, fiscal_year, category)


def _hybrid_chunk_search(db, query, top_k, sem_w, kw_w, fiscal_year, category):
    embedding = to_pgvector_literal(embed_query(query))

    sql = text("""
        WITH semantic AS (
            SELECT c.id, c.document_id, c.content, c.chunk_index, c.page_start, c.page_end,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS sem_score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND (:fiscal_year IS NULL OR d.fiscal_year = :fiscal_year)
              AND (:category IS NULL OR d.category = :category)
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :pool
        ),
        keyword AS (
            SELECT c.id, c.document_id, c.content, c.chunk_index, c.page_start, c.page_end,
                   ts_rank_cd(c.fts_vector, plainto_tsquery('english', :query)) AS kw_score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.fts_vector @@ plainto_tsquery('english', :query)
              AND (:fiscal_year IS NULL OR d.fiscal_year = :fiscal_year)
              AND (:category IS NULL OR d.category = :category)
            ORDER BY kw_score DESC
            LIMIT :pool
        ),
        combined AS (
            SELECT
                COALESCE(s.id, k.id)            AS chunk_id,
                COALESCE(s.document_id, k.document_id) AS document_id,
                COALESCE(s.content, k.content)  AS content,
                COALESCE(s.chunk_index, k.chunk_index) AS chunk_index,
                COALESCE(s.page_start, k.page_start)   AS page_start,
                COALESCE(s.page_end,   k.page_end)     AS page_end,
                COALESCE(s.sem_score, 0) * :sem_w
                  + COALESCE(k.kw_score, 0) * :kw_w   AS score
            FROM semantic s
            FULL OUTER JOIN keyword k ON s.id = k.id
        )
        SELECT c.chunk_id, c.document_id, c.content, c.chunk_index,
               c.page_start, c.page_end, c.score,
               d.filename, d.fiscal_year, d.category, d.doc_type
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
        "pool": top_k * 4,
        "top_k": top_k,
        "sem_w": sem_w,
        "kw_w": kw_w,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


def _keyword_chunk_search(db, query, top_k, fiscal_year, category):
    """tsvector-only fallback. Works without pgvector or embeddings."""
    sql = text("""
        SELECT c.id AS chunk_id, c.document_id, c.content, c.chunk_index,
               c.page_start, c.page_end,
               ts_rank_cd(c.fts_vector, plainto_tsquery('english', :query)) AS score,
               d.filename, d.fiscal_year, d.category, d.doc_type
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.fts_vector @@ plainto_tsquery('english', :query)
          AND (:fiscal_year IS NULL OR d.fiscal_year = :fiscal_year)
          AND (:category IS NULL OR d.category = :category)
        ORDER BY score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "query": query, "fiscal_year": fiscal_year,
        "category": category, "top_k": top_k,
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
            SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS sem_score
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
            SELECT id, ts_rank_cd(fts_vector, plainto_tsquery('english', :query)) AS kw_score
            FROM documents
            WHERE fts_vector @@ plainto_tsquery('english', :query)
              AND (:fiscal_year IS NULL OR fiscal_year = :fiscal_year)
              AND (:category IS NULL OR category = :category)
              AND lower(filename) NOT LIKE '%.xlsx'
              AND lower(filename) NOT LIKE '%.xls'
              AND lower(filename) NOT LIKE '%.csv'
            ORDER BY kw_score DESC
            LIMIT :pool
        ),
        combined AS (
            SELECT COALESCE(s.id, k.id) AS id,
                   COALESCE(s.sem_score, 0) * 0.6
                     + COALESCE(k.kw_score, 0) * 0.4 AS score
            FROM semantic s
            FULL OUTER JOIN keyword k ON s.id = k.id
        )
        SELECT d.id, d.filename, d.doc_type, d.category, d.fiscal_year,
               d.notes, d.page_count, c.score
        FROM combined c
        JOIN documents d ON d.id = c.id
        ORDER BY c.score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "embedding": embedding, "query": query,
        "fiscal_year": fiscal_year, "category": category,
        "pool": top_k * 4, "top_k": top_k,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


def _keyword_doc_search(db, query, top_k, fiscal_year, category):
    sql = text("""
        SELECT id, filename, doc_type, category, fiscal_year, notes, page_count,
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
