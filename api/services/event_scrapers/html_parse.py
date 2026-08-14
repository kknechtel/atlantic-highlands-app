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

    Real structure (confirmed by debug_proving_ground.py):
        <div class="event-text-holder">
          <h2>Carl Gentry</h2>
          <p>...date + time + description...</p>
        </div>

    Date format: "Sunday May 24th" or similar (no comma between weekday
    and month). Time: "7:00 PM - 10:00 PM" or "1pm-4pm".

    Previous attempts failed because (a) the parser was looking for <h3>
    instead of <h2>, and (b) regex-scanning the whole page text matched
    the empty-calendar-grid filler ("0 events on Friday, December 24th,
    2027") and produced 610 garbage rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()

    # Looser date regex — matches anywhere in the event's text block
    # (not anchored to line start) since SpotApps inlines date + time
    # + description into a single paragraph.
    date_re = re.compile(
        r"(?:(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*[,\s]+)?"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,\s+(\d{4}))?",
        re.I,
    )
    time_re = re.compile(
        r"\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
    )
    today = date.today()

    holders = soup.select("div.event-text-holder, .event-text-holder")
    for holder in holders:
        h2 = holder.find(["h2", "h3"])
        if not h2:
            continue
        title = h2.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        # Skip empty-month placeholder
        if title.lower().startswith("no events"):
            continue

        block = holder.get_text(" ", strip=True)
        d_match = date_re.search(block)
        if not d_match:
            continue
        mon = _MONTHS.get(d_match.group(1).lower())
        if not mon:
            continue
        day = int(d_match.group(2))
        yr = int(d_match.group(3)) if d_match.group(3) else year
        date_str = _safe_date(yr, mon, day)
        if not date_str:
            continue
        # Year rollover when month is well in the past
        parsed = date.fromisoformat(date_str)
        if not d_match.group(3) and (parsed - today).days < -180:
            date_str = _safe_date(yr + 1, mon, day) or date_str

        time_m = time_re.search(block)
        time_str = _normalize_time(time_m.group(0)) if time_m else None

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


def parse_drifthouse(html: str, year: int) -> list[dict]:
    """Drifthouse by David Burke at https://drifthousenj.com/events/.

    Event cards are .ebi-card__content with body text like:
        "Thu, May 28 2026 | Rich and Chad"

    One card per show. Date carries the year explicitly so no rollover
    inference needed.
    """
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()

    # "Thu, May 28 2026" or "Thursday, May 28, 2026"
    date_re = re.compile(
        r"(?:(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+)?"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?[,\s]+(\d{4})",
        re.I,
    )

    for card in soup.select(".ebi-card__content"):
        text = card.get_text(" | ", strip=True)
        if not text:
            continue
        m = date_re.search(text)
        if not m:
            continue
        mon = _MONTHS.get(m.group(1).lower())
        if not mon:
            continue
        date_str = _safe_date(int(m.group(3)), mon, int(m.group(2)))
        if not date_str:
            continue
        # Title = everything after the matched date, stripped of pipe noise
        title = text[m.end():].strip(" |·-—,")
        if not title or len(title) < 2:
            continue
        # Skip private events and other non-music
        if title.lower() in {"private event", "closed", "tba", "tbd"}:
            continue
        key = (date_str, title.lower())
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": date_str, "title": title})

    return events


def parse_sandbox(html: str, year: int) -> list[dict]:
    """The Sandbox at Seastreak homepage at https://sandbox.seastreak.com/.

    Layout (current week only — no separate /events page):
        <div class="event">
          <div class="date">
            <div class="day">23</div>
            <div class="weekday-month">
              <div class="weekday">Saturday</div>
              <div class="month">May</div>
            </div>
          </div>
          <div class="info">
            <div class="music">
              <h3>Music</h3>
              <div class="acts">
                <div class="act type-free|type-cover|type-ticketed">
                  <div class="photo">…</div>
                  <h4>Band Name</h4>
                  <p>6-9pm</p>
                </div>
                ...
              </div>
            </div>
          </div>
        </div>

    The class `type-free|type-cover|type-ticketed` carries the cover
    status. We only emit acts whose title doesn't look like a placeholder
    ("Sandbox Closed Due to Weather" etc).
    """
    soup = BeautifulSoup(html, "html.parser")
    # Photo SVGs are decorative — strip them so .get_text() is clean.
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    today = date.today()

    for ev_div in soup.select("div.event"):
        date_box = ev_div.select_one("div.date")
        if not date_box:
            continue
        day_el = date_box.select_one(".day")
        month_el = date_box.select_one(".month")
        if not (day_el and month_el):
            continue
        try:
            day = int(day_el.get_text(strip=True))
        except ValueError:
            continue
        mon = _MONTHS.get(month_el.get_text(strip=True).lower())
        if not mon:
            continue
        date_str = _safe_date(year, mon, day)
        if not date_str:
            continue
        # Year rollover for past months
        parsed = date.fromisoformat(date_str)
        if (parsed - today).days < -180:
            date_str = _safe_date(year + 1, mon, day) or date_str

        # Acts live under .music .acts (Food trucks go under .food, ignored)
        for act in ev_div.select("div.music div.act"):
            text = act.get_text(" | ", strip=True)
            if not text:
                continue
            parts = [p.strip() for p in text.split("|") if p.strip()]
            if not parts:
                continue
            # First non-time part is the title; a part with am/pm is the time.
            time_str: Optional[str] = None
            title_parts: list[str] = []
            time_re = re.compile(r"^\s*\d{1,2}(?::\d{2})?\s*[-–—]?\s*\d{0,2}(?::\d{2})?\s*[APap][Mm]?", re.I)
            for p in parts:
                if time_re.search(p) and any(c.isdigit() for c in p):
                    time_str = _normalize_time(p)
                else:
                    title_parts.append(p)
            title = " ".join(title_parts).strip(" -·|")
            if not title or len(title) < 2:
                continue
            # Skip closure placeholders and other non-music notices
            low = title.lower()
            if any(k in low for k in ("closed due to", "no music", "tbd", "tba",
                                       "no show", "no event", "weather")):
                continue

            # Event type from the .act class
            act_classes = " ".join(act.get("class") or [])
            etype = "live_music"  # all music acts are live_music for our schema
            cover_note = None
            if "type-cover" in act_classes:
                cover_note = "Cover charge at door"
            elif "type-ticketed" in act_classes:
                cover_note = "Ticketed"
            elif "type-free" in act_classes:
                cover_note = "Free"

            key = (date_str, title.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "date": date_str,
                "title": title,
                "time": time_str,
                "description": cover_note,
            })

    return events


def parse_seafarer(html: str, year: int) -> list[dict]:
    """The Seafarer homepage at https://www.seafarernj.com/.

    The schedule lives in one .sqs-html-content block among several. We
    identify it by date-line density rather than by heading text — see the
    block-selection comment below. Its text looks like:

        LIVE Entertainment + FUN EVENTS SCHEDULE!
        Friday May 22
        Charles Krause 6PM
        Saturday May 23
        Michael Murphy 6PM
        Sunday May 24
        Moroccan Sheepherders 6:30PM
        Monday 25                ← month elided; carry from previous
        Amanda & Nick Duo 2PM

    Lines come in pairs: weekday-date line, then band-line. The
    weekday-date sometimes omits the month (rolls over from a prior
    line); we carry the last seen month forward.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Date-line patterns:
    #   "Friday May 22"            full
    #   "Saturday, May 23"         comma after weekday
    #   "Sun May 24"               abbreviated weekday
    #   "Monday 25"                month elided — carry last month
    date_full = re.compile(
        r"^(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?$",
        re.I,
    )
    date_month_elided = re.compile(
        r"^(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?$",
        re.I,
    )
    time_re = re.compile(
        r"(\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?)",
    )

    def date_line_count(text: str) -> int:
        return sum(
            1 for ln in text.split("\n")
            if date_full.match(ln.strip()) or date_month_elided.match(ln.strip())
        )

    # Pick the schedule block by counting date lines, not by matching a
    # heading. The homepage carries several music-mentioning blocks — a
    # welcome blurb that names only tonight's act, an hours/specials block —
    # and the real lineup is simply whichever holds the most date lines.
    # Heading text has already changed twice ("LIVE MUSIC LINEUP" →
    # "LIVE Entertainment + FUN EVENTS SCHEDULE!"), so keying off it is what
    # left us serving one stale show per season.
    blocks = [b.get_text("\n", strip=True) for b in soup.select(".sqs-html-content")]
    block_text = max(blocks, key=date_line_count, default="")
    if date_line_count(block_text) == 0:
        # No block parsed as a schedule — fall back to whole-page text so a
        # structural restyle degrades instead of returning nothing.
        block_text = soup.get_text("\n", strip=True)
        marker = block_text.upper().find("LIVE MUSIC LINEUP")
        if marker >= 0:
            block_text = block_text[marker:]

    lines = [ln.strip() for ln in block_text.split("\n") if ln.strip()]
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    today = date.today()

    last_month: Optional[int] = None
    pending_date: Optional[str] = None
    for line in lines:
        m_full = date_full.match(line)
        m_short = date_month_elided.match(line)
        if m_full:
            mon = _MONTHS.get(m_full.group(1).lower())
            if not mon:
                continue
            day = int(m_full.group(2))
            d = _safe_date(year, mon, day)
            if not d:
                continue
            parsed = date.fromisoformat(d)
            if (parsed - today).days < -180:
                d = _safe_date(year + 1, mon, day) or d
            last_month = mon
            pending_date = d
        elif m_short and last_month is not None:
            day = int(m_short.group(1))
            d = _safe_date(year, last_month, day)
            if not d:
                continue
            parsed = date.fromisoformat(d)
            if (parsed - today).days < -180:
                d = _safe_date(year + 1, last_month, day) or d
            pending_date = d
        elif pending_date:
            # Band line — title + optional time
            tm = time_re.search(line)
            time_str = _normalize_time(tm.group(1)) if tm else None
            title = (line[:tm.start()] + line[tm.end():]) if tm else line
            title = title.strip(" -–—·,")
            if not title or len(title) < 2:
                pending_date = None
                continue
            key = (pending_date, title.lower())
            if key in seen:
                pending_date = None
                continue
            seen.add(key)
            events.append({"date": pending_date, "title": title, "time": time_str})
            pending_date = None  # consume — one band per date line

    return events
