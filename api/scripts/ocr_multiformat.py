#!/usr/bin/env python3
"""
Multi-format OCR/text extraction for non-PDF documents.

Handles file types that ocr_all.py (pymupdf-based) can't:
  .docx        → python-docx (paragraphs + table cells)
  .doc         → Gemini Files API (legacy Word, no native Python parser)
  .xlsx/.xlsm  → openpyxl (each sheet as markdown table)
  .xls         → Gemini Files API (legacy Excel)
  .jpg/.png/.jpeg → Gemini Vision (inline_data)
  octet-stream → sniff magic bytes, route accordingly

Skips .mp4 and other non-text formats.

Stores extracted text in documents.extracted_text and updates search_vector.
"""
import io
import logging
import os
import sys
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from sqlalchemy import text as sql_text

from config import GEMINI_API_KEY
from database import SessionLocal
from models.document import Document
from services.s3_service import S3Service

logger = logging.getLogger("ocr_multiformat")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ─── Format detection ────────────────────────────────────────────────────────

def detect_kind(filename: str, content: bytes) -> str:
    """Return one of: pdf, docx, doc, xlsx, xls, image, video, unknown."""
    fn = filename.lower()
    if fn.endswith(".pdf"):
        return "pdf"
    if fn.endswith(".docx"):
        return "docx"
    if fn.endswith(".doc"):
        return "doc"
    if fn.endswith(".xlsx") or fn.endswith(".xlsm"):
        return "xlsx"
    if fn.endswith(".xls"):
        return "xls"
    if fn.endswith(".jpg") or fn.endswith(".jpeg") or fn.endswith(".png"):
        return "image"
    if fn.endswith(".mp4") or fn.endswith(".mov") or fn.endswith(".avi"):
        return "video"
    # Sniff magic bytes for octet-stream uploads
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:4] == b"PK\x03\x04":
        # Could be docx, xlsx, pptx — sniff inside
        return "zip_office"
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        # OLE2: legacy .doc / .xls / .ppt
        return "ole2"
    if content[:3] == b"\xff\xd8\xff":
        return "image"  # JPEG
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    return "unknown"


# ─── Per-format extractors ───────────────────────────────────────────────────

def extract_docx(content: bytes) -> str:
    """python-docx: paragraphs + table cells, in document order."""
    from docx import Document as DocxDocument
    doc = DocxDocument(io.BytesIO(content))
    parts: list[str] = []
    # body iteration preserves order between paragraphs and tables
    for el in doc.element.body.iter():
        tag = el.tag.split("}")[-1]
        if tag == "p":
            txt = "".join(t.text or "" for t in el.iter() if t.tag.split("}")[-1] == "t")
            if txt.strip():
                parts.append(txt)
        elif tag == "tbl":
            # render table as markdown
            rows = []
            for tr in el.iter():
                if tr.tag.split("}")[-1] != "tr":
                    continue
                cells = []
                for tc in tr.iter():
                    if tc.tag.split("}")[-1] != "tc":
                        continue
                    cell_txt = "".join(t.text or "" for t in tc.iter() if t.tag.split("}")[-1] == "t")
                    cells.append(cell_txt.replace("|", "\\|").strip())
                if any(cells):
                    rows.append("| " + " | ".join(cells) + " |")
            if rows:
                parts.append("\n".join(rows))
    return "\n\n".join(parts)


def extract_xlsx(content: bytes) -> str:
    """openpyxl: each non-empty sheet as a markdown table."""
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    parts: list[str] = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            if not any(c is not None and str(c).strip() for c in row):
                continue
            cells = ["" if c is None else str(c).replace("|", "\\|").strip() for c in row]
            rows.append("| " + " | ".join(cells) + " |")
        if rows:
            parts.append(f"## Sheet: {ws.title}\n\n" + "\n".join(rows))
    return "\n\n".join(parts)


def extract_via_gemini(content: bytes, mime_type: str, prompt_extra: str = "") -> str:
    """Last-resort: send the file to Gemini and ask for text."""
    if not GEMINI_API_KEY:
        return ""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = (
        "Extract all text from this file. Preserve structure (headings, lists, "
        "tables as markdown tables). Output ALL text content, no summaries. "
        + prompt_extra
    )
    try:
        if len(content) < 19_000_000:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=content, mime_type=mime_type),
                    prompt,
                ],
            )
        else:
            # Files API for big payloads
            f = client.files.upload(file=io.BytesIO(content),
                                    config=dict(mime_type=mime_type))
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[f, prompt],
            )
        return resp.text or ""
    except Exception as exc:
        logger.warning(f"  gemini extract failed: {exc}")
        return ""


def extract_doc_via_antiword(content: bytes) -> str:
    """Extract text from legacy .doc (OLE2) using antiword.

    Gemini's Files API doesn't accept application/msword. antiword is a small
    binary that's bundled with mingw/git-bash on Windows and apt-installable
    on Linux. mingw's antiword can't read from stdin, so we go via temp file.
    """
    import subprocess, shutil, tempfile
    if not shutil.which("antiword"):
        return ""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tf:
            tf.write(content)
            tmp_path = tf.name
        r = subprocess.run(
            ["antiword", tmp_path],
            capture_output=True, timeout=60,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning(f"  antiword failed: {exc}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return ""


def extract_image(content: bytes, fname: str) -> str:
    """Gemini Vision OCR for images. Tag inferred mime type."""
    fn = fname.lower()
    if fn.endswith(".png"):
        mime = "image/png"
    else:
        mime = "image/jpeg"
    return extract_via_gemini(content, mime,
        "If the image contains a chart, describe the data values shown.")


def extract_one(filename: str, content: bytes) -> Tuple[str, str]:
    """Return (extracted_text, kind_used). Empty text means unrecoverable."""
    kind = detect_kind(filename, content)
    if kind == "pdf":
        # Don't double-handle PDFs here — ocr_all.py owns those.
        return "", "pdf_skipped"
    if kind == "docx" or kind == "zip_office":
        try:
            return extract_docx(content), "docx"
        except Exception as exc:
            logger.warning(f"  python-docx failed ({exc}); falling back to Gemini")
            return extract_via_gemini(
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ), "docx_via_gemini"
    if kind == "doc" or kind == "ole2":
        # Legacy Word (OLE2). Gemini rejects application/msword; use antiword.
        text = extract_doc_via_antiword(content)
        if text and len(text.strip()) > 50:
            return text, "doc_via_antiword"
        return "", "doc_unsupported"
    if kind == "xlsx":
        try:
            return extract_xlsx(content), "xlsx"
        except Exception as exc:
            logger.warning(f"  openpyxl failed ({exc}); falling back to Gemini")
            return extract_via_gemini(
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ), "xlsx_via_gemini"
    if kind == "xls":
        return extract_via_gemini(content, "application/vnd.ms-excel"), "xls_via_gemini"
    if kind == "image":
        return extract_image(content, filename), "image_via_gemini"
    if kind == "video":
        return "", "video_skipped"
    return "", "unknown_skipped"


# ─── Driver ──────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    s3 = S3Service()

    # Find every doc that doesn't have OCR text yet, EXCEPT PDFs (ocr_all.py
    # handles those) and videos (not text). Order by smallest first so the
    # quick wins land first.
    docs = (
        db.query(Document)
        .filter(
            (Document.extracted_text.is_(None))
            | (Document.extracted_text == ""),
        )
        .filter(~Document.filename.ilike("%.pdf"))
        .filter(~Document.filename.ilike("%.mp4"))
        .filter(~Document.filename.ilike("%.mov"))
        .filter(Document.file_size < 19_000_000)
        .order_by(Document.file_size)
        .all()
    )
    logger.info(f"OCRing {len(docs)} non-PDF documents...")

    by_kind: dict[str, int] = {}
    processed = errors = 0
    total_chars = 0

    for i, doc in enumerate(docs):
        try:
            content = s3.download_file(doc.s3_key)
            text, kind = extract_one(doc.filename, content)
            by_kind[kind] = by_kind.get(kind, 0) + 1

            if text and len(text.strip()) > 50:
                text = text.replace("\x00", "")
                # Cap at 1M chars — protects PostgreSQL row size + downstream
                # chunker memory. The full 21M-char NJ DCA UFB Database for
                # all 565 NJ municipalities is preserved in S3; only the
                # representative head + a truncation marker land in the DB.
                if len(text) > 1_000_000:
                    head = text[:990_000]
                    text = head + f"\n\n... [TRUNCATED — original {len(text):,} chars]"
                doc.extracted_text = text
                doc.status = "processed"
                total_chars += len(text)
                db.execute(sql_text(
                    "UPDATE documents SET search_vector = to_tsvector('english', coalesce(:text, '')) "
                    "WHERE id = :id"
                ), {"text": text[:100000], "id": str(doc.id)})
                processed += 1
                if processed % 5 == 0:
                    db.commit()
            else:
                # Mark as no_text but record what we tried (in metadata_)
                doc.status = "no_text"
                doc.extracted_text = ""

            if (i + 1) % 10 == 0:
                db.commit()
                logger.info(f"  {i+1}/{len(docs)} processed ({processed} ok, {errors} err, {total_chars:,} chars)")

        except Exception as exc:
            errors += 1
            logger.warning(f"  [{doc.filename[:50]}] {type(exc).__name__}: {str(exc)[:120]}")

    db.commit()
    db.close()
    logger.info(f"\nDONE: {processed}/{len(docs)} extracted, {errors} errors, "
                f"{total_chars:,} total chars")
    logger.info(f"By kind: {by_kind}")


if __name__ == "__main__":
    main()
