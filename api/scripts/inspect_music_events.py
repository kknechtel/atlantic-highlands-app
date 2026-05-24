"""One-shot diagnostic — print recent music events per venue.

Usage:
    /opt/atlantic-highlands/api/venv/bin/python -m scripts.inspect_music_events
"""
import sys

from sqlalchemy import text

from database import SessionLocal


def main() -> int:
    db = SessionLocal()
    try:
        for venue, in db.execute(text(
            "SELECT DISTINCT venue FROM calendar_events "
            "WHERE event_type = 'live_music' AND venue IS NOT NULL "
            "ORDER BY venue"
        )).fetchall():
            count = db.execute(text(
                "SELECT COUNT(*) FROM calendar_events WHERE venue = :v"
            ), {"v": venue}).scalar()
            print(f"\n=== {venue} ({count} total) ===")
            rows = db.execute(text(
                "SELECT date, time, title FROM calendar_events "
                "WHERE venue = :v ORDER BY date LIMIT 15"
            ), {"v": venue}).fetchall()
            for r in rows:
                title = (r.title or "")[:80]
                print(f"  {r.date} {(r.time or '       '):>10}  {title}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
