"""
Document ingestion: takes Documents that have extracted_text and produces
DocumentChunk rows + populates the embedding/fts_vector columns on both
documents and chunks.

Idempotent: re-ingesting a document deletes its existing chunks first.
Safe to run from a script, an admin endpoint, or as a one-shot on startup.
"""
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.document import Document
from models.document_chunk import DocumentChunk
from services.chunker import chunk_text
from services.embeddings import (
    embed_documents_batch,
    embed_document,
    to_pgvector_literal,
)

log = logging.getLogger(__name__)


def _refresh_doc_fts(db: Session, doc_id) -> None:
    db.execute(text("""
        UPDATE documents
        SET fts_vector = to_tsvector('english',
            coalesce(filename, '') || ' ' ||
            coalesce(notes, '') || ' ' ||
            coalesce(left(extracted_text, 50000), '')
        )
        WHERE id = CAST(:id AS uuid)
    """), {"id": str(doc_id)})


def _refresh_chunk_fts(db: Session, chunk_ids: list) -> None:
    if not chunk_ids:
        return
    db.execute(text("""
        UPDATE document_chunks
        SET fts_vector = to_tsvector('english', coalesce(content, ''))
        WHERE id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": [str(i) for i in chunk_ids]})


def _set_doc_embedding(db: Session, doc_id, vec: list[float]) -> None:
    db.execute(text("""
        UPDATE documents
        SET embedding = CAST(:vec AS vector)
        WHERE id = CAST(:id AS uuid)
    """), {"id": str(doc_id), "vec": to_pgvector_literal(vec)})


def _set_chunk_embeddings(db: Session, pairs: list[tuple]) -> None:
    """pairs: [(chunk_id, vec), ...]"""
    for cid, vec in pairs:
        db.execute(text("""
            UPDATE document_chunks
            SET embedding = CAST(:vec AS vector)
            WHERE id = CAST(:id AS uuid)
        """), {"id": str(cid), "vec": to_pgvector_literal(vec)})


def ingest_document(db: Session, doc: Document, force: bool = False) -> dict:
    """Chunk + embed one document. Returns a small summary dict."""
    if not doc.extracted_text or len(doc.extracted_text) < 100:
        return {"document_id": str(doc.id), "skipped": True, "reason": "no_text"}

    # Delete existing chunks to keep this idempotent.
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()

    chunks_text = list(chunk_text(doc.extracted_text))
    if not chunks_text:
        return {"document_id": str(doc.id), "skipped": True, "reason": "empty_after_chunking"}

    # Insert chunk rows first (without embeddings) so we have IDs.
    rows = [
        DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=c,
            token_count=len(c) // 4,
        )
        for i, c in enumerate(chunks_text)
    ]
    db.add_all(rows)
    db.flush()

    # Embed + populate fts in one pass.
    vecs = embed_documents_batch([r.content for r in rows])
    _set_chunk_embeddings(db, [(r.id, v) for r, v in zip(rows, vecs)])
    _refresh_chunk_fts(db, [r.id for r in rows])

    # Document-level vector uses filename + notes + first 32K of body.
    doc_text = " ".join(filter(None, [doc.filename, doc.notes or "", doc.extracted_text[:32000]]))
    _set_doc_embedding(db, doc.id, embed_document(doc_text))
    _refresh_doc_fts(db, doc.id)

    db.commit()
    return {"document_id": str(doc.id), "chunks": len(rows), "filename": doc.filename}


def ingest_all_pending(db: Session, limit: Optional[int] = None) -> dict:
    """Ingest all documents that don't have chunks yet (or have empty fts_vector)."""
    q = (
        db.query(Document)
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .filter(Document.extracted_text.isnot(None))
        .filter(DocumentChunk.id.is_(None))  # no chunks yet
    )
    if limit:
        q = q.limit(limit)

    docs = q.all()
    log.info("Ingesting %d documents", len(docs))
    summary = {"total": len(docs), "ingested": 0, "skipped": 0, "errors": 0, "details": []}
    for d in docs:
        try:
            res = ingest_document(db, d)
            if res.get("skipped"):
                summary["skipped"] += 1
            else:
                summary["ingested"] += 1
            summary["details"].append(res)
        except Exception as exc:
            log.exception("Failed to ingest %s: %s", d.filename, exc)
            db.rollback()
            summary["errors"] += 1
            summary["details"].append({"document_id": str(d.id), "error": str(exc)})
    return summary


def ingest_one(db: Session, document_id: str, force: bool = False) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return {"error": "not_found"}
    return ingest_document(db, doc, force=force)
