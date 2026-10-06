"""Local-only scraper for ecode360.com.

ecode360 is Cloudflare-Turnstile protected: the production API server has no
Chrome and is firewalled to a non-residential AWS IP, so the cloud scraper
returns 0 docs for this source. This script runs from a developer laptop
(which has Chrome and a residential IP) and pushes results to the same
RDS + S3 the cloud API uses.

First-time setup (selenium isn't in api/requirements.txt — it's a local-only dep):
    pip install selenium webdriver-manager

Usage (from repo root):
    cd api
    python scripts/scrape_ecode_local.py

Requirements:
    - api/.env points DATABASE_URL at the prod RDS (or whichever DB you want
      to write to) and has AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY for S3.
    - Google Chrome installed locally (webdriver_manager fetches the matching
      ChromeDriver automatically).

Runs are tagged triggered_by="local:ecode" so the UI's run-history panel
can distinguish them from scheduled/manual cloud runs.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Make sibling api/ modules (config, database, services, …) importable when
# this script is invoked directly. Equivalent to PYTHONPATH=api.
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ah_local_ecode")


async def main() -> int:
    from services.scraper.runner import run_scraper, get_scraper_status

    status = get_scraper_status()
    if status.get("running"):
        logger.warning("Another scraper run is already active in this process; aborting.")
        return 1

    logger.info("Starting local ecode360 scrape (Selenium + stealth Chrome).")
    await run_scraper(
        sites=["ecode"],
        historical=True,
        triggered_by="local:ecode",
    )
    final = get_scraper_status()
    logger.info(
        "Local ecode scrape done: %s uploaded, %s skipped, %s errors.",
        final["documents_uploaded"],
        final["documents_skipped"],
        len(final["errors"]),
    )
    for err in final["errors"][:10]:
        logger.warning("  err: %s", err)
    return 0 if not final["errors"] else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
