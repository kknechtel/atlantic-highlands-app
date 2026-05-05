"""Scraper routes - trigger and monitor document scraping from town/school websites."""
import asyncio
import logging
import threading
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class ScrapeRequest(BaseModel):
    sites: List[str] | None = None  # ["ahnj", "ecode", "tri"]
    project_id: str | None = None
    dry_run: bool = False


class SiteStats(BaseModel):
    status: str  # pending | running | done | error
    documents_found: int
    documents_uploaded: int
    documents_skipped: int
    errors: int
    started_at: str | None = None
    completed_at: str | None = None


class ScrapeStatusResponse(BaseModel):
    running: bool
    current_site: str | None
    documents_found: int
    documents_uploaded: int
    documents_skipped: int
    errors: List[str]
    started_at: str | None
    completed_at: str | None
    per_site: Dict[str, SiteStats] = {}
    sites_planned: List[str] = []
    sites_completed: List[str] = []


def _run_scraper_in_thread(sites, project_id, user_id, dry_run):
    """Run the async scraper inside its own OS thread + event loop.

    The scraper does long-running synchronous I/O (requests.get with up to
    3 × 30s connect timeouts per URL). Running it on the FastAPI worker's
    event loop via BackgroundTasks blocks the loop and produces 504s for
    every other request. A dedicated thread keeps the request handler
    responsive."""
    from services.scraper.runner import run_scraper
    try:
        asyncio.run(run_scraper(
            sites=sites,
            project_id=project_id,
            user_id=user_id,
            dry_run=dry_run,
        ))
    except Exception:
        logger.exception("Scraper thread crashed")


@router.post("/run")
async def start_scraper(
    req: ScrapeRequest,
    user: User = Depends(get_current_user),
):
    """Start the document scraper in the background."""
    from services.scraper.runner import get_scraper_status

    status = get_scraper_status()
    if status["running"]:
        return {"detail": "Scraper is already running", "status": status}

    threading.Thread(
        target=_run_scraper_in_thread,
        kwargs={
            "sites": req.sites,
            "project_id": req.project_id,
            "user_id": str(user.id),
            "dry_run": req.dry_run,
        },
        daemon=True,
    ).start()

    return {"detail": "Scraper started", "sites": req.sites or ["ahnj", "ecode", "tri"]}


@router.get("/status", response_model=ScrapeStatusResponse)
def get_status(user: User = Depends(get_current_user)):
    """Get current scraper status."""
    from services.scraper.runner import get_scraper_status
    return get_scraper_status()
