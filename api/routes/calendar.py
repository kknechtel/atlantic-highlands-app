"""Calendar events API - serves scraped borough events and document-derived dates."""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from database import get_db
from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/events")
def get_calendar_events(
    year: int = Query(None),
    month: int = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get calendar events from the scraped borough calendar."""
    query = "SELECT id, date, title, time, location, description, source, source_url, created_at FROM calendar_events"
    params = {}
    conditions = []

    if year:
        conditions.append("EXTRACT(YEAR FROM date) = :year")
        params["year"] = year
    if month:
        conditions.append("EXTRACT(MONTH FROM date) = :month")
        params["month"] = month

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date ASC"

    try:
        rows = db.execute(sql_text(query), params).fetchall()
        return [
            {
                "id": str(r.id),
                "date": r.date.isoformat(),
                "title": r.title,
                "time": r.time,
                "location": r.location,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"Calendar events query failed (table may not exist): {e}")
        return []
