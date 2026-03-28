#!/usr/bin/env python3
"""Batch AI summarization of all OCR'd documents using Gemini."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from database import SessionLocal
from models.document import Document
from sqlalchemy import func

client = genai.Client(api_key=GEMINI_API_KEY)
cfg = types.GenerateContentConfig(temperature=0.1, max_output_tokens=1000,
    thinking_config=types.ThinkingConfig(thinking_budget=0))
db = SessionLocal()

PROMPT = """Summarize this government document in 2-3 sentences. Include key facts, dates, dollar amounts, and decisions.
Also classify it: doc_type (agenda/minutes/budget/audit/financial_statement/resolution/ordinance/legal/general),
category (town/school/general), and list 3-5 tags.

Return JSON only:
{{"summary": "...", "doc_type": "...", "category": "...", "tags": ["..."]}}

Document filename: {filename}
Text (first 5000 chars):
{text}"""

# Get docs with text but no summary in metadata
docs = db.query(Document).filter(
    func.length(Document.extracted_text) > 100,
    Document.notes.is_(None),
).order_by(Document.created_at.desc()).all()

print(f"Summarizing {len(docs)} documents...")
done = 0; errs = 0

for i, doc in enumerate(docs):
    try:
        text = doc.extracted_text[:5000]
        prompt = PROMPT.format(filename=doc.filename, text=text)
        r = client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=cfg)
        if not r or not r.text: continue

        t = r.text.strip()
        if t.startswith("```"): t = t.split("\n", 1)[1]
        if t.endswith("```"): t = t.rsplit("\n", 1)[0]
        if t.startswith("json"): t = t[4:]

        result = json.loads(t.strip())
        doc.notes = result.get("summary", "")
        if result.get("doc_type") and not doc.doc_type:
            doc.doc_type = result["doc_type"]
        if result.get("category") and not doc.category:
            doc.category = result["category"]
        doc.metadata_ = {**(doc.metadata_ or {}),
            "ai_summary": result.get("summary"),
            "ai_tags": result.get("tags", []),
            "summarized_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        done += 1
        time.sleep(0.3)  # rate limit

    except json.JSONDecodeError:
        errs += 1
    except Exception as e:
        errs += 1
        if errs <= 5: print(f"  ERR: {e}")

    if (i + 1) % 25 == 0:
        db.commit()
        print(f"  {i+1}/{len(docs)} ({done} summarized, {errs} errors)")

db.commit()
db.close()
print(f"\nDONE: {done}/{len(docs)} summarized, {errs} errors")
