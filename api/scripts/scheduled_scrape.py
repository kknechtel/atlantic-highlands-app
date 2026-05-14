"""Entrypoint for the systemd-timer-driven daily scrape.

Invokes run_scraper() in recent-only mode (skips 2005-2013 AHNJ archives)
and tags the row in scraper_runs with triggered_by="schedule" so the UI
can distinguish auto runs from manual ones.

Wire-up on EC2:
  /etc/systemd/system/ah-scraper.service   (oneshot)
  /etc/systemd/system/ah-scraper.timer     (OnCalendar=Mon..Sun 11:00 UTC = 7am ET)

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

    logger.info("Starting scheduled scrape (recent_only).")
    await run_scraper(
        sites=None,  # default: all sites
        historical=False,  # recent-only: skip 2005-2013 AHNJ archives
        triggered_by="schedule",
    )
    final = get_scraper_status()
    logger.info(
        "Scheduled scrape done: %s uploaded, %s skipped, %s errors.",
        final["documents_uploaded"],
        final["documents_skipped"],
        len(final["errors"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
