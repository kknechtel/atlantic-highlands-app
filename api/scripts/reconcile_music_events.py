"""Reconcile stored live-music events against what the venues publish now.

The runner keys on (date, venue, title) and only ever inserts or refreshes
details. When a *title* changes — because a parser was fixed, or a venue
edited its listing — the old row is unreachable and survives forever
beside the corrected one. After the 2026-08 parser fixes prod still held:

    'The Nerds Get Tickets'          (button label swept into the title)
    'Miss Melissaâ€™s Aardvarks...'  (mojibake from an older scrape)

both sitting next to clean rows for the same show, with the broken bare
"7"/"10" times the fix was meant to replace.

This deletes rows the venue no longer lists. It does not insert — the
nightly run_music_scrape already adds new shows and refreshes details on
existing ones, so removing the unreachable leftovers is the only gap.

Two things keep it from deleting real data:

  * Only rows inside the date span the scrape actually returned are
    considered. Venues publish different windows (Sandbox ~3 months,
    Proving Ground ~1), so a row beyond the fresh span is out of scope,
    not stale.
  * A venue that scrapes zero events is skipped entirely — that's a dead
    site or a transient failure, not an empty calendar.

Past events are never touched; they're the archive.

Only scraper-written rows (source html:/playwright:/squarespace:/tribe:)
are eligible. Hand-entered and borough rows are left alone — for those,
see reconcile_borough_events.py.

Deleting an event can orphan RSVPs, which is safe by design:
event_rsvps.event_id is deliberately not a foreign key and dangling rows
just don't render (see models/event_rsvp.py).

Usage:
    python scripts/reconcile_music_events.py            # dry run
    python scripts/reconcile_music_events.py --apply
    python scripts/reconcile_music_events.py --venue "The Sandbox at Seastreak"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from database import SessionLocal
from services.event_scrapers.registry import VENUES

SCRAPER_SOURCE_PREFIXES = ("html:", "playwright:", "squarespace:", "tribe:")


def reconcile(venue_filter: str | None = None, apply: bool = False) -> int:
    db = SessionLocal()
    deleted_total = 0
    try:
        for name, city, fn, kwargs in VENUES:
            if venue_filter and name != venue_filter:
                continue
            try:
                fresh = fn(venue_name=name, city=city, **kwargs)
            except Exception as exc:
                print(f"{name}: scrape raised {type(exc).__name__}, skipping")
                continue
            if not fresh:
                print(f"{name}: scraped 0 events, skipping")
                continue

            dates = sorted(e["date"] for e in fresh if e.get("date"))
            span_start, span_end = dates[0], dates[-1]
            fresh_keys = {(e["date"], e["title"]) for e in fresh}

            src_clause = " OR ".join(
                f"source LIKE '{p}%'" for p in SCRAPER_SOURCE_PREFIXES
            )
            stored = db.execute(text(
                f"SELECT id, date, title, time FROM calendar_events "
                f"WHERE venue = :venue AND event_type = 'live_music' "
                f"AND date >= CURRENT_DATE AND date BETWEEN :s AND :e "
                f"AND ({src_clause})"
            ), {"venue": name, "s": span_start, "e": span_end}).fetchall()

            stale = [r for r in stored
                     if (r.date.isoformat(), r.title) not in fresh_keys]

            for r in stale:
                print(f"  - {r.date} {r.title!r} (time={r.time!r})")
                if apply:
                    db.execute(text("DELETE FROM calendar_events WHERE id = :id"),
                               {"id": r.id})
            deleted_total += len(stale)
            print(f"{name}: {len(stale)} stale of {len(stored)} stored "
                  f"in {span_start}..{span_end} ({len(fresh)} live)")

        if apply:
            db.commit()
            print(f"\nApplied: deleted {deleted_total} stale rows.")
        else:
            print(f"\nDry run: would delete {deleted_total}. "
                  f"Re-run with --apply to commit.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    ap.add_argument("--venue", default=None, help="limit to one venue by display name")
    args = ap.parse_args()
    sys.exit(reconcile(venue_filter=args.venue, apply=args.apply))
