"""Summarize a meeting transcript with Claude.

Produces a structured JSON summary with timestamps so the UI can render
clickable jump points into the audio/video player.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import anthropic

from config import api_key, setting
from municipality import TOWN, entities

logger = logging.getLogger(__name__)

# Haiku: summarizing a transcript into fixed JSON doesn't need a bigger model,
# and at $0.10/$0.50 per MTok a full 2-hour meeting costs under a cent.
# Overridable on the admin Settings screen (SUMMARY_MODEL).
DEFAULT_MODEL = "claude-haiku-5-5"

_BODIES = " or ".join(
    [TOWN.name]
    + [f"{e['abbr']} ({e['label']})" if e.get("abbr") else e["label"] for e in entities() if e.get("kind") == "school"]
)

SYSTEM_PROMPT = """You are a municipal-meeting analyst summarizing a recorded public meeting in __BODIES__.

Output STRICT JSON only, matching this schema:
{
  "tldr": "2-3 sentence plain-language summary",
  "decisions": [{"description": "...", "vote": "5-0" | "passed" | "tabled" | "...", "timestamp_seconds": 0}],
  "action_items": [{"description": "...", "owner": "name or role", "due": "date or null"}],
  "topics": [{"title": "...", "summary": "1-2 sentences", "start_seconds": 0, "end_seconds": 0}],
  "public_comments": [{"speaker": "name if stated, else 'Resident'", "topic": "...", "timestamp_seconds": 0}],
  "ordinances_resolutions": [{"number": "...", "description": "...", "outcome": "adopted|introduced|tabled"}]
}

Rules:
- timestamp_seconds MUST be a float number of seconds from the start of the meeting, derived from the [HH:MM:SS] markers in the input. Never invent timestamps.
- If a field has no content for this meeting, return an empty array (not omit).
- Be terse. Decisions should be one line. Topics should each be 1-2 sentences max.
- Do NOT include any text outside the JSON object.""".replace("__BODIES__", _BODIES)


def _segments_to_prompt(segments: list[dict]) -> str:
    """Render segments as time-stamped lines, capped at MAX_CHARS. The cap
    fits a ~4-hour meeting and keeps the prompt under the 100K-token line
    where Haiku's input price rises."""
    MAX_CHARS = 360_000  # ~90K tokens
    lines: list[str] = []
    total = 0
    for s in segments:
        start = float(s.get("start", 0))
        text = (s.get("text") or "").strip()
        if not text:
            continue
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        sec = int(start % 60)
        line = f"[{h:02d}:{m:02d}:{sec:02d}] {text}"
        if total + len(line) > MAX_CHARS:
            lines.append("... [transcript truncated for length]")
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def summarize_meeting(
    *,
    meeting_body: str,
    meeting_date: Optional[str],
    segments: list[dict],
    raw_text: Optional[str] = None,
) -> dict:
    """Returns a dict matching the SYSTEM_PROMPT schema. Caller persists it."""
    if not api_key("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    if segments:
        transcript_block = _segments_to_prompt(segments)
    else:
        transcript_block = (raw_text or "")[:360_000]

    header = f"Meeting body: {meeting_body}\nMeeting date: {meeting_date or 'unknown'}"
    user_msg = f"{header}\n\n--- Transcript ---\n{transcript_block}"

    client = anthropic.Anthropic(api_key=api_key("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=setting("SUMMARY_MODEL", DEFAULT_MODEL),
        # Haiku 5.5 thinks by default and thinking counts toward max_tokens;
        # 4096 left too little room and could cut the JSON off.
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Summary hit max_tokens before finishing the JSON")

    raw = "".join(
        getattr(block, "text", "") for block in resp.content
        if getattr(block, "type", "") == "text"
    ).strip()

    # Defensive — strip code fences if the model wraps the JSON.
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if m:
        raw = m.group(1)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Claude returned non-JSON summary, attempting recovery: %s", e)
        # Last resort — pick the first {...} block.
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"Could not parse summary JSON: {raw[:400]}")
