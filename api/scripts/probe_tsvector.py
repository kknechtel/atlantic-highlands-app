"""Print the actual tokens stored in a chunk's fts_vector to see how the
text-search config tokenized them. Helps diagnose hyphenated-word issues
like 'Winnerling-Moody' that LIKE finds but tsquery misses."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from database import SessionLocal
from sqlalchemy import text


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: probe_tsvector.py <term>")
        return 1
    q = sys.argv[1].lower()
    db = SessionLocal()
    try:
        # Show the raw lexemes that English config produces for 'winnerling'
        # — both the indexed form (to_tsvector) and the queried form (to_tsquery).
        print(f"=== how '{q}' is lexemized ===")
        idx = db.execute(text("SELECT to_tsvector('english', :q)"), {"q": q}).scalar()
        que = db.execute(text("SELECT websearch_to_tsquery('english', :q)::text"), {"q": q}).scalar()
        print(f"  to_tsvector('english', '{q}')        = {idx}")
        print(f"  websearch_to_tsquery('english', '{q}') = {que}")

        # Show how the actual hyphenated form gets tokenized in a chunk
        sample = "PB24-12 Winnerling-Moody Updated Plans"
        idx_sample = db.execute(text("SELECT to_tsvector('english', :s)"), {"s": sample}).scalar()
        print(f"\n  to_tsvector(English, {sample!r})")
        print(f"  = {idx_sample}")

        # Pull one chunk that has the literal substring but doesn't match websearch
        print(f"\n=== a chunk containing '{q}' (LIKE) but possibly missing from FTS ===")
        row = db.execute(text("""
            SELECT c.id, c.content, c.fts_vector::text AS vec
              FROM document_chunks c
             WHERE lower(c.content) LIKE :p
               AND NOT (c.fts_vector @@ websearch_to_tsquery('english', :q))
             LIMIT 1
        """), {"p": f"%{q}%", "q": q}).fetchone()
        if row:
            print(f"  chunk id={row.id}")
            # Show the relevant fragment of content
            content = row.content or ""
            idx = content.lower().find(q)
            snippet = content[max(0, idx - 80): idx + 120]
            print(f"  content excerpt: {snippet!r}")
            # Show whether the term is in the vector
            vec = row.vec or ""
            print(f"  vector contains '{q}': {q in vec}")
            print(f"  vector contains '{q[:6]}': {q[:6] in vec}")
            # Print only lexemes containing our term root
            tokens = [t for t in vec.split() if q[:5] in t.lower()]
            print(f"  matching tokens in vector: {tokens[:10]}")
        else:
            print("  (no such chunk — all LIKE matches also hit FTS)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
