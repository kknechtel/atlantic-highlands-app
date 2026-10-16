"""OCR for image-only PDF pages, by Gemini, for the search index.

The same approach as Techbrig's document classifier (cloud-functions/
document-classifier/extractors.py): the text layer is used where it reads,
and only image-only or garbled pages are sent out, each as a 150 DPI PNG
rendered when a worker is ready for it, so at most WORKERS page images are
in memory. (A page sent as a one-page PDF reads the same but took ~90s per
call against ~1s for the PNG, measured Oct 2026.) Local Tesseract on this
4 GB host held 30 pages at 200 DPI per document and ran the box out of
memory nightly.

Cost: a page is ~260 input tokens; at flash-lite prices a 30-page scan is
about a tenth of a cent. Never raises: a page that fails is simply missing
from the result and the caller marks it unreadable.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from config import GEMINI_API_KEY
from services.llm_models import GEMINI_FLASH_LITE

logger = logging.getLogger(__name__)

OCR_MODEL = os.environ.get("AH_OCR_MODEL", GEMINI_FLASH_LITE)
# Calls are network-bound; a few at once keeps a 100-page scan to a minute or two.
WORKERS = int(os.environ.get("AH_OCR_WORKERS", "4"))
ATTEMPTS = 3
DPI = 150
# A large-format plan at 150 DPI can pass 100 MP; past this it is rendered
# smaller. It is a drawing, not a paragraph.
MAX_PAGE_PIXELS = 20_000_000

PROMPT = """Transcribe this page of a municipal document exactly as printed, for a search index.

- Keep the reading order a person would use (left to right, top to bottom).
- Tables: one row per line, cells separated by " | ". Never drop a column.
- Form fields: "Label: value" on one line each.
- Letterheads, captions, stamps and seals: transcribe verbatim at the top.
- Signatures and handwriting: write them in brackets, e.g. [signed: John Smith].
- Numbers, dates, amounts, names and addresses: copy exactly as printed.
- Illegible or cut-off text: write [illegible] in its place. Never guess.
- No commentary, summary or code fences. Only the page's text."""


def enabled() -> bool:
    return bool(GEMINI_API_KEY)


def _page_png(src, i: int) -> bytes:
    import fitz  # PyMuPDF

    page = src[i]
    zoom = DPI / 72
    area = page.rect.width * page.rect.height * zoom * zoom
    if area > MAX_PAGE_PIXELS:
        zoom *= (MAX_PAGE_PIXELS / area) ** 0.5
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    try:
        return pix.tobytes("png")
    finally:
        del pix


def _ocr_one(png: bytes, page_index: int, filename: str) -> str:
    from google.genai import types

    from services.gemini_json import _get_client
    from services.usage import estimate_cost, record_usage

    cfg = dict(temperature=0, max_output_tokens=8192)
    try:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass
    contents = [
        types.Part.from_bytes(data=png, mime_type="image/png"),
        PROMPT,
    ]
    for attempt in range(ATTEMPTS):
        try:
            resp = _get_client().models.generate_content(
                model=OCR_MODEL, contents=contents, config=types.GenerateContentConfig(**cfg)
            )
        except Exception as exc:
            logger.warning("[gemini_ocr:%s] page %d attempt %d failed: %s",
                           filename, page_index + 1, attempt + 1, exc)
            time.sleep(2 ** attempt)
            continue
        usage = getattr(resp, "usage_metadata", None)
        in_t = int(getattr(usage, "prompt_token_count", 0) or 0)
        out_t = int(getattr(usage, "candidates_token_count", 0) or 0)
        try:
            from database import SessionLocal

            with SessionLocal() as db:
                record_usage(db, source="ocr", model=OCR_MODEL, input_tokens=in_t,
                             output_tokens=out_t,
                             estimated_cost_usd=estimate_cost(OCR_MODEL, in_t, out_t))
        except Exception:
            logger.debug("usage record skipped", exc_info=True)
        text = (getattr(resp, "text", "") or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rsplit("```", 1)[0].strip()
        return text
    return ""


def ocr_pages(pdf_bytes: bytes, indexes: Iterable[int], filename: str = "") -> dict[int, str]:
    """OCR the given 0-based pages. Returns {page_index: text} for the pages
    that came back with text."""
    import fitz  # PyMuPDF

    if not enabled():
        return {}
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        wanted = [i for i in sorted(set(indexes)) if i < len(src)]
        # Rendered under a lock: a PyMuPDF document is not safe to share
        # across threads. The Gemini calls run in parallel.
        lock = threading.Lock()

        def run(i: int) -> tuple[int, str]:
            try:
                with lock:
                    png = _page_png(src, i)
                return i, _ocr_one(png, i, filename)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[gemini_ocr:%s] page %d failed: %s", filename, i + 1, exc)
                return i, ""

        out: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(WORKERS, len(wanted)))) as ex:
            for i, text in ex.map(run, wanted):
                if text:
                    out[i] = text
    finally:
        src.close()
    logger.info("[gemini_ocr:%s] %d/%d page(s) read by %s", filename, len(out), len(wanted), OCR_MODEL)
    return out
