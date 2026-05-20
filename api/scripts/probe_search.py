"""End-to-end search probe — calls the actual search_documents() function the
HTTP route would call, then dumps a summary of what gets returned. Bypasses
auth entirely so we can sanity-check the search pipeline on prod via SSM.

  python scripts/probe_search.py winnerling
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from database import SessionLocal
from routes.search import SearchRequest, search_documents


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: probe_search.py <query>")
        return 1
    query = " ".join(sys.argv[1:])

    db = SessionLocal()
    try:
        # search_documents expects a `user`; pass None — the route doesn't
        # actually use it for anything except the log row.
        req = SearchRequest(query=query, limit=20)

        class _User:
            id = None
        user = _User()
        resp = search_documents(req, db=db, user=user)

        print(f"=== query: {query!r} ===")
        print(f"latency_ms:  {resp.latency_ms}")
        print(f"query_id:    {resp.query_id}")
        print(f"did_you_mean: {resp.did_you_mean!r}")
        if resp.parsed_filters:
            print(f"parsed_filters: hits={resp.parsed_filters.hits} "
                  f"fy={resp.parsed_filters.fiscal_year} "
                  f"dept={resp.parsed_filters.department} "
                  f"doc_type={resp.parsed_filters.doc_type}")
        print(f"results: {len(resp.results)}")
        print()
        for i, r in enumerate(resp.results, 1):
            print(f"  {i:2}. score={r.score:.3f}  match={r.match_type}  matches={r.match_count or 1}")
            print(f"      title:    {r.title!r}")
            print(f"      filename: {r.filename}")
            print(f"      dept:     {r.department}  | date: {r.doc_date}  | fy: {r.fiscal_year}")
            if r.summary:
                print(f"      summary:  {r.summary[:120]!r}")
            if r.snippet:
                # Strip MARK delimiters for terminal display
                snip = r.snippet.replace("<<MARK>>", "[").replace("<</MARK>>", "]")
                print(f"      snippet:  {snip[:140]!r}")
            print()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
