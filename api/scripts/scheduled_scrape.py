"""Entrypoint for the systemd-timer-driven nightly scrape.

Runs in three steps each tick, each isolated so a failure can't take
out the next:

  1. Document scrape — `run_scraper(historical=True)` across every source
     in the municipality's sources.json.
     Tags the scraper_runs row with triggered_by="schedule".
  2. Town event calendar — `run_events_scrape()` against the source's
     events_calendar page for current month + 12 ahead.
     2b. School district calendar — `run_school_calendar_scrape()` reads
     the source's events_ical feed.
  3. Live-music scrape — `run_music_scrape()` iterates the venue registry
     (Squarespace + WordPress Tribe Events adapters).

Wire-up on EC2:
  /etc/systemd/system/ah-scraper.service   (oneshot)
  /etc/systemd/system/ah-scraper.timer     (OnCalendar=*-*-* 00:00:00 America/New_York)

The unit files live in infra/systemd/ and are installed via SSM, not by
the application code itself.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ah_scheduled_scrape")


async def main() -> int:
    from services.scraper.runner import run_scraper, get_scraper_status

    status = get_scraper_status()
    if status.get("running"):
        # A manual run is already in flight in another process. Skip rather
        # than queue — running two scrapers against the same project would
        # produce duplicate skipped counts and noise.
        logger.warning("Another scraper run is already active; skipping scheduled tick.")
        return 0

    logger.info("Starting scheduled scrape (historical=True, all sources).")
    # historical=True crawls each source's historical_pages too. Per-doc dedup
    # in the runner means re-crawling those archives every night is wasted
    # bandwidth, not duplicate data — but it's the simplest way to
    # guarantee "everything available" is in the index.
    await run_scraper(
        sites=None,           # default: every configured source
        historical=True,      # full crawl, including historical_pages
        triggered_by="schedule",
    )
    final = get_scraper_status()
    logger.info(
        "Document scrape done: %s uploaded, %s skipped, %s errors.",
        final["documents_uploaded"],
        final["documents_skipped"],
        len(final["errors"]),
    )

    # Step 2 — town event calendar. Imported lazily so a bug here can't
    # break the doc scrape's import-time path.
    try:
        from scripts.scrape_events import run_events_scrape
        events_summary = run_events_scrape(months_ahead=12)
        logger.info("Town events scrape done: %s", events_summary)
    except Exception as exc:
        logger.exception("town events scrape failed: %s", exc)

    # Step 2b — school district calendar (iCal feed).
    try:
        from services.school_calendar import run_school_calendar_scrape
        logger.info("School calendar scrape done: %s", run_school_calendar_scrape())
    except Exception as exc:
        logger.exception("school calendar scrape failed: %s", exc)

    # Step 3 — live-music venue scrape.
    try:
        from services.event_scrapers import run_music_scrape
        music_summary = run_music_scrape()
        logger.info(
            "Music scrape done: %d venues OK / %d failed, %d events scraped, %d new",
            music_summary["venues_ok"],
            music_summary["venues_failed"],
            music_summary["scraped_total"],
            music_summary["inserted_total"],
        )
        # Per-venue detail at INFO so journalctl shows which sites broke.
        for v in music_summary["venues"]:
            status = "ok" if v["ok"] else f"FAIL ({v.get('error', '?')})"
            logger.info("  %s (%s): %d scraped, %d new — %s",
                        v["venue"], v["city"], v["scraped"], v["inserted"], status)
    except Exception as exc:
        logger.exception("music scrape step failed: %s", exc)

    # Step 4 — process new docs: local OCR, flash-lite title/summary, index.
    # Capped per night so a big backlog can't run for hours; the rest
    # carries over to the next run (or scripts.enrich_all for backfills).
    try:
        from services.document_processor import process_pending
        limit = int(os.environ.get("NIGHTLY_PROCESS_LIMIT", "400"))
        totals = await process_pending(limit=limit)
        logger.info("Document processing done: %s", totals)
        from database import SessionLocal
        from services.ingestion import reembed_missing
        with SessionLocal() as db:
            reembed_missing(db)
    except Exception as exc:
        logger.exception("document processing step failed: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
