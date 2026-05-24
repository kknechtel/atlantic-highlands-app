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

    Each event renders as:
        <h3>Event Title</h3>
        <p>Sunday May 24th</p>
        <p>7:00 PM - 10:00 PM</p>
        <p>Description (optional)</p>

    The page has no per-event container class — just headings + paragraph
    siblings in the page flow. We walk every <h3>, then look at its next
    siblings for a date-shaped paragraph.

    The earlier version scanned the entire page text with a regex, which
    matched calendar-header strings like "January 1st, 2027" and produced
    610 garbage rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()

    # "Sunday May 24th" / "May 24" / "May 24, 2026"
    date_re = re.compile(
        r"^\s*(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*[,\s]+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,\s+(\d{4}))?\s*$",
        re.I,
    )
    time_re = re.compile(
        r"\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
    )

    for h3 in soup.find_all("h3"):
        title = h3.get_text(" ", strip=True)
        if not title or len(title) < 3:
            continue
        # Skip section headings that aren't actual event titles. SpotApps
        # uses <h3> sparingly so this is mostly safe, but guard anyway.
        if title.lower() in {"events", "upcoming events", "past events", "calendar"}:
            continue

        # Scan the next few siblings for the first date-shaped <p>.
        date_str: str | None = None
        time_str: str | None = None
        for sib in h3.find_next_siblings(limit=6):
            if sib.name == "h3":
                break  # next event starts
            ptxt = sib.get_text(" ", strip=True) if sib.name else ""
            if not ptxt:
                continue
            if date_str is None:
                m = date_re.match(ptxt)
                if m:
                    mon = _MONTHS.get(m.group(1).lower())
                    day = int(m.group(2))
                    yr = int(m.group(3)) if m.group(3) else year
                    if mon:
                        d = _safe_date(yr, mon, day)
                        if d:
                            # Year inference — if the parsed month is more than
                            # 6 months behind today, assume it rolled into next year.
                            today = date.today()
                            parsed = date.fromisoformat(d)
                            if not m.group(3) and (parsed - today).days < -180:
                                d = _safe_date(yr + 1, mon, day) or d
                            date_str = d
                    continue
            if time_str is None:
                tm = time_re.search(ptxt)
                if tm:
                    time_str = _normalize_time(tm.group(0))
            if date_str and time_str:
                break

        if not date_str:
            continue
        key = (date_str, title.lower())
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": date_str, "title": title, "time": time_str})

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
