"""Sanity checks for meeting dates parsed from recording filenames.

Town staff name recording files by hand and sometimes mistype the year
("2029.09.09 Council Recording.wma" for the 9/9/2026 meeting). A recording
can't be from the future, so a future date means a typo in the year.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional
from urllib.parse import unquote

# Match a year segment anywhere in a URL path: /2024/, /2024%20Recordings/,
# / 2024 Recordings/. Used as fallback when the filename has no year — many
# Harbor files are like "Harbor Commission 04.07.wma" inside /2020 Recordings/.
_URL_YEAR_RE = re.compile(r"/(20\d{2})(?:%20Recordings|\s+Recordings)?/", re.I)


def year_from_url(url: str) -> Optional[int]:
    m = _URL_YEAR_RE.search(unquote(url))
    return int(m.group(1)) if m else None


def correct_future_date(meeting_date: str, *, url_year: Optional[int] = None,
                        today: Optional[date] = None) -> Optional[str]:
    """Return a corrected YYYY-MM-DD for a future date, or None if it's fine.

    Keeps the month and day and takes the year from the URL path when it has
    one, else the most recent year that puts the date on or before today."""
    today = today or date.today()
    try:
        d = date.fromisoformat(meeting_date)
    except (TypeError, ValueError):
        return None
    if d <= today:
        return None
    years = [url_year] if url_year and url_year <= today.year else []
    years += [today.year, today.year - 1]
    for y in years:
        try:
            fixed = d.replace(year=y)
        except ValueError:  # Feb 29 in a non-leap year
            continue
        if fixed <= today:
            return fixed.isoformat()
    return None
