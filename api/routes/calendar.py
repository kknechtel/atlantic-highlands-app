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
    event_type: str = Query(None, description="'general' (borough) or 'live_music'"),
    city: str = Query(None),
    venue: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get calendar events from the scraped borough calendar + live-music
    venue scrapers. Filterable by year/month and by event_type/city/venue."""
    query = (
        "SELECT id, date, title, time, end_time, location, description, "
        "source, source_url, venue, city, event_type, ticket_url, created_at "
        "FROM calendar_events"
    )
    params = {}
    conditions = []

    if year:
        conditions.append("EXTRACT(YEAR FROM date) = :year")
        params["year"] = year
    if month:
        conditions.append("EXTRACT(MONTH FROM date) = :month")
        params["month"] = month
    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type
    if city:
        conditions.append("city = :city")
        params["city"] = city
    if venue:
        conditions.append("venue = :venue")
        params["venue"] = venue

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date ASC, time ASC NULLS LAST"

    try:
        rows = db.execute(sql_text(query), params).fetchall()
        return [
            {
                "id": str(r.id),
                "date": r.date.isoformat(),
                "title": r.title,
                "time": r.time,
                "end_time": getattr(r, "end_time", None),
                "location": r.location,
                "description": r.description,
                "source": r.source,
                "source_url": r.source_url,
                "venue": getattr(r, "venue", None),
                "city": getattr(r, "city", None),
                "event_type": getattr(r, "event_type", None) or "general",
                "ticket_url": getattr(r, "ticket_url", None),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"Calendar events query failed (table may not exist): {e}")
        return []
