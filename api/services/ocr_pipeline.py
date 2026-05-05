"""
OCR pipeline cascade.

Two-tier strategy for converting a PDF's bytes into clean markdown text:

  1. pdfplumber          — instant, free, native text-layer extraction
  2. Gemini Vision OCR   — pages → PNG → Gemini Flash 2.5 vision

Falls forward to the next tier when the previous tier returns no/short
text. The bank-processor has a 3rd Textract tier; we omit it for now —
Gemini Vision covers virtually all municipal scanned PDFs and avoids
the Lambda + Textract infra setup. Easy to add later if needed.

Adapted from bank-processor/api/services/pipeline/ocr.py.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

PROGRESS_CB = Callable[[int, int], Awaitable[None]]


@dataclass
class OCRResult:
    success: bool
    markdown: str = ""
    page_count: int = 0
    tier: str = ""              # "pdfplumber" | "gemini_vision" | "none"
    processing_time_ms: float = 0
    estimated_cost: float = 0.0
    error: Optional[str] = None


# Below this many chars we treat the pdfplumber result as "didn't really work"
# and fall through to Gemini Vision. Municipal docs vary widely — a 1-page
# resolution might legitimately have only a few hundred characters — but if
# pdfplumber thought the doc was text-based and yields < this many chars,
# the text layer is probably broken (e.g. CID-encoded text). 300 is a good
# floor across our corpus.
MIN_USEFUL_CHARS = 300


async def extract_pdf_to_markdown(
    pdf_bytes: bytes,
    filename: str = "",
    progress_callback: Optional[PROGRESS_CB] = None,
) -> OCRResult:
    """Run the OCR cascade on a PDF and return clean markdown.

    Tier 1 (pdfplumber) runs first. If it returns substantive text (the
    PDF has a usable text layer), we stop there. Otherwise Tier 2 (Gemini
    Vision) renders + OCRs every page.
    """
    start = time.time()

    # ── Tier 1: pdfplumber ────────────────────────────────────────────
    try:
        from services.pdfplumber_service import extract_text as plumber
        plumber_result = plumber(pdf_bytes)
        if (plumber_result.success and plumber_result.markdown
                and plumber_result.chars_extracted >= MIN_USEFUL_CHARS):
            elapsed = (time.time() - start) * 1000
            logger.info(
                "[OCR:%s] pdfplumber: %d pages, %d chars, %d tables, %.0fms (free)",
                filename, plumber_result.page_count, plumber_result.chars_extracted,
                plumber_result.tables_found, elapsed,
            )
            return OCRResult(
                success=True,
                markdown=plumber_result.markdown,
                page_count=plumber_result.page_count,
                tier="pdfplumber",
                processing_time_ms=elapsed,
                estimated_cost=0.0,
            )
        # Either short or scanned — fall through.
        if not plumber_result.is_text_based:
            logger.info("[OCR:%s] no text layer, falling through to Gemini Vision", filename)
        else:
            logger.info(
                "[OCR:%s] pdfplumber returned only %d chars — falling through to Gemini Vision",
                filename, plumber_result.chars_extracted,
            )
    except ImportError:
        logger.debug("[OCR:%s] pdfplumber not installed", filename)
    except Exception as exc:
        logger.warning("[OCR:%s] pdfplumber error: %s", filename, exc)

    # ── Tier 2: Gemini Vision ─────────────────────────────────────────
    try:
        from services.gemini_vision_ocr import get_gemini_vision_ocr
        gemini = get_gemini_vision_ocr()
        result = await gemini.extract_from_pdf(pdf_bytes, progress_callback=progress_callback)
        elapsed = (time.time() - start) * 1000
        if result.success and result.markdown:
            logger.info(
                "[OCR:%s] Gemini Vision: %d pages, %d chars, %.0fms, $%.4f",
                filename, result.page_count, len(result.markdown), elapsed, result.estimated_cost,
            )
            return OCRResult(
                success=True,
                markdown=result.markdown,
                page_count=result.page_count,
                tier="gemini_vision",
                processing_time_ms=elapsed,
                estimated_cost=result.estimated_cost,
            )
        logger.warning("[OCR:%s] Gemini returned no usable text: %s", filename, result.error)
    except ValueError as exc:
        # GEMINI_API_KEY not configured — clear error for the operator
        logger.error("[OCR:%s] Gemini Vision unavailable: %s", filename, exc)
        return OCRResult(success=False, tier="none",
                         processing_time_ms=(time.time() - start) * 1000,
                         error=str(exc))
    except Exception as exc:
        logger.error("[OCR:%s] Gemini Vision failed: %s", filename, exc, exc_info=True)
        return OCRResult(success=False, tier="none",
                         processing_time_ms=(time.time() - start) * 1000,
                         error=str(exc))

    return OCRResult(
        success=False, tier="none",
        processing_time_ms=(time.time() - start) * 1000,
        error="All OCR tiers failed",
    )
