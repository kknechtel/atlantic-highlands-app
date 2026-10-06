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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# Cap most municipal docs — first N pages have the substantive content.
DEFAULT_MAX_PAGES = 30
# 200 DPI: noticeably better on small-print scans than 150, and we only
# OCR pages whose text layer is missing or garbled.
DEFAULT_DPI = 200
# How many pages to OCR concurrently in-process. Tesseract is CPU-bound, so
# pinning to a few workers avoids context-switching overhead. t3.small has
# 2 vCPU, t3.medium has 2; tune via env if upgrading instance type.
import os
DEFAULT_WORKERS = int(os.environ.get("TESSERACT_WORKERS", "4"))


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


def _render_pages(pdf_bytes: bytes, indexes: List[int], dpi: int) -> List[tuple[bytes, int]]:
    """Render the given 0-based page indexes to PNG bytes via PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF not installed")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: List[tuple[bytes, int]] = []
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    try:
        for p in indexes:
            if p >= len(doc):
                continue
            try:
                pix = doc[p].get_pixmap(matrix=mat)
                out.append((pix.tobytes("png"), p))
            except Exception as exc:
                logger.warning("Failed to render page %d: %s", p + 1, exc)
    finally:
        doc.close()
    return out


def ocr_pages(
    pdf_bytes: bytes,
    indexes: List[int],
    *,
    dpi: int = DEFAULT_DPI,
    workers: int = DEFAULT_WORKERS,
) -> dict[int, str]:
    """OCR specific pages. Returns {page_index: text}; failed pages map to ""."""
    pages = _render_pages(pdf_bytes, indexes, dpi)
    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tesseract") as ex:
        for fut in as_completed([ex.submit(_ocr_one_page, img, num) for img, num in pages]):
            page_num, text = fut.result()
            results[page_num] = text
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
