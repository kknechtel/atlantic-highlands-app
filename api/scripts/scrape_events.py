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


def save_to_db(events: list[dict]):
    """Save events to the database calendar_events table."""
    from database import SessionLocal
    from sqlalchemy import text as sql_text

    db = SessionLocal()
    try:
        # Create table if not exists
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
                    INSERT INTO calendar_events (date, title, time, source, source_url)
                    VALUES (:date, :title, :time, :source, :url)
                """), {
                    "date": event["date"],
                    "title": event["title"],
                    "time": event.get("time"),
                    "source": event.get("source", "ahnj_calendar"),
                    "url": event.get("url"),
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


if __name__ == "__main__":
    # Scrape 2026 calendar
    events = scrape_all_months(2026, 1, 2026, 12)
    print(f"\nTotal events found: {len(events)}")
    for e in events[:20]:
        print(f"  {e['date']} {(e.get('time') or ''):10s} {e['title']}")

    save_to_json(events)
    save_to_db(events)
