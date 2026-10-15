"""
Tesseract local OCR — fastest tier of the cascade.

Renders PDF pages to PIL images via PyMuPDF, OCRs them in parallel via
pytesseract. No network round-trips, no API costs, no rate limits.
Quality is "good enough" for keyword/semantic search on municipal docs;
not bank-statement-grade column alignment.

Requires the `tesseract` system binary (apt: tesseract-ocr).
"""
from __future__ import annotations

import io
import logging
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# Cap most municipal docs — first N pages have the substantive content.
DEFAULT_MAX_PAGES = 30
# 200 DPI: noticeably better on small-print scans than 150, and we only
# OCR pages whose text layer is missing or garbled.
DEFAULT_DPI = 200
# How many pages to OCR at once. The API shares this 2-vCPU, 4 GB box, so
# keep it at the vCPU count or below; tune via env if the instance grows.
import os
DEFAULT_WORKERS = int(os.environ.get("TESSERACT_WORKERS", "2"))
# A large-format plan or map at 200 DPI is hundreds of megapixels. Past this
# the page is rendered smaller; it is a drawing, not a paragraph of text.
MAX_PAGE_PIXELS = 20_000_000


@dataclass
class TesseractResult:
    success: bool
    markdown: str = ""
    page_count: int = 0
    processing_time_seconds: float = 0
    error: Optional[str] = None
    estimated_cost: float = 0.0  # always 0 for Tesseract (free)
    pages_ocr_failed: int = 0


def is_tesseract_available() -> bool:
    """Check both the binary and the Python wrapper are present."""
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def _ocr_one_page(img_bytes: bytes, page_num: int) -> tuple[int, str]:
    """OCR a single PNG. Returns (page_num, text)."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        # `--oem 1` = LSTM only (fast, accurate); `--psm 6` = uniform block of text
        text = pytesseract.image_to_string(img, config="--oem 1 --psm 6")
        return page_num, text
    except Exception as exc:
        logger.warning("Tesseract page %d failed: %s", page_num + 1, exc)
        return page_num, ""


def _render_page(doc, p: int, dpi: int) -> Optional[bytes]:
    """One page to PNG bytes, downscaled when it would exceed MAX_PAGE_PIXELS."""
    import fitz  # PyMuPDF

    page = doc[p]
    zoom = dpi / 72
    w, h = page.rect.width * zoom, page.rect.height * zoom
    if w * h > MAX_PAGE_PIXELS:
        zoom *= (MAX_PAGE_PIXELS / (w * h)) ** 0.5
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        png = pix.tobytes("png")
        del pix
        return png
    except Exception as exc:
        logger.warning("Failed to render page %d: %s", p + 1, exc)
        return None


def ocr_pages(
    pdf_bytes: bytes,
    indexes: List[int],
    *,
    dpi: int = DEFAULT_DPI,
    workers: int = DEFAULT_WORKERS,
) -> dict[int, str]:
    """OCR specific pages. Returns {page_index: text}; failed pages map to "".

    Pages are rendered one at a time as workers free up, so at most `workers`
    page images are in memory at once. Rendering everything first held up to
    30 full-resolution pages per document and ran the box out of memory.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed")

    results: dict[int, str] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tesseract") as ex:
            pending = set()
            for p in indexes:
                if p >= len(doc):
                    continue
                if len(pending) >= workers:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for fut in done:
                        page_num, text = fut.result()
                        results[page_num] = text
                png = _render_page(doc, p, dpi)
                if png is None:
                    results[p] = ""
                    continue
                pending.add(ex.submit(_ocr_one_page, png, p))
            for fut in as_completed(pending):
                page_num, text = fut.result()
                results[page_num] = text
    finally:
        doc.close()
    return results


def extract_from_pdf(
    pdf_bytes: bytes,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    dpi: int = DEFAULT_DPI,
    workers: int = DEFAULT_WORKERS,
) -> TesseractResult:
    """OCR the first max_pages pages of a PDF. Synchronous (caller can run via to_thread)."""
    if not is_tesseract_available():
        return TesseractResult(
            success=False,
            error="tesseract binary or pytesseract package not installed",
        )

    start = time.time()
    try:
        results = ocr_pages(pdf_bytes, list(range(max_pages)), dpi=dpi, workers=workers)
    except Exception as exc:
        logger.error("PDF render failed: %s", exc)
        return TesseractResult(success=False, error=f"render_failed: {exc}",
                               processing_time_seconds=time.time() - start)

    if not results:
        return TesseractResult(success=False, error="no_pages_rendered",
                               processing_time_seconds=time.time() - start)

    failed = sum(1 for t in results.values() if not t.strip())
    parts = [f"## Page {p + 1}\n\n{results[p].strip()}"
             for p in sorted(results) if results[p].strip()]
    markdown = "\n\n---\n\n".join(parts)
    elapsed = time.time() - start

    logger.info(
        "Tesseract: %d pages, %d chars, %d failed, %.2fs",
        len(results), len(markdown), failed, elapsed,
    )

    return TesseractResult(
        success=bool(markdown),
        markdown=markdown,
        page_count=len(results),
        processing_time_seconds=elapsed,
        pages_ocr_failed=failed,
    )
