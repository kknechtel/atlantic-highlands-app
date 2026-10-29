"""Replace chunk vectors written while no Voyage key was set.

Older code stored a non-semantic placeholder vector when VOYAGE_API_KEY was
missing. Those rows look embedded, so the nightly reembed_missing pass skips
them. This clears vectors for chunks created on/after --since and re-embeds
them with Voyage.

  python scripts/reembed_chunks.py --since 2026-05-23 [--dry-run]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from services.embeddings import semantic_available  # noqa: E402
from services.ingestion import reembed_missing  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="YYYY-MM-DD; chunks created on/after this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not semantic_available():
        print("VOYAGE_API_KEY is not set; nothing would be re-embedded. Aborting.")
        return 1

    db = SessionLocal()
    try:
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
        total = 0
        while True:
            done = reembed_missing(db, limit=500)
            total += done
            print(f"  re-embedded {total}", flush=True)
            if done == 0:
                break
        left = db.execute(text("SELECT count(*) FROM document_chunks WHERE embedding IS NULL")).scalar()
        print(f"Done: {total} re-embedded; {left} chunks still without vectors (retried nightly).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
