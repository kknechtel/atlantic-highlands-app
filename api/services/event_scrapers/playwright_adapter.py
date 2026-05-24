"""Playwright adapter — renders JS-heavy venue pages and parses the
post-render DOM.

Use this only for venues that fail with requests + BeautifulSoup
because their events are injected client-side (Chubby Pickle's
JetEngine widget, Donovan's Reef BeatGig embed). The synchronous
Playwright API is fine here — the music scrape runs in its own
process out of the systemd timer, not inside the FastAPI event loop.

Per-venue parsers in this module:
  parse_chubby_pickle_dom   — JetEngine event-list grid
  parse_donovans_dom        — BeatGig venue-calendar embed

Each parser takes the rendered HTML and the current year; returns a
list of partial event dicts. The shared `fetch_events` wrapper drives
Playwright, hands the rendered HTML to the parser, and normalizes the
output into our standard event dict.

Install on prod:
    /opt/atlantic-highlands/api/venv/bin/playwright install --with-deps chromium

That step is idempotent. The browser binary lives in
~/.cache/ms-playwright on the host running it (so under the
ah-scraper systemd user's HOME).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Callable, Optional

from bs4 import BeautifulSoup

from .html_parse import (
    _MONTHS, _safe_date, _normalize_time,
)

logger = logging.getLogger(__name__)

PAGE_TIMEOUT_MS = 25_000      # hard cap on page load
SETTLE_WAIT_MS = 4_000         # extra wait after networkidle for JS-only events
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


ParserFn = Callable[[str, int], list[dict]]


def _render_page(url: str, wait_for_selector: Optional[str] = None) -> Optional[str]:
    """Open the URL in headless Chromium, wait for network idle + selector,
    return the post-render HTML. Returns None on any failure so the
    caller can log + continue."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright not installed; cannot render %s", url)
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1800})
                page = context.new_page()
                page.set_default_timeout(PAGE_TIMEOUT_MS)
                page.goto(url, wait_until="networkidle")
                if wait_for_selector:
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=PAGE_TIMEOUT_MS)
                    except Exception as exc:
                        logger.info("[playwright] selector %r not found on %s: %s",
                                    wait_for_selector, url, exc)
                page.wait_for_timeout(SETTLE_WAIT_MS)
                return page.content()
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("[playwright] render failed for %s: %s", url, exc)
        return None


def fetch_events(
    venue_name: str,
    city: str,
    url: str,
    parser: ParserFn,
    wait_for_selector: Optional[str] = None,
    year_context: Optional[int] = None,
) -> list[dict]:
    html = _render_page(url, wait_for_selector=wait_for_selector)
    if not html:
        return []
    yr = year_context or date.today().year
    try:
        partials = parser(html, yr)
    except Exception as exc:
        logger.exception("[playwright:%s] parser raised: %s", venue_name, exc)
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
            "source": f"playwright:{venue_name}",
            "url": p.get("url") or url,
            "ticket_url": p.get("url"),
            "description": p.get("description"),
        })
    logger.info("[playwright:%s] parsed %d events", venue_name, len(out))
    return out


# ── Per-venue parsers ────────────────────────────────────────────────

def parse_chubby_pickle_dom(html: str, year: int) -> list[dict]:
    """Chubby Pickle's calendar is a JetEngine Calendar widget. Post-render
    each visible day is a .jet-calendar-week__day-wrap div containing:
      - .jet-calendar-week__day-date  (text: "26", "27", …)
      - .jet-calendar-week__day-event (one per event on that day)
          inner text: "Title | 8:30 PM | - 11:59 PM"

    Day numbers wrap across month boundaries (visible week might show
    28, 29, 30, 1, 2, 3, 4). We assume current month for day >= today's
    day, next month for day < today's day. Year follows the month.
    """
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    today = date.today()
    time_re = re.compile(
        r"\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
    )

    for wrap in soup.select(".jet-calendar-week__day-wrap"):
        day_el = wrap.select_one(".jet-calendar-week__day-date")
        if not day_el:
            continue
        day_text = day_el.get_text(strip=True)
        if not day_text.isdigit():
            continue
        day = int(day_text)
        # Pick month — current if day >= today, next month if day < today
        # (visible week often spans the month boundary).
        mon, yr = today.month, today.year
        if day < today.day - 7:  # tolerance: only "rolled into next month"
            mon += 1
            if mon > 12:
                mon = 1
                yr += 1
        d = _safe_date(yr, mon, day)
        if not d:
            continue

        for ev_div in wrap.select(".jet-calendar-week__day-event"):
            text = ev_div.get_text(" | ", strip=True)
            if not text:
                continue
            parts = [p.strip() for p in text.split("|") if p.strip()]
            if not parts:
                continue
            # Title is the first part that isn't a time
            title_parts = []
            time_str = None
            for p in parts:
                if time_str is None and re.match(r"^\s*-?\s*\d{1,2}(?::\d{2})?\s*[APap][Mm]", p):
                    tm = time_re.search(p)
                    if tm:
                        time_str = _normalize_time(tm.group(0))
                    continue
                title_parts.append(p)
            title = " ".join(title_parts).strip()
            if not title or len(title) < 2:
                continue
            key = (d, title.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append({"date": d, "title": title, "time": time_str})
    return events


def parse_donovans_dom(html: str, year: int) -> list[dict]:
    """Donovan's Reef calendar (post-render) uses Squarespace's events
    widget — NOT BeatGig as the venue's embed suggested. Diagnostic
    confirmed:
      .marker                  31 instances, text "Fri | 1" (day name | num)
      .flyoutitem-datetime    108 instances (3x per event: 12hr/24hr/local)
                              text "6:00 PM – 10:00 PM"

    Each marker represents one date (day-of-month integer); events for
    that date attach as siblings/children. The reliable extractor walks
    `.marker` divs and then for each looks at the immediate area for
    flyoutitem groups containing title + datetime.

    The flyoutitem text we have so far gives us only times — title
    extraction needs to look for an event-title element near each
    datetime. Falls back to a generic page-text regex over date
    headings + nearby title text if that doesn't work, so we always
    return SOMETHING.
    """
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    today = date.today()
    time_re = re.compile(
        r"\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
    )

    # Each .marker has its parent that contains the day's events
    for marker in soup.select(".marker"):
        # Marker text is like "Fri | 1" — read the day number
        text = marker.get_text(" ", strip=True)
        day_match = re.search(r"\b(\d{1,2})\b", text)
        if not day_match:
            continue
        day = int(day_match.group(1))
        if not (1 <= day <= 31):
            continue
        # Month/year — assume current month if day >= today, else next month
        mon, yr = today.month, today.year
        if day < today.day - 7:
            mon += 1
            if mon > 12:
                mon, yr = 1, yr + 1
        d = _safe_date(yr, mon, day)
        if not d:
            continue

        # Walk up to a reasonable container — try parent then grandparent.
        container = marker.parent
        for _ in range(3):
            if container is None:
                break
            classes = " ".join(container.get("class") or [])
            # Heuristic: stop when we reach something that looks like a
            # day row or eventlist item
            if any(k in classes for k in ("day", "item", "eventlist", "event")):
                break
            container = container.parent
        if container is None:
            continue

        # Inside the container, look for title + time pairs.
        # Squarespace event widget commonly uses .eventlist-title or h3 for title.
        titles = container.select(
            ".eventlist-title, .flyoutitem-title, .event-title, h3, h4"
        )
        times = container.select(".flyoutitem-datetime--12hr, .eventlist-meta-date, time")

        # Pair them by index — fragile but the cleanest first cut
        for idx, title_el in enumerate(titles):
            title = title_el.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            time_str: Optional[str] = None
            if idx < len(times):
                tm = time_re.search(times[idx].get_text(" ", strip=True))
                if tm:
                    time_str = _normalize_time(tm.group(0))
            key = (d, title.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append({"date": d, "title": title, "time": time_str})

    return events
