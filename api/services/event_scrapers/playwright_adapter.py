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
    """Chubby Pickle uses Elementor + JetEngine's "Listing Grid" widget.
    Each event card is a .jet-listing-grid__item with an inner h2 (title)
    and a date field rendered by .elementor-widget-jet-listing-dynamic-field
    containing a value like "May 24, 2026" or "Friday, May 24".

    The diagnostic confirmed 22 h2 event titles inside
    .elementor-widget-container. Post-render, each card should have BOTH
    a title h2 and a sibling .jet-listing-dynamic-field with the date.
    """
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    today = date.today()
    date_re = re.compile(
        r"(?:(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+)?"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,\s+(\d{4}))?",
        re.I,
    )
    time_re = re.compile(
        r"\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
    )

    # Strategy: walk grid items first; fall back to scanning h2s + adjacent
    # text in the page if the grid selector doesn't return anything.
    cards = soup.select(".jet-listing-grid__item, .jet-listing-grid-item, .jet-engine-listing-overlay-wrap")
    if not cards:
        cards = []
        for h2 in soup.find_all("h2"):
            container = h2.find_parent(class_=re.compile(r"elementor-element"))
            if container:
                cards.append(container)

    for card in cards:
        h2 = card.find("h2")
        if not h2:
            continue
        title = h2.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        if title.lower() in {"upcoming events", "past events", "coming for karaoke?"}:
            continue
        text = card.get_text(" ", strip=True)
        m = date_re.search(text)
        if not m:
            continue
        mon = _MONTHS.get(m.group(1).lower())
        if not mon:
            continue
        day = int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else year
        d = _safe_date(yr, mon, day)
        if not d:
            continue
        parsed = date.fromisoformat(d)
        if not m.group(3) and (parsed - today).days < -180:
            d = _safe_date(yr + 1, mon, day) or d

        tm = time_re.search(text)
        time_str = _normalize_time(tm.group(0)) if tm else None

        key = (d, title.lower())
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": d, "title": title, "time": time_str})
    return events


def parse_donovans_dom(html: str, year: int) -> list[dict]:
    """Donovan's Reef uses a BeatGig embed that injects venue events into
    the calendar page. The DOM after JS render typically contains a list
    of `.bg-event` or similar BeatGig-prefixed elements with title + date.

    First-render selectors we've seen across BeatGig embeds:
      div[class*="bg-event"]      one card per event
      .bg-event__title            band name
      .bg-event__date             date string
      .bg-event__time             time string

    If BeatGig changes their CSS, the fallback regex over the page text
    keeps us reading SOME events even without per-class selectors.
    """
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()

    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    today = date.today()
    date_re = re.compile(
        r"(?:(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,?\s+)?"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,\s+(\d{4}))?",
        re.I,
    )
    time_re = re.compile(
        r"\d{1,2}(?::\d{2})?\s*[APap][Mm](?:\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*[APap][Mm])?",
    )

    cards = soup.select(
        'div[class*="bg-event"], .beatgig-event, .beatgig-calendar-event, '
        '[data-beatgig-event], .gig-card, .event-card'
    )
    for card in cards:
        text = card.get_text(" ", strip=True)
        if not text:
            continue
        # Title: try named subselectors first, else first non-empty <strong>/<h*>.
        title_el = card.select_one(
            '.bg-event__title, .beatgig-event__title, .gig-title, '
            '[class*="title"]'
        )
        title = (title_el.get_text(" ", strip=True) if title_el else "").strip()
        if not title:
            # First short line
            for line in text.split(" | "):
                if 2 <= len(line) <= 60 and not date_re.match(line):
                    title = line.strip()
                    break
        if not title:
            continue

        m = date_re.search(text)
        if not m:
            continue
        mon = _MONTHS.get(m.group(1).lower())
        if not mon:
            continue
        day = int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else year
        d = _safe_date(yr, mon, day)
        if not d:
            continue
        parsed = date.fromisoformat(d)
        if not m.group(3) and (parsed - today).days < -180:
            d = _safe_date(yr + 1, mon, day) or d

        tm = time_re.search(text)
        time_str = _normalize_time(tm.group(0)) if tm else None

        key = (d, title.lower())
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": d, "title": title, "time": time_str})

    return events
