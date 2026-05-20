"""Quick diagnostic: given a search term, show every doc/chunk that mentions
it via plain SQL LIKE, plus what tsvector FTS returns.

  python scripts/probe_term.py winnerling
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from database import SessionLocal
from sqlalchemy import text


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: probe_term.py <term>")
        return 1
    q = sys.argv[1].lower()
    like = f"%{q}%"
    db = SessionLocal()
    try:
        print(f"=== docs with '{q}' anywhere ===")
        rows = db.execute(text(
            """SELECT id, filename, doc_type, department, fiscal_year, title
                 FROM documents
                WHERE lower(extracted_text) LIKE :p
                   OR lower(filename) LIKE :p
                   OR lower(notes) LIKE :p
                   OR lower(coalesce(title, '')) LIKE :p
                LIMIT 30"""
        ), {"p": like}).fetchall()
        for r in rows:
            print(f"  {r.filename[:70]:<70} | dept={r.department or '-':<25} | title={(r.title or '-')[:55]}")
        print(f"docs-total: {len(rows)}")

        print(f"\n=== chunks with '{q}' ===")
        rows = db.execute(text(
            """SELECT c.document_id, d.filename, c.chunk_index, d.department
                 FROM document_chunks c
                 JOIN documents d ON d.id = c.document_id
                WHERE lower(c.content) LIKE :p
                LIMIT 10"""
        ), {"p": like}).fetchall()
        for r in rows:
            print(f"  {r.filename[:70]:<70} chunk={r.chunk_index} dept={r.department}")
        print(f"chunk-total: {len(rows)}")

        print("\n=== FTS hits ===")
        doc_hits = db.execute(text(
            "SELECT count(*) FROM documents WHERE fts_vector @@ websearch_to_tsquery('english', :q)"
        ), {"q": q}).scalar()
        chunk_hits = db.execute(text(
            "SELECT count(*) FROM document_chunks WHERE fts_vector @@ websearch_to_tsquery('english', :q)"
        ), {"q": q}).scalar()
        print(f"FTS-document-hits: {doc_hits}")
        print(f"FTS-chunk-hits: {chunk_hits}")

        # Top FTS-ranked docs for the term, for the actual search-route path
        print(f"\n=== top tsvector-ranked docs for '{q}' ===")
        rows = db.execute(text(
            """SELECT d.filename, d.department, ts_rank(d.fts_vector, websearch_to_tsquery('english', :q)) AS rank
                 FROM documents d
                WHERE d.fts_vector @@ websearch_to_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT 5"""
        ), {"q": q}).fetchall()
        for r in rows:
            print(f"  rank={r.rank:.4f}  dept={r.department}  {r.filename[:70]}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
