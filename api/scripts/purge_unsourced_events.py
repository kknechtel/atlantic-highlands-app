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

The second mode (--venue with --between) removes rows a parser dated
wrong. reconcile_music_events can't: it only judges rows inside the span
the venue currently publishes, precisely so it won't delete real events
beyond that window — and a misdated row is outside the window *because*
it's misdated. The Donovan's month bug left eight Aug 1-6 shows stored
as Sep 1-6, duplicating the corrected August rows.

Usage:
    python scripts/purge_unsourced_events.py                 # dry run
    python scripts/purge_unsourced_events.py --apply
    python scripts/purge_unsourced_events.py --source foo --apply
    python scripts/purge_unsourced_events.py --venue "Donovan's Reef" \\
        --between 2026-09-01 2026-09-06 --source-prefix "playwright:" --apply
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


def purge_range(venue: str, start: str, end: str,
                source_prefix: str | None = None, apply: bool = False) -> int:
    """Delete one venue's rows in an explicit date range.

    For parser artifacts only — rows whose date is wrong, which is why
    the venue-window logic in reconcile_music_events can't see them.
    Always dry-run first: this deletes whatever matches, with no
    cross-check against the venue's live listing.
    """
    db = SessionLocal()
    try:
        sql = ("SELECT id, date, title, time, source FROM calendar_events "
               "WHERE venue = :v AND date BETWEEN :s AND :e")
        params = {"v": venue, "s": start, "e": end}
        if source_prefix:
            sql += " AND source LIKE :p"
            params["p"] = f"{source_prefix}%"

        rows = db.execute(text(sql + " ORDER BY date"), params).fetchall()
        print(f"{venue} {start}..{end}"
              f"{f' source {source_prefix}%' if source_prefix else ''}: {len(rows)} row(s)")
        for r in rows:
            print(f"  - {r.date} {r.title!r} {r.time}")

        if apply and rows:
            db.execute(text(sql.replace(
                "SELECT id, date, title, time, source FROM", "DELETE FROM")), params)
            db.commit()
            print(f"\nDeleted {len(rows)} row(s).")
        elif not apply:
            print(f"\nDry run: would delete {len(rows)} row(s). Re-run with --apply.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="commit (default: dry run)")
    ap.add_argument("--source", action="append", default=None,
                    help="source string to purge; repeatable. "
                         "Defaults to the known fabricated sources.")
    ap.add_argument("--venue", default=None,
                    help="range mode: venue whose misdated rows to remove")
    ap.add_argument("--between", nargs=2, metavar=("START", "END"), default=None,
                    help="range mode: inclusive YYYY-MM-DD bounds")
    ap.add_argument("--source-prefix", default=None,
                    help="range mode: restrict to sources with this prefix")
    args = ap.parse_args()

    if args.venue or args.between:
        if not (args.venue and args.between):
            ap.error("--venue and --between must be given together")
        sys.exit(purge_range(args.venue, args.between[0], args.between[1],
                             source_prefix=args.source_prefix, apply=args.apply))
    sys.exit(purge(args.source or FABRICATED_SOURCES, apply=args.apply))
