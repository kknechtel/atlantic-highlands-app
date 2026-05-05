"""
Gemini Vision OCR for scanned PDFs.

Tier 1 of the OCR cascade. Renders PDF pages to PNG via PyMuPDF (with
pdf2image fallback) and asks Gemini Flash 2.5 to transcribe each page.
50-way page parallelism via a dedicated ThreadPoolExecutor — Gemini
Flash's rate limits handle this comfortably.

Adapted from bank-processor/api/services/gemini_vision_ocr_service.py.
The bank-statement-specific prompt has been replaced with a municipal
documents prompt (council minutes, budgets, ordinances, etc.).
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    from google import genai
    from google.genai import types
    USING_NEW_GENAI = True
except ImportError:
    import google.generativeai as genai  # type: ignore
    types = None  # type: ignore
    USING_NEW_GENAI = False

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


# Gemini 2.5 Flash pricing
GEMINI_INPUT_COST_PER_TOKEN = 0.15 / 1_000_000
GEMINI_OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000
GEMINI_VISION_TOKENS_PER_IMAGE = 1000  # rough


PROGRESS_CB = Callable[[int, int], Awaitable[None]]


@dataclass
class GeminiVisionResult:
    success: bool
    markdown: str = ""
    page_count: int = 0
    processing_time_seconds: float = 0
    error: Optional[str] = None
    estimated_cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


_OCR_PROMPT = """You are an OCR system transcribing a page from a municipal government document
(could be council meeting minutes, an agenda, a budget, an audit, an ordinance, a resolution,
a CAFR, or correspondence). Output ALL visible text on this page as clean markdown.

RULES:
1. Output ONLY visible text — nothing more, nothing less. Do not add commentary.
2. Use markdown headings (# / ## / ###) for visible heading hierarchy.
3. Use markdown tables for tabular data — preserve column alignment.
4. Use bullet points where the source uses bullets.
5. Preserve numbers EXACTLY as printed: dollar signs, commas, decimals, parentheses for negatives.
6. Preserve dates EXACTLY as printed.
7. Preserve names, titles, and proper nouns EXACTLY — do not "correct" them.
8. Names of council members, board members, employees, and vendors must be transcribed verbatim.
9. Do NOT translate, paraphrase, or summarize.
10. Do NOT generate content that is not visible in the image.
11. If a portion of the page is illegible, write [illegible] in its place.
12. If a footnote or sidebar exists, transcribe it after the main text.

OUTPUT ONLY THE MARKDOWN TEXT — no preamble, no fences, no commentary."""


class GeminiVisionOCR:
    """Gemini-Flash-Vision-backed OCR for PDFs that have no text layer."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        self.model_name = "gemini-2.5-flash"
        # Dedicated executor for blocking SDK calls. 50 workers ≈ Gemini Flash's
        # comfortable concurrency ceiling.
        self._executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="gemini-ocr")

        if USING_NEW_GENAI:
            self.client = genai.Client(api_key=self.api_key)
            self._legacy_model = None
        else:
            genai.configure(api_key=self.api_key)
            self.client = None
            self._legacy_model = genai.GenerativeModel(self.model_name)
        logger.info("GeminiVisionOCR initialized with %s", self.model_name)

    # ── PDF → image rendering ──────────────────────────────────────────

    @staticmethod
    def _page_count(pdf_bytes: bytes) -> int:
        if PYMUPDF_AVAILABLE:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            n = len(doc)
            doc.close()
            return n
        # pdf2image has no cheap page-count, return a high number and let the
        # caller cap it. Worst case: the OCR loop exits when no more images come back.
        return 1000

    @staticmethod
    def _render_range(pdf_bytes: bytes, start: int, end: int, dpi: int = 200) -> List[Tuple[bytes, str, int]]:
        """Render pages [start, end) as PNG bytes. Returns (bytes, fmt, 0-indexed_page)."""
        if PYMUPDF_AVAILABLE:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                actual_end = min(end, len(doc))
                out: List[Tuple[bytes, str, int]] = []
                zoom = dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                for p in range(start, actual_end):
                    pix = doc[p].get_pixmap(matrix=mat)
                    out.append((pix.tobytes("png"), "png", p))
                doc.close()
                return out
            except Exception as exc:
                logger.warning("PyMuPDF render failed: %s — falling back to pdf2image", exc)

        if PDF2IMAGE_AVAILABLE:
            pil_imgs = convert_from_bytes(
                pdf_bytes, dpi=dpi, first_page=start + 1, last_page=end,
            )
            out = []
            for i, img in enumerate(pil_imgs):
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                out.append((buf.getvalue(), "png", start + i))
            return out

        raise RuntimeError("Neither PyMuPDF nor pdf2image is available")

    # ── Per-page OCR call ──────────────────────────────────────────────

    async def _ocr_page(self, image_bytes: bytes, fmt: str, page_num: int) -> Tuple[str, dict]:
        start = time.time()
        try:
            loop = asyncio.get_event_loop()

            if USING_NEW_GENAI:
                contents = [
                    types.Content(parts=[
                        types.Part(inline_data=types.Blob(mime_type=f"image/{fmt}", data=image_bytes)),
                        types.Part(text=_OCR_PROMPT),
                    ])
                ]
                # OCR doesn't need reasoning. We deliberately do NOT pass a
                # thinking_config — different google-genai versions expose
                # different fields on ThinkingConfig (thinking_budget vs
                # thinkingBudget vs no kwarg at all), and "no thinking" is
                # the default behavior on Flash anyway.
                config = types.GenerateContentConfig(
                    temperature=0.0, max_output_tokens=16384,
                )
                response = await loop.run_in_executor(
                    self._executor,
                    lambda: self.client.models.generate_content(
                        model=self.model_name, contents=contents, config=config,
                    ),
                )
                text = response.text if response and response.text else ""
            else:
                import base64
                b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
                response = await loop.run_in_executor(
                    self._executor,
                    lambda: self._legacy_model.generate_content([
                        _OCR_PROMPT,
                        {"mime_type": f"image/{fmt}", "data": b64},
                    ]),
                )
                text = response.text if response and response.text else ""

            elapsed = time.time() - start
            logger.info("OCR p%d: %d chars in %.2fs", page_num + 1, len(text), elapsed)
            return text, {"page": page_num + 1, "elapsed": elapsed,
                          "chars": len(text), "success": True}

        except Exception as exc:
            elapsed = time.time() - start
            logger.error("OCR p%d failed: %s", page_num + 1, exc)
            return "", {"page": page_num + 1, "elapsed": elapsed,
                        "error": str(exc), "success": False}

    # ── Public API ─────────────────────────────────────────────────────

    async def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        dpi: int = 200,
        max_pages: int = 500,
        concurrent_pages: int = 50,
        progress_callback: Optional[PROGRESS_CB] = None,
    ) -> GeminiVisionResult:
        start = time.time()
        try:
            total = self._page_count(pdf_bytes)
            page_count = min(total, max_pages)
            logger.info("PDF has %d pages, OCRing %d", total, page_count)

            if progress_callback:
                try:
                    await progress_callback(0, page_count)
                except Exception:
                    pass

            all_md: List[str] = []
            all_details: List[dict] = []

            for batch_start in range(0, page_count, concurrent_pages):
                batch_end = min(batch_start + concurrent_pages, page_count)
                images = self._render_range(pdf_bytes, batch_start, batch_end, dpi=dpi)
                tasks = [self._ocr_page(b, f, p) for (b, f, p) in images]
                results = await asyncio.gather(*tasks)
                for text, det in results:
                    all_md.append(text)
                    all_details.append(det)
                del images, tasks, results

                if progress_callback:
                    try:
                        await progress_callback(batch_end, page_count)
                    except Exception:
                        pass

                # Tiny breather between batches
                if batch_end < page_count:
                    await asyncio.sleep(0.1)

            empties = [i + 1 for i, t in enumerate(all_md) if not t.strip()]
            if empties:
                logger.warning("OCR empty for pages: %s (of %d)", empties[:20], page_count)

            combined = "\n\n---\n\n".join(
                f"## Page {i + 1}\n\n{t}" for i, t in enumerate(all_md) if t.strip()
            )

            output_chars = sum(d.get("chars", 0) for d in all_details)
            output_toks = output_chars // 4
            input_toks = page_count * GEMINI_VISION_TOKENS_PER_IMAGE
            cost = (input_toks * GEMINI_INPUT_COST_PER_TOKEN
                    + output_toks * GEMINI_OUTPUT_COST_PER_TOKEN)

            return GeminiVisionResult(
                success=bool(combined),
                markdown=combined,
                page_count=page_count,
                processing_time_seconds=time.time() - start,
                estimated_cost=cost,
                input_tokens=input_toks,
                output_tokens=output_toks,
            )
        except Exception as exc:
            logger.error("Gemini Vision OCR failed: %s", exc, exc_info=True)
            return GeminiVisionResult(
                success=False,
                processing_time_seconds=time.time() - start,
                error=str(exc),
            )


# Singleton
_singleton: Optional[GeminiVisionOCR] = None


def get_gemini_vision_ocr() -> GeminiVisionOCR:
    global _singleton
    if _singleton is None:
        _singleton = GeminiVisionOCR()
    return _singleton
