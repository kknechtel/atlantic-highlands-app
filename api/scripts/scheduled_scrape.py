"""Entrypoint for the systemd-timer-driven nightly scrape.

Runs in three steps each tick:
  1. Document scrape — `run_scraper(historical=True)` across all 13 crawlers.
     Tags the scraper_runs row with triggered_by="schedule".
  2. Event calendar scrape — `run_events_scrape()` against ahnj.com/Upcoming
     Events for the rolling current-month + 12-month window. Failure here is
     logged but does not fail the unit, so docs always get committed.

Wire-up on EC2:
  /etc/systemd/system/ah-scraper.service   (oneshot)
  /etc/systemd/system/ah-scraper.timer     (OnCalendar=*-*-* 00:00:00 America/New_York)

The unit files live in infra/systemd/ and are installed via SSM, not by
the application code itself.
"""
import asyncio
import logging
import sys

sys.path.insert(0, "/opt/atlantic-highlands/api")

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
    # historical=True crawls the 2005-2013 AHNJ archives too. Per-doc dedup
    # in the runner means re-crawling those archives every night is wasted
    # bandwidth, not duplicate data — but it's the simplest way to
    # guarantee "everything available" is in the index.
    await run_scraper(
        sites=None,           # default: all 13 crawlers
        historical=True,      # full crawl, including 2005-2013 archives
        triggered_by="schedule",
    )
    final = get_scraper_status()
    logger.info(
        "Document scrape done: %s uploaded, %s skipped, %s errors.",
        final["documents_uploaded"],
        final["documents_skipped"],
        len(final["errors"]),
    )

    # Step 2 — event calendar. Imported lazily so a bug here can't break
    # the doc scrape's import-time path.
    try:
        from scripts.scrape_events import run_events_scrape
        events_summary = run_events_scrape(months_ahead=12)
        logger.info("Events scrape done: %s", events_summary)
    except Exception as exc:
        logger.exception("events scrape step failed: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
