"""Reconcile stored borough-calendar events against ahnj.com.

`scrape_events.save_to_db` is insert-only (dedup on date+title), so any
row a buggy parser ever wrote stays in the table forever. That is how we
ended up serving "Music and Food Truck" and "Festival" as two separate
events on 2026-08-02, plus a bare "Borough" from "Borough Offices
Closed": the keyword-splitting parser produced them, then the fixed
parser simply inserted the correct titles alongside the old fragments.

This script re-scrapes each month and makes the table match the source:
rows the borough calendar no longer backs are deleted, missing ones are
inserted. It self-corrects any future parser change too, so prefer it
over one-off DELETE-by-title cleanups.

Only `source = 'ahnj_calendar'` rows are touched — live-music and
hand-entered events are never considered.

Deleting an event can orphan RSVPs that point at it. That is safe by
design: event_rsvps.event_id is deliberately not a foreign key and
dangling rows just don't render (see models/event_rsvp.py).

Usage:
    python scripts/reconcile_borough_events.py            # dry run
    python scripts/reconcile_borough_events.py --apply    # commit
    python scripts/reconcile_borough_events.py --apply --months 18
"""
import argparse
import calendar as _calendar
import sys
from datetime import date
from pathlib import Path

# Run as `python scripts/reconcile_borough_events.py` from api/ — put the
# package root on the path so `database` / `models` resolve, same as
# scrape_events.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from database import SessionLocal
from scripts.scrape_events import scrape_month, classify_borough_event


def _month_span(year: int, month: int) -> tuple[str, str]:
    last = _calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"


def _months(start: date, count: int) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    for _ in range(count):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def reconcile(months: int = 12, apply: bool = False) -> int:
    db = SessionLocal()
    deleted_total = inserted_total = 0
    try:
        for year, month in _months(date.today().replace(day=1), months):
            fresh = scrape_month(year, month)
            if not fresh:
                # Distinguishing "no events this month" from "fetch failed"
                # isn't worth the complexity — scrape_month returns [] for
                # both. Skipping means a transient outage can't wipe a month.
                print(f"{year}-{month:02d}: scraped 0 events, skipping")
                continue

            start, end = _month_span(year, month)
            fresh_keys = {(e["date"], e["title"]) for e in fresh}

            stored = db.execute(text(
                "SELECT id, date, title FROM calendar_events "
                "WHERE source = 'ahnj_calendar' AND date BETWEEN :s AND :e"
            ), {"s": start, "e": end}).fetchall()

            stale = [r for r in stored if (r.date.isoformat(), r.title) not in fresh_keys]
            stored_keys = {(r.date.isoformat(), r.title) for r in stored}
            missing = [e for e in fresh if (e["date"], e["title"]) not in stored_keys]

            for r in stale:
                print(f"  - {r.date} {r.title!r}")
                if apply:
                    db.execute(text("DELETE FROM calendar_events WHERE id = :id"), {"id": r.id})
            for e in missing:
                print(f"  + {e['date']} {e['title']!r}")
                if apply:
                    db.execute(text("""
                        INSERT INTO calendar_events
                            (date, title, time, source, source_url, event_type)
                        VALUES (:date, :title, :time, :source, :url, :event_type)
                    """), {
                        "date": e["date"],
                        "title": e["title"],
                        "time": e.get("time"),
                        "source": e.get("source", "ahnj_calendar"),
                        "url": e.get("url"),
                        "event_type": classify_borough_event(e["title"]),
                    })

            deleted_total += len(stale)
            inserted_total += len(missing)
            print(f"{year}-{month:02d}: {len(stale)} stale, {len(missing)} missing "
                  f"({len(fresh)} on the borough calendar)")

        if apply:
            db.commit()
            print(f"\nApplied: deleted {deleted_total}, inserted {inserted_total}.")
        else:
            print(f"\nDry run: would delete {deleted_total}, insert {inserted_total}. "
                  f"Re-run with --apply to commit.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    ap.add_argument("--months", type=int, default=12, help="months to reconcile from this month")
    args = ap.parse_args()
    sys.exit(reconcile(months=args.months, apply=args.apply))
