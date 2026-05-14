"""Meeting-recording routes.

Surfaces Documents whose doc_type starts with 'recording_' as Meeting objects,
with endpoints to fetch playable audio/video URLs, kick off transcription
(faster-whisper or YouTube captions), and generate a structured summary.

Phase 1: transcription + summary are synchronous fire-and-forget HTTP calls
that return 202 + the new status. The UI polls /api/meetings/{id} for updates.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import SessionLocal, get_db
from models.document import Document
from models.user import User
from services.s3_service import S3Service

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Models ──────────────────────────────────────────────────────────

class MeetingListItem(BaseModel):
    id: str
    title: str                # human-readable title (filename without prefix)
    meeting_body: str
    meeting_date: Optional[str]
    platform: str             # "audio" | "youtube"
    doc_type: str
    category: str | None
    status: str               # uploaded | transcribed | summarized | failed_*
    has_transcript: bool
    has_summary: bool
    duration_seconds: float | None


class MeetingDetail(MeetingListItem):
    youtube_id: Optional[str]
    audio_url: Optional[str]  # presigned URL for the player when platform=audio
    transcript: Optional[dict] = None  # {engine, language, duration_seconds, segments}
    summary: Optional[dict] = None     # the JSON produced by meeting_summary


# ─── Helpers ─────────────────────────────────────────────────────────

_RECORDING_DOC_TYPES = (
    "recording_council",
    "recording_planning",
    "recording_harbor",
    "recording_school_board",
)


def _is_recording(doc: Document) -> bool:
    if not doc.doc_type:
        return False
    return doc.doc_type.startswith("recording_")


def _recording_meta(doc: Document) -> dict:
    return (doc.metadata_ or {}).get("recording", {}) or {}


def _list_item(doc: Document) -> MeetingListItem:
    meta = _recording_meta(doc)
    transcript = (doc.metadata_ or {}).get("transcript")
    summary = (doc.metadata_ or {}).get("summary")
    return MeetingListItem(
        id=str(doc.id),
        title=doc.filename,
        meeting_body=meta.get("meeting_body") or "Unknown body",
        meeting_date=meta.get("meeting_date"),
        platform=meta.get("platform") or "audio",
        doc_type=doc.doc_type or "recording",
        category=doc.category,
        status=doc.status,
        has_transcript=bool(transcript) or bool(doc.extracted_text),
        has_summary=bool(summary),
        duration_seconds=(transcript or {}).get("duration_seconds"),
    )


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("", response_model=list[MeetingListItem], include_in_schema=False)
@router.get("/", response_model=list[MeetingListItem])
def list_meetings(
    body: Optional[str] = Query(None, description="Filter by meeting body"),
    platform: Optional[str] = Query(None, description="audio | youtube"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Document).filter(Document.doc_type.in_(_RECORDING_DOC_TYPES))
    docs = q.order_by(Document.created_at.desc()).limit(limit * 3).all()  # over-fetch to filter
    items: list[MeetingListItem] = []
    for d in docs:
        item = _list_item(d)
        if body and item.meeting_body != body:
            continue
        if platform and item.platform != platform:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    # Sort: prefer parsed meeting_date desc, fall back to created_at order.
    items.sort(key=lambda x: (x.meeting_date or "", x.title), reverse=True)
    return items


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == meeting_id).first()
    if not doc or not _is_recording(doc):
        raise HTTPException(404, "Meeting not found")

    meta = _recording_meta(doc)
    base = _list_item(doc)
    detail = MeetingDetail(
        **base.model_dump(),
        youtube_id=meta.get("youtube_id"),
        audio_url=None,
        transcript=(doc.metadata_ or {}).get("transcript"),
        summary=(doc.metadata_ or {}).get("summary"),
    )

    if base.platform == "audio":
        try:
            s3 = S3Service()
            detail.audio_url = s3.get_presigned_url(doc.s3_key, expires_in=3600)
        except Exception as e:
            logger.warning("Could not presign audio for %s: %s", meeting_id, e)

    return detail


@router.post("/{meeting_id}/transcribe", status_code=202)
def transcribe_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="Re-transcribe even if a transcript exists"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == meeting_id).first()
    if not doc or not _is_recording(doc):
        raise HTTPException(404, "Meeting not found")
    if not force and (doc.metadata_ or {}).get("transcript"):
        return {"status": "already_transcribed", "id": meeting_id}

    # Mark transcribing optimistically so the UI sees state change immediately.
    doc.status = "transcribing"
    db.commit()
    background_tasks.add_task(_transcribe_in_background, meeting_id)
    return {"status": "transcribing", "id": meeting_id}


@router.post("/{meeting_id}/summarize", status_code=202)
def summarize_meeting_endpoint(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == meeting_id).first()
    if not doc or not _is_recording(doc):
        raise HTTPException(404, "Meeting not found")
    if not (doc.metadata_ or {}).get("transcript") and not doc.extracted_text:
        raise HTTPException(409, "Transcribe the meeting before summarizing")

    doc.status = "summarizing"
    db.commit()
    background_tasks.add_task(_summarize_in_background, meeting_id)
    return {"status": "summarizing", "id": meeting_id}


# ─── Background workers ─────────────────────────────────────────────

def _transcribe_in_background(meeting_id: str) -> None:
    """Pulled out so background_tasks can call it with a fresh DB session."""
    from services.transcription_service import (
        transcribe_audio_bytes, transcribe_youtube,
    )
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == meeting_id).first()
        if not doc:
            logger.warning("Transcribe target %s vanished", meeting_id)
            return
        meta = doc.metadata_ or {}
        rec = meta.get("recording") or {}
        platform = rec.get("platform") or "audio"

        try:
            if platform == "youtube":
                yt_id = rec.get("youtube_id")
                if not yt_id:
                    raise RuntimeError("youtube_id missing from metadata")
                result = transcribe_youtube(yt_id)
            else:
                s3 = S3Service()
                audio_bytes = s3.download_file(doc.s3_key)
                result = transcribe_audio_bytes(audio_bytes, filename_hint=doc.original_filename or doc.filename)
        except Exception as e:
            logger.exception("Transcription failed for %s: %s", meeting_id, e)
            doc.status = "transcription_failed"
            doc.metadata_ = {**(doc.metadata_ or {}), "transcription_error": str(e)[:500]}
            db.commit()
            return

        doc.extracted_text = result.text
        # SQLAlchemy doesn't auto-detect JSONB mutation; reassign so it persists.
        new_meta = {**meta}
        new_meta["transcript"] = result.to_dict()
        new_meta.pop("transcription_error", None)
        doc.metadata_ = new_meta
        doc.status = "transcribed"
        db.commit()
        logger.info("Transcribed meeting %s (%d segments, engine=%s)",
                    meeting_id, len(result.segments), result.engine)

        # Hand off to existing chunk+embed pipeline so chat can search it.
        try:
            from services.ingestion import ingest_document
            ingest_document(db, doc)
        except Exception as e:
            logger.warning("Post-transcribe ingest failed for %s: %s", meeting_id, e)
    finally:
        db.close()


def _summarize_in_background(meeting_id: str) -> None:
    from services.meeting_summary import summarize_meeting as run_summary
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == meeting_id).first()
        if not doc:
            return
        meta = doc.metadata_ or {}
        rec = meta.get("recording") or {}
        transcript = meta.get("transcript") or {}
        segments = transcript.get("segments") or []

        try:
            summary = run_summary(
                meeting_body=rec.get("meeting_body") or "Unknown body",
                meeting_date=rec.get("meeting_date"),
                segments=segments,
                raw_text=doc.extracted_text,
            )
        except Exception as e:
            logger.exception("Summarization failed for %s: %s", meeting_id, e)
            doc.status = "summary_failed"
            doc.metadata_ = {**meta, "summary_error": str(e)[:500]}
            db.commit()
            return

        new_meta = {**meta}
        new_meta["summary"] = summary
        new_meta.pop("summary_error", None)
        doc.metadata_ = new_meta
        doc.status = "summarized"
        db.commit()
        logger.info("Summarized meeting %s", meeting_id)
    finally:
        db.close()
