"""One-shot backfill: populate documents.department from existing metadata.

For each row where department IS NULL we derive a label using the same
[[detect_department]] helper the live scraper now uses, sourcing from
metadata.source_url (and metadata.recording.meeting_body for recordings).

Idempotent: skips rows that already have a department.

Run:
  python scripts/backfill_department.py
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("backfill_department")


def main() -> int:
    from database import SessionLocal
    from models.document import Document
    from services.scraper.utils import detect_department

    db = SessionLocal()
    try:
        rows = db.query(Document).filter(Document.department.is_(None)).all()
        logger.info("Scanning %d documents without department", len(rows))

        filled = 0
        unmatched: list[tuple[str, str]] = []
        for doc in rows:
            meta = doc.metadata_ or {}
            source_url = meta.get("source_url")
            recording_body = (meta.get("recording") or {}).get("meeting_body")
            dept = detect_department(source_url, recording_body)
            if not dept:
                unmatched.append((doc.filename, source_url or ""))
                continue
            doc.department = dept
            filled += 1

        db.commit()
        logger.info("Backfilled department on %d rows", filled)
        if unmatched:
            logger.info("%d rows had no recoverable department:", len(unmatched))
            for fn, u in unmatched[:20]:
                logger.info("  - %s  (%s)", fn, u)
            if len(unmatched) > 20:
                logger.info("  ... and %d more", len(unmatched) - 20)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
