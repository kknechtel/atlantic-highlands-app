#!/usr/bin/env python3
"""
OCR all documents.

Tier 1 (fast, free): pymupdf4llm — native PDF text extraction, works on any
PDF that has a real text layer. Outputs markdown.

Tier 2 (Gemini fallback): for scanned PDFs where pymupdf4llm yields <50 chars
(typically pre-2010 town budgets that were scanned image-only), call Gemini
2.5 Flash with the PDF as inline_data and ask for markdown extraction. We
chose Gemini over Textract after a head-to-head: Gemini returned 70-95% more
chars per doc and produced proper markdown tables (Textract loses table
structure). Cost is ~$0.01/doc.

Stores extracted text in documents.extracted_text and updates search_vector for FTS.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf
import pymupdf4llm
from sqlalchemy import text as sql_text
from database import SessionLocal
from models.document import Document
from services.s3_service import S3Service
from config import GEMINI_API_KEY

db = SessionLocal()
s3 = S3Service()


def _gemini_ocr(content: bytes) -> str:
    """Tier-2 OCR via Gemini 2.5 Flash.

    Returns extracted markdown or '' if the call failed. Gemini accepts inline
    PDF up to ~20MB; for larger files we'd need the Files API but the scanned
    docs we hit are all under that.
    """
    if not GEMINI_API_KEY:
        return ""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=content, mime_type="application/pdf"),
                "Extract all text from this PDF. Preserve table structure as "
                "markdown tables (with | delimiters). Output ALL text content; "
                "do NOT summarize, paraphrase, or omit anything.",
            ],
        )
        return resp.text or ""
    except Exception as exc:
        print(f"  [gemini-ocr] failed: {exc}")
        return ""

# Get all unprocessed PDFs
docs = db.query(Document).filter(
    Document.extracted_text.is_(None),
    Document.filename.ilike("%.pdf"),
).order_by(Document.created_at.desc()).all()

print(f"OCR processing {len(docs)} PDF documents...")

processed = 0
errors = 0
total_chars = 0

gemini_used = 0

for i, doc in enumerate(docs):
    try:
        content = s3.download_file(doc.s3_key)
        pdf = pymupdf.open(stream=content, filetype="pdf")
        page_count = pdf.page_count

        # Tier 1a: pymupdf4llm markdown
        try:
            markdown = pymupdf4llm.to_markdown(pdf)
        except Exception:
            markdown = ""

        # Tier 1b: per-page get_text fallback
        if not markdown or len(markdown.strip()) < 100:
            pages = []
            for p in range(page_count):
                t = pdf[p].get_text()
                if t.strip():
                    pages.append(t)
            markdown = "\n\n---\n\n".join(pages)

        pdf.close()

        # Tier 2: Gemini fallback for scanned PDFs (image-only, no text layer).
        # Threshold of 50 chars matches the original "no_text" gate; under that
        # the pymupdf path produced nothing useful.
        if (not markdown or len(markdown.strip()) < 50) and len(content) < 19_000_000:
            print(f"  [{i+1}/{len(docs)}] Gemini fallback for {doc.filename[:60]}")
            gem = _gemini_ocr(content)
            if gem and len(gem.strip()) > 50:
                markdown = gem
                gemini_used += 1

        if markdown and len(markdown.strip()) > 50:
            # Strip NUL bytes that break PostgreSQL
            markdown = markdown.replace("\x00", "")
            doc.extracted_text = markdown
            doc.page_count = page_count
            doc.status = "processed"
            total_chars += len(markdown)

            # Update search vector
            db.execute(sql_text(
                "UPDATE documents SET search_vector = to_tsvector('english', coalesce(:text, '')) WHERE id = :id"
            ), {"text": markdown[:100000], "id": str(doc.id)})

            processed += 1
        else:
            doc.page_count = page_count
            doc.status = "no_text"
            doc.extracted_text = ""

        if (i + 1) % 25 == 0:
            db.commit()
            print(f"  Progress: {i+1}/{len(docs)} ({processed} extracted, {errors} errors, {total_chars:,} total chars)")

    except Exception as e:
        errors += 1
        if errors <= 10:
            print(f"  ERR [{doc.filename[:40]}]: {e}")

db.commit()
db.close()

print(f"\nDONE! {processed}/{len(docs)} documents OCR'd, {errors} errors, {gemini_used} via Gemini")
print(f"Total extracted text: {total_chars:,} characters")
