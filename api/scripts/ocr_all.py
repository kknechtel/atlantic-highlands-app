#!/usr/bin/env python3
"""
OCR all documents using pymupdf4llm. Fast local extraction, no cloud services needed.
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

db = SessionLocal()
s3 = S3Service()

# Get all unprocessed PDFs
docs = db.query(Document).filter(
    Document.extracted_text.is_(None),
    Document.filename.ilike("%.pdf"),
).order_by(Document.created_at.desc()).all()

print(f"OCR processing {len(docs)} PDF documents...")

processed = 0
errors = 0
total_chars = 0

for i, doc in enumerate(docs):
    try:
        content = s3.download_file(doc.s3_key)
        pdf = pymupdf.open(stream=content, filetype="pdf")
        page_count = pdf.page_count

        # Try pymupdf4llm first (best for native text PDFs)
        try:
            markdown = pymupdf4llm.to_markdown(pdf)
        except Exception:
            markdown = ""

        # Fallback to page-by-page text extraction
        if not markdown or len(markdown.strip()) < 100:
            pages = []
            for p in range(page_count):
                t = pdf[p].get_text()
                if t.strip():
                    pages.append(t)
            markdown = "\n\n---\n\n".join(pages)

        pdf.close()

        if markdown and len(markdown.strip()) > 50:
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

print(f"\nDONE! {processed}/{len(docs)} documents OCR'd, {errors} errors")
print(f"Total extracted text: {total_chars:,} characters")
