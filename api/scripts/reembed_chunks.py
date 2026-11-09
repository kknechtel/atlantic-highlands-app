"""Clear and re-embed stored vectors.

  --all            every chunk AND document vector. Needed after changing
                   EMBEDDING_MODEL: vectors from different models aren't
                   comparable, so old ones would make semantic search return
                   noise until replaced.
  --since DATE     only chunks created on/after DATE (the old placeholder-vector
                   cleanup from when no Voyage key was set).

  python scripts/reembed_chunks.py --all --dry-run   # counts + token estimate
  python scripts/reembed_chunks.py --all

Vectors are cleared first, then refilled. Until the refill finishes, cleared
rows are simply absent from semantic search (keyword search still covers
them). Anything a failed call leaves NULL is retried by the nightly scrape.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from services.embeddings import EMBEDDING_MODEL, semantic_available  # noqa: E402
from services.ingestion import reembed_missing, reembed_missing_docs  # noqa: E402

# ~4 chars per token for English text; good enough to compare against the
# free-token allowance before spending anything.
_CHUNK_CHARS = "SELECT coalesce(sum(length(coalesce(context, '')) + length(content)), 0) FROM document_chunks"
_DOC_CHARS = """
    SELECT coalesce(sum(length(coalesce(title, '')) + length(filename) + length(coalesce(notes, ''))
                        + least(length(coalesce(extracted_text, '')), 32000)), 0)
    FROM documents d
    WHERE EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.id)
"""


def _drain(fn, db, label: str) -> int:
    total = 0
    while True:
        done = fn(db, limit=500)
        total += done
        print(f"  {label}: re-embedded {total}", flush=True)
        if done == 0:
            return total


def main() -> int:
    ap = argparse.ArgumentParser()
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="every chunk and document vector")
    scope.add_argument("--since", help="YYYY-MM-DD; chunks created on/after this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not semantic_available():
        print("VOYAGE_API_KEY is not set; nothing would be re-embedded. Aborting.")
        return 1

    db = SessionLocal()
    try:
        if args.all:
            n_chunks = db.execute(text("SELECT count(*) FROM document_chunks")).scalar()
            n_docs = db.execute(text("SELECT count(*) FROM documents WHERE embedding IS NOT NULL")).scalar()
            est = (db.execute(text(_CHUNK_CHARS)).scalar() + db.execute(text(_DOC_CHARS)).scalar()) // 4
            print(f"{n_chunks} chunks and {n_docs} document vectors to re-embed with {EMBEDDING_MODEL}.")
            print(f"Estimated ~{est / 1e6:.1f}M tokens.")
            if args.dry_run:
                return 0
            db.execute(text("UPDATE document_chunks SET embedding = NULL"))
            db.execute(text("UPDATE documents SET embedding = NULL"))
        else:
            n = db.execute(text(
                "SELECT count(*) FROM document_chunks WHERE created_at >= :since AND embedding IS NOT NULL"
            ), {"since": args.since}).scalar()
            print(f"{n} chunks created since {args.since} have vectors to replace.")
            if args.dry_run or not n:
                return 0
            db.execute(text(
                "UPDATE document_chunks SET embedding = NULL WHERE created_at >= :since"
            ), {"since": args.since})
        db.commit()

        chunks = _drain(reembed_missing, db, "chunks")
        docs = _drain(reembed_missing_docs, db, "documents") if args.all else 0
        left = db.execute(text("SELECT count(*) FROM document_chunks WHERE embedding IS NULL")).scalar()
        print(f"Done: {chunks} chunks, {docs} documents re-embedded; "
              f"{left} chunks still without vectors (retried nightly).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
