"""Remove calendar_events rows attributed to a source no scraper produces.

Prod carried a row claiming "Brian Kirk & The Jirks" at The Sandbox at
Seastreak on 2026-08-14, 7:00-10:00 PM, with source
`band_site:briankirkandthejirks`.

Nothing in this codebase writes that source — there is no band-site
scraper. The row was inserted by hand (see ssm_add_briankirk.json at the
repo root, since removed) and the invented source string made it look
scraped. The venue's own schedule for that date is Meg Cannon 4-7 PM and
Roots In Blue Stone 7-10 PM, so the row put one real band in another
real band's slot at a real venue.

It survives every other cleanup we have: reconcile_music_events only
considers html:/playwright:/squarespace:/tribe: sources precisely so it
won't touch hand-curated entries, and the nightly scrape never revisits
a row it didn't create.

Note what this script is NOT for. Hand-curated rows with an honest
provenance are legitimate and must be left alone — the Gaslight series
is transcribed from the venue's own Instagram calendar image and is
titled "Gaslight Live Music - Check @gaslight.ah for lineup", which
tells the reader exactly where to verify it. The test is whether a
source describes something real, not whether a scraper wrote it.

Usage:
    python scripts/purge_unsourced_events.py                 # dry run
    python scripts/purge_unsourced_events.py --apply
    python scripts/purge_unsourced_events.py --source foo --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from database import SessionLocal

# Sources confirmed to be hand-inserted with a fabricated provenance.
FABRICATED_SOURCES = ["band_site:briankirkandthejirks"]


def purge(sources: list[str], apply: bool = False) -> int:
    db = SessionLocal()
    total = 0
    try:
        for src in sources:
            rows = db.execute(text(
                "SELECT id, date, title, time, venue FROM calendar_events "
                "WHERE source = :s ORDER BY date"
            ), {"s": src}).fetchall()

            if not rows:
                print(f"{src}: nothing found")
                continue

            print(f"{src}: {len(rows)} row(s)")
            for r in rows:
                print(f"  - {r.date} {r.title!r} {r.time} @ {r.venue}")
            if apply:
                db.execute(text("DELETE FROM calendar_events WHERE source = :s"), {"s": src})
            total += len(rows)

        if apply:
            db.commit()
            print(f"\nDeleted {total} row(s).")
        else:
            print(f"\nDry run: would delete {total} row(s). Re-run with --apply.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    ap.add_argument("--source", action="append", default=None,
                    help="source string to purge; repeatable. "
                         "Defaults to the known fabricated sources.")
    args = ap.parse_args()
    sys.exit(purge(args.source or FABRICATED_SOURCES, apply=args.apply))
