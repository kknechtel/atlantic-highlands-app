"""Landing-page overview for the town or the school district.

One call returns what the home page and the /town and /school hubs show:
latest meetings (with their summaries), ordinances/resolutions, upcoming
calendar events, new documents, and the resident-facing financial picture.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.document import Document
from models.financial import FinancialLineItem, FinancialStatement
from models.user import User
from municipality import TOWN, entities
from routes.documents import _accessible_project_ids
from services import financial_headline, financial_overview as fo

logger = logging.getLogger(__name__)
router = APIRouter()

Entity = Literal["town", "school"]

_MEETING_TYPES = {
    "town": ("recording_council", "recording_planning", "recording_harbor"),
    "school": ("recording_school_board",),
}
_LEGISLATION_DAYS = 180
_UPCOMING_DAYS = 45


def _label(entity: Entity) -> str:
    if entity == "town":
        return TOWN.official_name
    school = next((e for e in entities() if e.get("kind") == "school"), None)
    return school["label"] if school else "School District"


def _short_label(entity: Entity) -> str:
    if entity == "town":
        return TOWN.name
    school = next((e for e in entities() if e.get("kind") == "school"), None)
    return (school.get("abbr") or school["short"]) if school else "District"


def _meetings(db: Session, entity: Entity, limit: int) -> list[dict]:
    meta = Document.metadata_
    meeting_date = meta["recording"]["meeting_date"].astext
    rows = (
        db.query(Document.id, Document.filename, meta["recording"], meta["summary"])
        .filter(Document.doc_type.in_(_MEETING_TYPES[entity]))
        .order_by(meeting_date.desc().nullslast(), Document.created_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for doc_id, filename, rec, summary in rows:
        rec, summary = rec or {}, summary or {}
        out.append({
            "id": str(doc_id),
            "title": filename,
            "body": rec.get("meeting_body") or "Meeting",
            "date": rec.get("meeting_date"),
            "has_summary": bool(summary),
            "tldr": summary.get("tldr"),
            "decisions": [
                {"description": d.get("description"), "vote": d.get("vote")}
                for d in (summary.get("decisions") or [])[:4] if d.get("description")
            ],
            "legislation": [
                {"number": o.get("number"), "description": o.get("description"), "outcome": o.get("outcome")}
                for o in (summary.get("ordinances_resolutions") or []) if o.get("description")
            ],
        })
    return out


def _legislation(meetings: list[dict]) -> list[dict]:
    """Ordinances/resolutions from recent summarized meetings, newest first.
    A numbered item keeps only its most recent status (introduced → adopted)."""
    cutoff = (date.today() - timedelta(days=_LEGISLATION_DAYS)).isoformat()
    seen, out = set(), []
    for m in meetings:
        if not m["date"] or m["date"] < cutoff:
            continue
        for item in m["legislation"]:
            key = (item["number"] or "").strip().lower() or item["description"].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({**item, "meeting_id": m["id"], "meeting_body": m["body"], "meeting_date": m["date"]})
    return out


def _upcoming(db: Session, entity: Entity) -> list[dict]:
    type_filter = ("event_type = 'school'" if entity == "school"
                   else "event_type IS DISTINCT FROM 'school' AND event_type IS DISTINCT FROM 'live_music'")
    try:
        rows = db.execute(sql_text(f"""
            SELECT id, date, title, time, location, source_url, event_type FROM calendar_events
            WHERE date >= CURRENT_DATE AND date <= CURRENT_DATE + :days AND {type_filter}
            ORDER BY date, title LIMIT 8
        """), {"days": _UPCOMING_DAYS}).fetchall()
    except Exception as e:  # table is created by the first events scrape
        logger.warning("overview: calendar query failed: %s", e)
        db.rollback()
        return []
    return [{"id": str(r.id), "date": r.date.isoformat(), "title": r.title, "time": r.time,
             "location": r.location, "url": r.source_url, "event_type": r.event_type} for r in rows]


def _documents(db: Session, entity: Entity, user: User) -> list[dict]:
    q = db.query(Document).filter(Document.category == entity,
                                  ~Document.doc_type.like("recording_%"))
    accessible = _accessible_project_ids(db, user)
    if accessible is not None:
        q = q.filter(Document.project_id.in_(accessible)) if accessible else q.filter(False)
    docs = q.order_by(Document.created_at.desc()).limit(6).all()
    return [{"id": str(d.id), "title": d.title or d.filename, "doc_type": d.doc_type,
             "department": d.department,
             "created_at": d.created_at.isoformat() if d.created_at else None} for d in docs]


def _finances(db: Session, entity: Entity, background_tasks: BackgroundTasks) -> dict:
    stmts = db.query(FinancialStatement).filter(FinancialStatement.entity_type == entity).all()
    years = fo.yearly_series(stmts)
    profile_about = getattr(TOWN, "about", None) or {}
    trend_note = profile_about.get("school_trend_note") if entity == "school" else None
    if not years:
        return {"years": [], "latest": None, "headline": {"text": None, "source": None},
                "trend_note": trend_note}

    latest = years[-1]
    prev = years[-2] if len(years) > 1 else None
    reserves = fo.reserves(latest, entity)
    facts = financial_headline.build_facts(_short_label(entity), years,
                                           reserves["pct"] if reserves else None)
    by_id = {str(s.id): s for s in stmts}
    latest_stmt = by_id[latest["statement_id"]]
    flags, line_flag_count = fo.plain_flags(latest_stmt.anomaly_flags)
    items = db.query(FinancialLineItem).filter(FinancialLineItem.statement_id == latest_stmt.id).all()
    source_doc = db.query(Document.title, Document.filename).filter(Document.id == latest_stmt.document_id).first()

    return {
        "years": years,
        "latest": latest,
        "changes": {k: fo.pct_change(latest[k], prev and prev[k])
                    for k in ("revenue", "expenditures", "fund_balance", "debt")},
        "previous_year": prev["fiscal_year"] if prev else None,
        "reserves": reserves,
        "headline": financial_headline.headline(db, entity, facts, background_tasks),
        "flags": flags,
        "line_flag_count": line_flag_count,
        "top_lines": fo.top_lines(items),
        "source": {
            "document_id": latest["document_id"],
            "statement_id": latest["statement_id"],
            "statement_type": latest["statement_type"],
            "title": (source_doc.title or source_doc.filename) if source_doc else None,
        },
        "accounting_basis": latest_stmt.accounting_basis,
        "trend_note": trend_note,
    }


@router.get("/{entity}")
def get_overview(
    entity: Entity,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meetings = _meetings(db, entity, limit=40)
    about = (getattr(TOWN, "about", None) or {}).get(entity)
    return {
        "entity": entity,
        "label": _label(entity),
        "short_label": _short_label(entity),
        "about": about,
        "meetings": meetings[:5],
        "legislation": _legislation(meetings)[:12],
        "upcoming": _upcoming(db, entity),
        "documents": _documents(db, entity, user),
        "finances": _finances(db, entity, background_tasks),
    }
