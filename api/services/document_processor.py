"""
Document processing pipeline.
OCR extraction, AI summarization, and auto-tagging for imported documents.
"""
import logging
import asyncio
import json
from typing import Optional, Dict
from datetime import datetime

from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)


async def process_document(document_id: str):
    """
    Full document processing pipeline:
    1. Extract text via OCR (PyMuPDF)
    2. AI summarization and auto-tagging
    3. Update document record with extracted data
    """
    from database import SessionLocal
    from models.document import Document
    from services.s3_service import S3Service

    db = SessionLocal()
    s3 = S3Service()

    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        # Skip non-PDFs for now
        if not doc.filename.lower().endswith(".pdf"):
            doc.status = "processed"
            db.commit()
            return

        doc.status = "processing"
        db.commit()

        # Step 1: Extract text
        logger.info(f"[{doc.filename}] Extracting text...")
        content = s3.download_file(doc.s3_key)
        text = await extract_text_from_pdf(content)

        if not text or len(text.strip()) < 50:
            logger.warning(f"[{doc.filename}] Minimal text extracted ({len(text or '')} chars)")
            doc.status = "processed"
            doc.metadata_ = {**(doc.metadata_ or {}), "text_length": len(text or ""), "extraction": "minimal"}
            db.commit()
            return

        # Store extracted text length
        text_preview = text[:500] if text else ""

        # Step 2: AI summarization and tagging
        logger.info(f"[{doc.filename}] Running AI analysis ({len(text)} chars)...")
        analysis = await analyze_document(text, doc.filename)

        if analysis:
            # Update document with AI results
            if analysis.get("doc_type") and not doc.doc_type:
                doc.doc_type = analysis["doc_type"]
            if analysis.get("category") and not doc.category:
                doc.category = analysis["category"]
            if analysis.get("fiscal_year") and not doc.fiscal_year:
                doc.fiscal_year = analysis["fiscal_year"]
            if analysis.get("department") and not doc.department:
                doc.department = analysis.get("department")

            doc.metadata_ = {
                **(doc.metadata_ or {}),
                "text_length": len(text),
                "text_preview": text_preview,
                "ai_summary": analysis.get("summary", ""),
                "ai_tags": analysis.get("tags", []),
                "ai_entities": analysis.get("entities", []),
                "ai_date_references": analysis.get("date_references", []),
                "processed_at": datetime.utcnow().isoformat(),
                "extraction_model": analysis.get("model", "unknown"),
            }
            if analysis.get("summary") and not doc.notes:
                doc.notes = analysis["summary"]

        doc.status = "processed"
        db.commit()
        logger.info(f"[{doc.filename}] Processing complete")

    except Exception as e:
        logger.error(f"Document processing failed for {document_id}: {e}", exc_info=True)
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = "error"
                doc.metadata_ = {**(doc.metadata_ or {}), "error": str(e)}
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def extract_text_from_pdf(content: bytes) -> Optional[str]:
    """Extract text from PDF using PyMuPDF."""
    try:
        import pymupdf
        doc = pymupdf.open(stream=content, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text)
        doc.close()

        if pages:
            return "\n\n---\n\n".join(pages)

        # If no text found, try pymupdf4llm for better extraction
        try:
            import pymupdf4llm
            doc = pymupdf.open(stream=content, filetype="pdf")
            markdown = pymupdf4llm.to_markdown(doc)
            doc.close()
            return markdown
        except Exception:
            pass

        return None
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return None


async def analyze_document(text: str, filename: str) -> Optional[Dict]:
    """Use AI to summarize, tag, and classify a document."""
    # Truncate text for API limits
    text_for_ai = text[:30000]

    prompt = f"""Analyze this government document and provide structured metadata.

Filename: {filename}

Document text:
{text_for_ai}

Respond with ONLY a JSON object:
{{
  "summary": "2-3 sentence summary of the document's purpose and key content",
  "doc_type": "one of: agenda, minutes, budget, audit, financial_statement, resolution, ordinance, legal, records_request, presentation, planning, performance_report, general",
  "category": "one of: town, school, general",
  "fiscal_year": "YYYY or YYYY-YYYY or null",
  "department": "department name or null",
  "tags": ["list", "of", "relevant", "tags"],
  "entities": ["key people, organizations, or places mentioned"],
  "date_references": ["important dates mentioned in the document"]
}}"""

    # Try Gemini first (faster, cheaper)
    if GEMINI_API_KEY:
        try:
            return await _analyze_with_gemini(prompt)
        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e}")

    # Fallback to Claude
    if ANTHROPIC_API_KEY:
        try:
            return await _analyze_with_claude(prompt)
        except Exception as e:
            logger.warning(f"Claude analysis failed: {e}")

    return None


def _record_doc_processor_usage(model: str, in_t: int, out_t: int) -> None:
    if not (in_t or out_t):
        return
    try:
        from database import SessionLocal
        from services.usage import record_usage
        sess = SessionLocal()
        try:
            record_usage(
                sess, source="document_processor", model=model,
                input_tokens=in_t, output_tokens=out_t,
            )
        finally:
            sess.close()
    except Exception:
        pass


async def _analyze_with_gemini(prompt: str) -> Optional[Dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=2000,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        ),
    )

    if response and response.text:
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            _record_doc_processor_usage(
                "gemini-2.5-flash",
                int(getattr(usage, "prompt_token_count", 0) or 0),
                int(getattr(usage, "candidates_token_count", 0) or 0),
            )
        return _parse_json(response.text, "gemini")
    return None


async def _analyze_with_claude(prompt: str) -> Optional[Dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        ),
    )

    if response and response.content:
        _record_doc_processor_usage(
            "claude-sonnet-4-20250514",
            getattr(response.usage, "input_tokens", 0) or 0,
            getattr(response.usage, "output_tokens", 0) or 0,
        )
        return _parse_json(response.content[0].text, "claude")
    return None


def _parse_json(text: str, model: str) -> Optional[Dict]:
    """Parse JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0] if "\n" in text else text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    try:
        result = json.loads(text)
        result["model"] = model
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI analysis JSON: {e}")
        return None
