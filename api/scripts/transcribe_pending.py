"""Drain the meeting-recording processing queue.

Runs as a systemd timer (`ah-transcribe.timer`). Each invocation:

  1. Transcodes every pending .wma/.wmv recording to .mp3 (fast — ~30s per
     90-min meeting on CPU). Drains ALL pending so playback comes online
     immediately across the whole library.
  2. Transcribes ONE pending recording (slow — roughly 0.2x realtime on
     2 vCPUs with faster-whisper small.en/int8/beam 5, more if the instance
     is out of CPU credits). New recordings first; when none are waiting,
     re-transcribes one whose transcript came from an older model.
  3. Summarizes whatever has a fresh transcript but no summary yet (fast).

Why one transcription per tick: keeps memory steady, lets systemd OOM-kill
or wall-clock cap recover gracefully, and the next tick picks up the next
meeting cleanly. The timer fires again 5 minutes after this run exits.

Why drain transcodes in one pass: they're fast and a backlog of unplayable
recordings is the most user-visible bug. Get playback working first.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

# So `python -m scripts.transcribe_pending` resolves api/ modules from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ah_transcribe_pending")

# Wall-clock cap per run. Without a cap, a stuck Whisper call could pin the
# CPU forever. systemd will also kill via TimeoutStartSec= but we want a
# graceful exit before that.
MAX_RUNTIME_SECONDS = int(os.getenv("TRANSCRIBE_MAX_RUNTIME", "5400"))  # 90 min


def _within_budget(start: float) -> bool:
    return (time.monotonic() - start) < MAX_RUNTIME_SECONDS


def main() -> int:
    from services.meeting_pipeline import (
        fix_future_meeting_dates,
        process_playback_ready, process_summarize, process_transcribe,
        pending_playback_ids, pending_summarize_ids, pending_transcribe_ids,
        pending_upgrade_ids,
        reingest_pending,
    )

    started = time.monotonic()

    # ── 0a. Correct meeting dates with a mistyped future year.
    try:
        n = fix_future_meeting_dates()
        if n:
            logger.info("Corrected %d future-dated recording(s)", n)
    except Exception as e:
        logger.exception("Future-date repair errored: %s", e)

    # ── 0. Re-ingest any recordings that have extracted_text but no chunks
    # (transcript landed but vector pipeline crashed, or text predates the
    # timestamped-text rollout). Fast — no transcription work, just embedding.
    try:
        n = reingest_pending()
        if n:
            logger.info("Re-ingested %d recording(s) into chunks + embeddings", n)
    except Exception as e:
        logger.exception("Re-ingest pass errored: %s", e)

    # ── 1. Transcode all pending playback. Fast — drain everything.
    playback_pending = pending_playback_ids()
    if playback_pending:
        logger.info("Transcoding %d pending audio file(s)", len(playback_pending))
    for mid in playback_pending:
        if not _within_budget(started):
            logger.warning("Time budget exceeded during transcode pass; stopping")
            return 0
        try:
            outcome = process_playback_ready(mid)
            logger.info("Transcode %s → %s", mid, outcome)
        except Exception as e:
            logger.exception("Unhandled error transcoding %s: %s", mid, e)

    # ── 2. Transcribe one. Board of Education first, then town audio (always
    # works from our S3), then other YouTube (frequently blocked from EC2
    # IPs — see comment in services/transcription_service.py::transcribe_youtube).
    if _within_budget(started):
        candidates = pending_transcribe_ids()
        from sqlalchemy import text as sql_text
        from database import SessionLocal
        if candidates:
            db = SessionLocal()
            try:
                rows = db.execute(
                    sql_text(
                        "SELECT id, metadata->'recording'->>'platform' AS p, doc_type "
                        "FROM documents WHERE id::text = ANY(:ids)"
                    ),
                    {"ids": candidates},
                ).fetchall()
                # Keep the newest-first order from pending_transcribe_ids().
                order = {mid: i for i, mid in enumerate(candidates)}
                rows = sorted(rows, key=lambda r: order.get(str(r[0]), 0))
                boe = [str(r[0]) for r in rows if r[2] == "recording_school_board"]
                yt = [str(r[0]) for r in rows if r[1] == "youtube" and r[2] != "recording_school_board"]
                audio = [str(r[0]) for r in rows if r[1] != "youtube" and r[2] != "recording_school_board"]
            finally:
                db.close()

            target = (boe or audio or yt)[0] if (boe or audio or yt) else None
            if target:
                logger.info(
                    "Transcribing 1 of %d pending (boe=%d, audio=%d, yt=%d): %s",
                    len(candidates), len(boe), len(audio), len(yt), target,
                )
                try:
                    outcome = process_transcribe(target)
                    logger.info("Transcribe %s → %s", target, outcome)
                except Exception as e:
                    logger.exception("Unhandled error transcribing %s: %s", target, e)
        else:
            # Nothing new — spend the tick upgrading an old transcript.
            upgrades = pending_upgrade_ids()
            if upgrades:
                target = upgrades[0]
                logger.info(
                    "Re-transcribing 1 of %d older-model transcript(s): %s",
                    len(upgrades), target,
                )
                try:
                    outcome = process_transcribe(target)
                    logger.info("Re-transcribe %s → %s", target, outcome)
                except Exception as e:
                    logger.exception("Unhandled error re-transcribing %s: %s", target, e)

    # ── 3. Summarize anything that has a fresh transcript.
    if _within_budget(started):
        summary_pending = pending_summarize_ids()
        if summary_pending:
            logger.info("Summarizing %d transcript(s)", len(summary_pending))
        for mid in summary_pending:
            if not _within_budget(started):
                logger.warning("Time budget exceeded during summary pass; stopping")
                return 0
            try:
                outcome = process_summarize(mid)
                logger.info("Summarize %s → %s", mid, outcome)
            except Exception as e:
                logger.exception("Unhandled error summarizing %s: %s", mid, e)

    elapsed = int(time.monotonic() - started)
    logger.info("Pipeline tick complete in %ds", elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
