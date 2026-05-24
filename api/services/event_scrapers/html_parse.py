"""HTML-parse adapter for venues that don't expose a structured events API.

Each venue gets its own `parse_*` function because every site lays out
its schedule differently. The shared `fetch_events` wrapper does the
HTTP GET, hands the response body to the parser, and normalizes the
result into our standard event dict.

Per-venue parsers in this module:
  - parse_proving_ground   — Highlands, SpotApps event list
  - parse_chubby_pickle    — Highlands, WP REST page render (calendar grid)
  - parse_seafarer         — Highlands, plain text block on homepage

Parsers return a list of partial event dicts (date, title, time, optional
end_time). The wrapper fills in venue/city/event_type/source/ticket_url.

Failures never raise — they log + return []. We'd rather skip a broken
venue than tank the nightly run.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ah-events-scraper/1.0; +https://ahnj.info)",
    "Accept": "text/html,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Parser signature: takes the raw response body (str), returns a list of
# partial event dicts. Year context is passed so parsers without an explicit
# year in the source (e.g. "Friday, May 22") can construct a real date.
ParserFn = Callable[[str, int], list[dict]]


def fetch_events(
    venue_name: str,
    city: str,
    url: str,
    parser: ParserFn,
    year_context: Optional[int] = None,
) -> list[dict]:
    """Fetch + parse one venue."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("[html:%s] fetch failed (%s): %s", venue_name, url, exc)
        return []

    yr = year_context or date.today().year
    try:
        partials = parser(resp.text, yr)
    except Exception as exc:
        logger.exception("[html:%s] parser raised: %s", venue_name, exc)
        return []

    out: list[dict] = []
    for p in partials:
        if not p.get("date") or not p.get("title"):
            continue
        out.append({
            "date": p["date"],
            "title": p["title"],
            "time": p.get("time"),
            "end_time": p.get("end_time"),
            "venue": venue_name,
            "city": city,
            "location": f"{venue_name}, {city}",
            "event_type": "live_music",
            "source": f"html:{venue_name}",
            "url": p.get("url") or url,
            "ticket_url": p.get("url"),
            "description": p.get("description"),
        })
    logger.info("[html:%s] parsed %d events", venue_name, len(out))
    return out


# ── Date helpers ────────────────────────────────────────────────────────

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _safe_date(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except (ValueError, TypeError):
        return None


def _normalize_time(t: str) -> Optional[str]:
    """'7PM', '7:00 PM', '7pm-10pm' → '7:00 PM' (start only)."""
    if not t:
        return None
    t = t.strip().rstrip(".")
    # Strip end-time half of a range
    t = re.split(r"\s*[-–—]\s*", t, 1)[0].strip()
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([APap][Mm])$", t.replace(".", ""))
    if not m:
        return t  # return as-is; caller can still render it
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    ampm = m.group(3).upper()
    return f"{hh}:{mm:02d} {ampm}"


# ── Per-venue parsers ──────────────────────────────────────────────────

def parse_proving_ground(html: str, year: int) -> list[dict]:
    """SpotApps event list at https://www.theprovingground.com/events.

    SpotApps renders each event as a card with a date label like
    "Sunday, May 25" + the title. Layout is fragile but consistent enough
    to grep with text-only soup.
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    # Cards on SpotApps usually live inside `div.spot-event` or similar.
    # Fall back to scanning the whole page text for date headings.
    cards = soup.find_all(attrs={"class": re.compile(r"event", re.I)})
    if not cards:
        cards = [soup]

    seen: set[tuple[str, str]] = set()
    for card in cards:
        text = card.get_text("\n", strip=True)
        # Match lines like: "Sunday, May 25" or "May 25" or "May 25, 2026"
        date_pattern = re.compile(
            r"(?:(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+)?"
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})"
            r"(?:,\s+(\d{4}))?",
            re.I,
        )
        for m in date_pattern.finditer(text):
            mon = _MONTHS.get(m.group(1).lower())
            if not mon:
                continue
            day = int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else year
            d = _safe_date(yr, mon, day)
            if not d:
                continue
            # Title is the next non-empty line after the date.
            tail = text[m.end():].lstrip()
            title_line = tail.split("\n", 1)[0].strip() if tail else ""
            title_line = re.sub(r"^[-–—:]\s*", "", title_line)
            if not title_line or len(title_line) < 3:
                continue
            # Time is a "7PM" / "1pm-4pm" pattern anywhere in the next 200 chars.
            time_m = re.search(r"\d{1,2}(?::\d{2})?\s*(?:[APap][Mm])(?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
                               tail[:200])
            t = _normalize_time(time_m.group(0)) if time_m else None
            key = (d, title_line.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append({"date": d, "title": title_line, "time": t})

    return events


def parse_chubby_pickle(json_body: str, year: int) -> list[dict]:
    """WP REST page response. Pass `https://thechubbypicklenj.com/wp-json/wp/v2/pages?slug=calendar`
    — the response is a JSON array; take pages[0]['content']['rendered'],
    parse the resulting HTML for calendar cells."""
    import json
    try:
        pages = json.loads(json_body)
    except Exception:
        return []
    if not isinstance(pages, list) or not pages:
        return []
    rendered = (pages[0].get("content") or {}).get("rendered") or ""
    if not rendered:
        return []
    soup = BeautifulSoup(rendered, "html.parser")
    events: list[dict] = []
    # Each "event" cell in JetEngine's calendar widget renders titles inside
    # link tags. Grab visible text and pair it with the cell's day-number.
    for cell in soup.select(".jet-listing-grid__item, .jet-calendar-day, td"):
        day_el = cell.select_one(".jet-calendar-day__date, .day-number, .day")
        title_el = cell.select_one("a, .event-title, .jet-listing-dynamic-field__content")
        if not day_el or not title_el:
            continue
        day_text = day_el.get_text(strip=True)
        title_text = title_el.get_text(" ", strip=True)
        if not day_text.isdigit() or not title_text:
            continue
        # The page rendering itself doesn't tell us the month — for the
        # current view it's "this month". Fall back to today's month.
        today = date.today()
        d = _safe_date(year, today.month, int(day_text))
        if d:
            events.append({"date": d, "title": title_text})
    return events


def parse_seafarer(html: str, year: int) -> list[dict]:
    """Free-text schedule block on the Seafarer homepage. Lines look like:
        "Friday, May 22 — Charles Krause at 6PM"
        "Saturday May 23: Band Name 7-10pm"
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    events: list[dict] = []
    pattern = re.compile(
        r"(?:(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+)?"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:,\s+(\d{4}))?"
        r"\s*[-–—:]\s*"
        r"(.+?)"
        r"(?=\n|$)",
        re.I,
    )
    for m in pattern.finditer(text):
        mon = _MONTHS.get(m.group(1).lower())
        if not mon:
            continue
        day = int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else year
        d = _safe_date(yr, mon, day)
        if not d:
            continue
        rest = m.group(4).strip()
        time_m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:[APap][Mm])(?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?)",
                           rest)
        time_str = _normalize_time(time_m.group(0)) if time_m else None
        title = re.sub(r"\s+(?:at|@)\s+\d.+$", "", rest).strip(" .,-—:")
        if time_m:
            title = title.replace(time_m.group(0), "").strip(" .,-—:")
        if not title or len(title) < 3:
            continue
        events.append({"date": d, "title": title, "time": time_str})
    return events
