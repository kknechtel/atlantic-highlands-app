"""Paging and in-document search for the chat's read_document tool.

Extracted text is "## Page N" markdown (see ocr_pipeline), so both helpers
report page numbers. Pure functions — no DB — so they're cheap to test.
"""
from __future__ import annotations

import re
from typing import Optional

from services.query_expansion import amount_variants

_PAGE_MARK = re.compile(r"^## Page (\d+)\s*$")
_MD_HEADING = re.compile(r"^#{1,4}\s+(.+)$")

FIND_MAX_MATCHES = 60
FIND_MAX_CHARS = 15000


def read_window(text: str, offset: int, max_chars: int) -> dict:
    """Return text[offset:offset+max_chars], cut back to a line break when
    one is near the end so rows and sentences aren't split, plus where to
    continue. next_offset is None at the end of the document."""
    total = len(text)
    offset = max(0, min(offset, total))
    end = min(offset + max_chars, total)
    if end < total:
        nl = text.rfind("\n", offset, end)
        if nl > offset + max_chars * 0.8:
            end = nl + 1
    return {
        "offset": offset,
        "excerpt": text[offset:end],
        "total_chars": total,
        "next_offset": end if end < total else None,
        "start_page": _page_at(text, offset),
    }


def _page_at(text: str, pos: int) -> Optional[int]:
    last = None
    for m in re.finditer(r"^## Page (\d+)\s*$", text[:pos + 1], re.M):
        last = int(m.group(1))
    return last


def find_lines(text: str, term: str) -> dict:
    """Every line containing `term` (case-insensitive; dollar figures match
    with or without thousands separators), with its page and the nearest
    heading above it. OCR often splits a label from its amount, so a short
    matching line carries the next line along."""
    needles = [term.lower()] + [v.lower() for v in amount_variants(term)]
    lines = text.splitlines()
    page: Optional[int] = None
    heading: Optional[str] = None
    matches, used, total = [], 0, 0
    for i, raw in enumerate(lines):
        line = raw.strip()
        pm = _PAGE_MARK.match(line)
        if pm:
            page, heading = int(pm.group(1)), None
            continue
        hm = _MD_HEADING.match(line)
        if hm:
            heading = hm.group(1)[:120]
        if not line or not any(n in line.lower() for n in needles):
            continue
        total += 1
        if len(matches) >= FIND_MAX_MATCHES or used >= FIND_MAX_CHARS:
            continue
        shown = line[:300]
        if len(line) < 60 and i + 1 < len(lines) and lines[i + 1].strip():
            shown += " | " + lines[i + 1].strip()[:200]
        matches.append({"page": page, "heading": heading, "line": shown})
        used += len(shown)
    out = {"term": term, "match_count": total, "matches": matches}
    if total > len(matches):
        out["note"] = (f"Showing {len(matches)} of {total} matches. "
                       "Use a more specific term to narrow.")
    elif total == 0:
        out["note"] = "No lines contain that term. Try a shorter or different word."
    return out
