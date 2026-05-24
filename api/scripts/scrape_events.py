"""
Scrape the borough events calendar from ahnj.com and store events in the database.
Run: python scripts/scrape_events.py
"""
import sys, os, re, json, logging, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

CALENDAR_URL = "https://www.ahnj.com/ahnj/Upcoming%20Events/"
MONTH_URL = "https://www.ahnj.com/ahnj/Upcoming%20Events/?month={month:02d}&year={year}"

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}


def scrape_month(year: int, month: int) -> list[dict]:
    """Scrape events for a specific month from the borough calendar."""
    url = MONTH_URL.format(month=month, year=year)
    logger.info(f"Scraping {year}-{month:02d}: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    events = []

    # Find calendar table cells - use separator to preserve structure
    for cell in soup.find_all("td"):
        # Get text with newlines preserved between elements
        raw = cell.get_text(separator="\n", strip=True)
        if not raw:
            continue

        # First line should be the day number
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        if not lines:
            continue

        # Check if first token is a day number
        first_match = re.match(r'^(\d{1,2})$', lines[0])
        if not first_match:
            # Try embedded: "2Mayor & Council..."
            first_match = re.match(r'^(\d{1,2})(\D.+)', lines[0])
            if first_match:
                day = int(first_match.group(1))
                if day < 1 or day > 31:
                    continue
                remaining = [first_match.group(2).strip()] + lines[1:]
            else:
                continue
        else:
            day = int(first_match.group(1))
            if day < 1 or day > 31:
                continue
            remaining = lines[1:]

        if not remaining:
            continue

        # Join all remaining text into one event string, then split by known event markers
        full_text = " ".join(remaining)

        # Skip noise
        if "Printed Calendar" in full_text:
            continue

        # Split into individual events by known event keywords
        event_markers = r'(?=(?:Mayor\s*&\s*Council|Planning\s*Board|Harbor\s*Commission|Recreation|Environmental\s*Commission|Shade\s*Tree|Board\s*of\s*Education|BOE|Easter|July\s*4|Independence|Memorial\s*Day|Labor\s*Day|Veterans|Christmas|Thanksgiving|Holiday|Parade|Festival|Concert|Farmers?\s*Market|Clean\s*Up|Borough\s*(?:and\s*)?Harbor|Offices?\s*(?:are\s*)?closed))'
        event_parts = re.split(event_markers, full_text, flags=re.I)

        for part in event_parts:
            part = part.strip()
            if not part or len(part) < 4:
                continue

            # Extract time if present
            time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM|Noon))', part)
            if not time_match:
                time_match = re.search(r'(\d{1,2}:\d{2})\s', part)
            event_time = time_match.group(1) if time_match else None

            # Clean title
            event_title = part.strip()
            # Remove trailing time if already captured
            if event_time:
                event_title = event_title.replace(event_time, "").strip()
            # Remove trailing punctuation artifacts
            event_title = re.sub(r'[\u25b6\u25ba►▶]\s*', '', event_title).strip()

            if not event_title or len(event_title) < 3:
                continue

            date_str = f"{year}-{month:02d}-{day:02d}"

            events.append({
                "date": date_str,
                "title": event_title,
                "time": event_time,
                "source": "ahnj_calendar",
                "url": url,
            })

    logger.info(f"  Found {len(events)} events for {year}-{month:02d}")
    time.sleep(1)  # Be polite
    return events


def scrape_all_months(start_year=2026, start_month=1, end_year=2026, end_month=12) -> list[dict]:
    """Scrape multiple months."""
    all_events = []
    for year in range(start_year, end_year + 1):
        for month in range(start_month if year == start_year else 1,
                           (end_month if year == end_year else 12) + 1):
            events = scrape_month(year, month)
            all_events.extend(events)
    return all_events


# Borough-calendar classification. Lives server-side so both apps consume
# the SAME bucket assignment instead of duplicating heuristics in TS.
#   - 'govt'      → council, planning, harbor commission, BOE, offices-closed
#   - 'community' → parades, fireworks, concerts, farmers markets, holidays,
#                   anything else not matching a govt keyword
_GOVT_KEYWORDS = (
    "council", "planning board", "commission",
    "board of education", "boe", "reorganization",
    "offices closed", "offices are closed",
    "borough hall", "town hall", "court",
    "zoning board", "shade tree",
    "environmental commission", "recreation commission",
)


def classify_borough_event(title: str) -> str:
    t = (title or "").lower()
    return "govt" if any(k in t for k in _GOVT_KEYWORDS) else "community"


def save_to_db(events: list[dict]):
    """Save events to the database calendar_events table."""
    from database import SessionLocal
    from sqlalchemy import text as sql_text

    db = SessionLocal()
    try:
        # Create table if not exists. Extra columns (venue/city/event_type/
        # end_time/ticket_url) added in 2026-05; the IF NOT EXISTS guards
        # make this idempotent on fresh installs, and the migration in
        # database.py picks them up on existing prod tables.
        db.execute(sql_text("""
            CREATE TABLE IF NOT EXISTS calendar_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                date DATE NOT NULL,
                title TEXT NOT NULL,
                time TEXT,
                location TEXT,
                description TEXT,
                source TEXT DEFAULT 'ahnj_calendar',
                source_url TEXT,
                venue TEXT,
                city TEXT,
                event_type TEXT DEFAULT 'general',
                end_time TEXT,
                ticket_url TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.commit()

        # Insert events (upsert by date+title)
        inserted = 0
        for event in events:
            exists = db.execute(sql_text(
                "SELECT 1 FROM calendar_events WHERE date = :date AND title = :title"
            ), {"date": event["date"], "title": event["title"]}).fetchone()

            if not exists:
                db.execute(sql_text("""
                    INSERT INTO calendar_events (date, title, time, source, source_url, event_type)
                    VALUES (:date, :title, :time, :source, :url, :event_type)
                """), {
                    "date": event["date"],
                    "title": event["title"],
                    "time": event.get("time"),
                    "source": event.get("source", "ahnj_calendar"),
                    "url": event.get("url"),
                    "event_type": classify_borough_event(event["title"]),
                })
                inserted += 1

        db.commit()
        logger.info(f"Inserted {inserted} new events ({len(events)} total scraped)")
    finally:
        db.close()


def save_to_json(events: list[dict], path: str = None):
    """Save events to a JSON file."""
    if not path:
        path = str(Path(__file__).parent.parent / "storage" / "calendar_events.json")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(events, f, indent=2)
    logger.info(f"Saved {len(events)} events to {path}")


def run_events_scrape(months_ahead: int = 12) -> dict:
    """Scrape a rolling window starting at the current month and going
    `months_ahead` months forward, then persist to the calendar_events table.

    Called by `scripts/scheduled_scrape.py` on the nightly tick. Returns a
    counts dict for the caller to log; never raises so a scrape failure
    can't cascade into the doc scrape it's chained off.
    """
    try:
        now = datetime.utcnow()
        # Inclusive end month (now.month → now.month + months_ahead).
        total_end = now.month + months_ahead
        end_year = now.year + (total_end - 1) // 12
        end_month = ((total_end - 1) % 12) + 1
        events = scrape_all_months(now.year, now.month, end_year, end_month)
        save_to_db(events)
        return {"scraped": len(events), "ok": True}
    except Exception as exc:
        logger.exception("events scrape failed: %s", exc)
        return {"scraped": 0, "ok": False, "error": str(exc)}


if __name__ == "__main__":
    summary = run_events_scrape()
    print(f"\nEvents scrape: {summary}")
