"""Scraper routes - trigger and monitor document scraping from town/school websites."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from pydantic import BaseModel

from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class ScrapeRequest(BaseModel):
    sites: List[str] | None = None  # ["ahnj", "ecode", "tri"]
    project_id: str | None = None
    dry_run: bool = False


class ScrapeStatusResponse(BaseModel):
    running: bool
    current_site: str | None
    documents_found: int
    documents_uploaded: int
    documents_skipped: int
    errors: List[str]
    started_at: str | None
    completed_at: str | None


@router.post("/run")
async def start_scraper(
    req: ScrapeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Start the document scraper in the background."""
    from services.scraper.runner import get_scraper_status, run_scraper

    status = get_scraper_status()
    if status["running"]:
        return {"detail": "Scraper is already running", "status": status}

    background_tasks.add_task(
        run_scraper,
        sites=req.sites,
        project_id=req.project_id,
        user_id=str(user.id),
        dry_run=req.dry_run,
    )

    return {"detail": "Scraper started", "sites": req.sites or ["ahnj", "ecode", "tri"]}


@router.get("/status", response_model=ScrapeStatusResponse)
def get_status(user: User = Depends(get_current_user)):
    """Get current scraper status."""
    from services.scraper.runner import get_scraper_status
    return get_scraper_status()
