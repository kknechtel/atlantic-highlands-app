"""
Rebuild fts_vector for every document and every chunk.

We hit this when:
  - The fts_vector column was added before all docs had extracted_text
    (so newly-OCR'd docs never got their vector populated).
  - The build-input changed (e.g. adding the title field, or switching
    to weighted setweight composition).

This script does both updates in single bulk SQL statements — much faster
than iterating per-row. Postgres only needs to scan the docs/chunks table
once each. On a 4k-doc corpus this completes in <10 seconds.

Usage on prod:
    /opt/atlantic-highlands/api/venv/bin/python scripts/rebuild_fts.py
"""
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    from database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # Document-level: title=A, filename=B, notes=C, body=D
        log.info("Rebuilding documents.fts_vector with weighted composition...")
        result = db.execute(text("""
            UPDATE documents
            SET fts_vector =
                setweight(to_tsvector('english', coalesce(title, '')),    'A') ||
                setweight(to_tsvector('english', coalesce(filename, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(notes, '')),    'C') ||
                setweight(to_tsvector('english', coalesce(left(extracted_text, 50000), '')), 'D')
        """))
        db.commit()
        log.info(f"  documents updated: {result.rowcount}")

        # Chunk-level: just the content (chunks are body slices already)
        log.info("Rebuilding document_chunks.fts_vector...")
        result = db.execute(text("""
            UPDATE document_chunks
            SET fts_vector = to_tsvector('english', coalesce(content, ''))
        """))
        db.commit()
        log.info(f"  chunks updated: {result.rowcount}")

        log.info("Done.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
