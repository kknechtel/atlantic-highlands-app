"""Two-to-three sentence plain-language headline for an entity's finances.

Conservative by construction: the facts are computed and formatted here, the
model only rewords them, and its output is rejected (falling back to the
template) if it contains any number not in the facts, any judgement word, or
runs long. Results are cached by a hash of the facts, so the model is only
called when the underlying numbers change.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from typing import Optional

import anthropic
from sqlalchemy import text as sql_text

from config import api_key, setting
from services.financial_overview import pct_change
from services.meeting_summary import DEFAULT_MODEL

logger = logging.getLogger(__name__)

MAX_CHARS = 420
# Words that turn a description into a verdict. The page shows numbers and
# the reserve thresholds; whether that is good or bad is the reader's call.
BANNED_WORDS = re.compile(
    r"\b(alarming|concerning|worrying|troubling|healthy|unhealthy|strong|weak|"
    r"excellent|poor|good|bad|risky|dangerous|crisis|significant(ly)?|dramatic(ally)?|"
    r"surg(e|ed|ing)|soar(ed|ing)?|plummet(ed|ing)?|skyrocket(ed|ing)?|"
    r"likely|expected|will|should|because|due to|caused|mismanage\w*)\b",
    re.I,
)
NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s?[MK%]?")

SYSTEM_PROMPT = """You rewrite a short list of facts about a local government's finances into 2-3 plain sentences for residents.

Rules:
- Use ONLY the facts given. Do not add context, causes, comparisons, opinions, praise, criticism or predictions.
- Copy every number exactly as written in the facts (same rounding, same $, M and % symbols). Do not compute new numbers.
- Do not describe anything as good, bad, healthy, concerning, strong or weak.
- No more than 60 words. Plain text only, no lists, no markdown."""


def money(n: float) -> str:
    a = abs(n)
    s = f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a / 1e3:.0f}K" if a >= 1e3 else f"${a:.0f}"
    return f"-{s}" if n < 0 else s


def build_facts(label: str, years: list[dict], reserves_pct: Optional[float]) -> list[str]:
    """Pre-formatted fact sentences for the latest year. Empty if no data."""
    if not years:
        return []
    cur = years[-1]
    prev = years[-2] if len(years) > 1 else None
    fy = cur["fiscal_year"]
    plan = " (budgeted)" if cur["kind"] == "budget" else ""
    facts = []
    if cur.get("expenditures") is not None:
        f = f"{label} spending in FY {fy}{plan} was {money(cur['expenditures'])}"
        ch = pct_change(cur["expenditures"], prev and prev.get("expenditures"))
        if ch is not None:
            f += f", {'up' if ch >= 0 else 'down'} {abs(ch):.1f}% from FY {prev['fiscal_year']}"
        facts.append(f + ".")
    if cur.get("revenue") is not None:
        facts.append(f"Revenue in FY {fy}{plan} was {money(cur['revenue'])}.")
    if reserves_pct is not None:
        facts.append(f"Fund balance equals {reserves_pct:.1f}% of spending.")
    if cur.get("debt") is not None:
        facts.append(f"Total debt was {money(cur['debt'])}.")
    return facts


def template_text(facts: list[str]) -> str:
    return " ".join(facts)


def allowed_numbers(facts: list[str]) -> set[str]:
    return {_norm(m) for f in facts for m in NUMBER.findall(f)}


def _norm(tok: str) -> str:
    return tok.replace(" ", "").rstrip(".,")


def passes_guard(text: str, facts: list[str]) -> bool:
    if not text or len(text) > MAX_CHARS or BANNED_WORDS.search(text):
        return False
    allowed = allowed_numbers(facts)
    return all(_norm(tok) in allowed for tok in NUMBER.findall(text))


def facts_hash(entity_type: str, facts: list[str]) -> str:
    return hashlib.sha256(json.dumps([entity_type, facts]).encode()).hexdigest()[:32]


def cached(db, entity_type: str, h: str) -> Optional[dict]:
    try:
        row = db.execute(sql_text(
            "SELECT text, source FROM entity_headlines WHERE entity_type = :e AND facts_hash = :h"
        ), {"e": entity_type, "h": h}).fetchone()
        return {"text": row[0], "source": row[1]} if row else None
    except Exception as e:
        logger.warning("entity_headlines lookup failed: %s", e)
        db.rollback()
        return None


def rewrite(facts: list[str]) -> tuple[Optional[str], dict]:
    """Ask the model for a rewording. Returns (text or None, usage)."""
    model = setting("SUMMARY_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic(api_key=api_key("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=model,
        # Haiku thinks by default and thinking counts toward max_tokens.
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Facts:\n" + "\n".join(f"- {f}" for f in facts)}],
    )
    usage = {"model": model,
             "input_tokens": getattr(resp.usage, "input_tokens", 0),
             "output_tokens": getattr(resp.usage, "output_tokens", 0)}
    if resp.stop_reason == "max_tokens":
        return None, usage
    text = "".join(getattr(b, "text", "") for b in resp.content
                   if getattr(b, "type", "") == "text").strip()
    return (text if passes_guard(text, facts) else None), usage


_in_flight: set[str] = set()
_lock = threading.Lock()


def generate_and_store(entity_type: str, facts: list[str], h: str) -> None:
    """Background task: reword and cache. A rejected rewording caches the
    template text so the model isn't retried for the same facts."""
    with _lock:
        if h in _in_flight:
            return
        _in_flight.add(h)
    from database import SessionLocal
    from services.usage import record_usage
    db = SessionLocal()
    try:
        text, usage = rewrite(facts)
        record_usage(db, source="financial_headline", model=usage["model"],
                     input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
                     resource_type="entity", resource_id=entity_type)
        source = "ai" if text else "template"
        if not text:
            logger.info("headline rewrite for %s rejected by guard; caching template", entity_type)
        db.execute(sql_text("""
            INSERT INTO entity_headlines (entity_type, facts_hash, text, source)
            VALUES (:e, :h, :t, :s)
            ON CONFLICT (entity_type, facts_hash) DO NOTHING
        """), {"e": entity_type, "h": h, "t": text or template_text(facts), "s": source})
        db.commit()
    except Exception as e:
        logger.warning("headline generation failed for %s: %s", entity_type, e)
    finally:
        db.close()
        with _lock:
            _in_flight.discard(h)


def headline(db, entity_type: str, facts: list[str], background_tasks=None) -> dict:
    """Cached rewording if present, else the template now and a background
    rewrite for next time (when a key is configured)."""
    if not facts:
        return {"text": None, "source": None}
    h = facts_hash(entity_type, facts)
    hit = cached(db, entity_type, h)
    if hit:
        return hit
    if background_tasks is not None and api_key("ANTHROPIC_API_KEY"):
        background_tasks.add_task(generate_and_store, entity_type, facts, h)
    return {"text": template_text(facts), "source": "template"}
