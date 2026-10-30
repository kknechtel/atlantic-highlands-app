"""School district events from the district site's iCal feed.

The feed is the source in sources.json with an `events_ical` path (Edlio
sites publish one at /apps/events/ical/?id=0). Events are stored in
calendar_events with event_type='school'; the calendar API leaves them out
of untyped listings so they don't show up in the community events app.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from municipality import TOWN, sources
from services.scraper.config import USER_AGENT

logger = logging.getLogger(__name__)

EVENT_TYPE = "school"


def _feed_source() -> tuple[Optional[str], Optional[str]]:
    for name, cfg in sources().get("documents", {}).items():
        if cfg.get("events_ical"):
            return name, cfg["base_url"] + cfg["events_ical"]
    return None, None


def _unfold(text: str) -> list[str]:
    """RFC 5545 line unfolding: a line starting with space/tab continues the previous one."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(v: str) -> str:
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\")).strip()


def _clock(dt: datetime) -> str:
    """'7:00 PM' — the format routes/calendar.py sorts on."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _parse_dt(value: str, params: dict[str, str], local: ZoneInfo) -> tuple[date, Optional[datetime]]:
    """Returns (local date, local datetime or None for all-day)."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").date(), None
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    else:
        tz = local
        if params.get("TZID"):
            try:
                tz = ZoneInfo(params["TZID"])
            except Exception:
                pass
        dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tz)
    dt = dt.astimezone(local)
    return dt.date(), dt


def parse_ics(text: str, tz_name: str | None = None) -> list[dict]:
    """VEVENTs as dicts ready for calendar_events. Recurrence rules are not
    expanded — school feeds list each occurrence as its own event."""
    local = ZoneInfo(tz_name or getattr(TOWN, "timezone", None) or "America/New_York")
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
            continue
        if line == "END:VEVENT":
            if cur is not None and cur.get("title") and cur.get("date"):
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *rest = head.split(";")
        params = dict(p.split("=", 1) for p in rest if "=" in p)
        name = name.upper()
        if name == "SUMMARY":
            cur["title"] = _unescape(value)
        elif name == "LOCATION":
            cur["location"] = _unescape(value) or None
        elif name == "DESCRIPTION":
            cur["description"] = _unescape(value)[:2000] or None
        elif name == "URL":
            cur["url"] = value.strip() or None
        elif name == "DTSTART":
            d, dt = _parse_dt(value.strip(), params, local)
            cur["date"], cur["time"] = d, (_clock(dt) if dt else None)
        elif name == "DTEND":
            d, dt = _parse_dt(value.strip(), params, local)
            cur["end_time"] = _clock(dt) if dt else None
    return events


def save(db, events: list[dict], source: str, source_url: str) -> int:
    """Insert events not already stored (same date + title + source)."""
    from sqlalchemy import text as sql_text
    inserted = 0
    for ev in events:
        exists = db.execute(sql_text(
            "SELECT 1 FROM calendar_events WHERE date = :d AND title = :t AND source = :s"
        ), {"d": ev["date"], "t": ev["title"], "s": source}).fetchone()
        if exists:
            continue
        db.execute(sql_text("""
            INSERT INTO calendar_events
                (date, title, time, end_time, location, description, source, source_url, event_type)
            VALUES (:date, :title, :time, :end_time, :location, :description, :source, :url, :etype)
        """), {
            "date": ev["date"], "title": ev["title"], "time": ev.get("time"),
            "end_time": ev.get("end_time"), "location": ev.get("location"),
            "description": ev.get("description"), "source": source,
            "url": ev.get("url") or source_url, "etype": EVENT_TYPE,
        })
        inserted += 1
    db.commit()
    return inserted


def run_school_calendar_scrape(days_back: int = 30) -> dict:
    """Fetch the feed and store events from `days_back` ago onward. Never
    raises, so a failure can't break the nightly scrape it's chained off."""
    name, url = _feed_source()
    if not url:
        return {"scraped": 0, "ok": True, "skipped": "no events_ical source"}
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        if "BEGIN:VCALENDAR" not in resp.text[:500]:
            return {"scraped": 0, "ok": False, "error": "response was not an iCal feed"}
        cutoff = date.today() - timedelta(days=days_back)
        events = [e for e in parse_ics(resp.text) if e["date"] >= cutoff]
        from database import SessionLocal
        db = SessionLocal()
        try:
            inserted = save(db, events, f"{name}_calendar", url)
        finally:
            db.close()
        return {"scraped": len(events), "inserted": inserted, "ok": True}
    except Exception as exc:
        logger.exception("school calendar scrape failed: %s", exc)
        return {"scraped": 0, "ok": False, "error": str(exc)}
