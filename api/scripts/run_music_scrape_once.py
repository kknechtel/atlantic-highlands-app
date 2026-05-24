"""One-shot manual trigger for the live-music venue scrape.

Same code path as the nightly run inside `scheduled_scrape.py`, broken
out so it can be invoked via SSM without nested-quote shell games.

Usage on EC2:
    sudo systemctl restart ah-api    # so the latest event_scrapers package is loaded
    cd /opt/atlantic-highlands/api
    /opt/atlantic-highlands/api/venv/bin/python -m scripts.run_music_scrape_once
"""
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main() -> int:
    from services.event_scrapers import run_music_scrape

    summary = run_music_scrape()
    print("---RESULT---")
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("venues_ok", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
