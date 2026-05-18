#!/usr/bin/env python3
"""
Extract financial data from the 21 NJ DOE school ACFRs (AHSD/0130, HHRS/2120,
HSD/2160 x FY18-24) into financial_statements + financial_line_items.

Unlike the older scripts/extract_financials.py, this one:
  - keys by document_id (no dedup by category/fy), so all 21 districts/years survive
  - threads the entity_name + district_code through from documents.metadata
  - tags each row as GAAP + school_year + predecessor_entity (per the
    financial.py model docstring's HHRSD consolidation note: HHRSD was formed
    7/1/2024 from AHSD/HHRS/HSD — historical values can't be summed across the
    predecessors)
  - reads documents.extracted_text (already OCR'd) instead of re-OCRing each
    time, which is faster and avoids depending on pymupdf for this run
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from database import SessionLocal
from models.document import Document
from models.financial import FinancialStatement, FinancialLineItem

client = genai.Client(api_key=GEMINI_API_KEY)
cfg = types.GenerateContentConfig(
    temperature=0.1,
    max_output_tokens=65000,
    thinking_config=types.ThinkingConfig(thinking_budget=0),
)
db = SessionLocal()

PROMPT = """You are a municipal finance expert. Extract ALL financial data from this NJ school district ACFR (Annual Comprehensive Financial Report).

Entity (per source metadata): {entity}
District code (NJ DOE):       {dist}
Fiscal year (reported):       {fy}  (NJ school fiscal year ends June 30)

<DOCUMENT>
{markdown}
</DOCUMENT>

Return JSON ONLY (no markdown fences, no commentary). Use the entity_name found INSIDE the document — should match "{entity}" but trust the document.

{{
  "entity_name":"...",
  "fiscal_year":"YYYY",
  "income_statement":{{
    "total_revenue":null,"property_tax_revenue":null,"state_aid":null,"federal_aid":null,
    "miscellaneous_revenue":null,"other_revenue":null,
    "total_expenditures":null,"salaries_wages":null,"other_expenses":null,
    "capital_improvements":null,"debt_service":null,"surplus_deficit":null,
    "revenue_line_items":[{{"name":"...","amount":0,"prior_year":null}}],
    "expenditure_line_items":[{{"name":"...","amount":0,"prior_year":null,"budget":null}}]
  }},
  "balance_sheet":{{
    "total_assets":null,"cash_and_investments":null,"receivables":null,
    "total_liabilities":null,"accounts_payable":null,"bonds_payable":null,
    "total_fund_balance":null,"unreserved_fund_balance":null,"reserved_fund_balance":null
  }},
  "debt":{{
    "total_outstanding_debt":null,"bonds_outstanding":null,"notes_outstanding":null,
    "annual_debt_service":null
  }},
  "enrollment":{{"adm":null,"pupil_count":null}},
  "per_pupil":{{"total_spending_per_pupil":null,"instructional_salaries_per_pupil":null}}
}}

CRITICAL: Extract REAL dollar amounts from the document. Do NOT return 0 unless the document says 0.
For NJ school ACFRs, the General Fund (Fund 11) figures are the primary "total revenue/expenditures";
include Special Revenue (Fund 20), Capital Projects (Fund 30), and Debt Service (Fund 40) if reported.
"""

# Map district code -> (entity_name, predecessor_entity_tag). Per memory:
# HHRSD consolidated 2024-07-01, so FY24 (ends 2024-06-30) is the last year of
# the predecessors. All three districts in our corpus are "predecessor" rows.
DISTRICTS = {
    "0130": ("Atlantic Highlands School District", "AHSD"),
    "2120": ("Henry Hudson Regional School District", "HHRS"),
    "2160": ("Highlands School District", "HSD"),
}


def main():
    docs = (
        db.query(Document)
        .filter(Document.doc_type == "audit", Document.category == "school")
        .filter(Document.extracted_text.isnot(None))
        .order_by(Document.fiscal_year, Document.filename)
        .all()
    )
    docs = [d for d in docs if d.extracted_text and len(d.extracted_text) > 1000]
    print(f"Extracting {len(docs)} school ACFRs...")

    count = 0
    for doc in docs:
        fy = (doc.fiscal_year or "")[:4]
        dist = (doc.metadata_ or {}).get("district_code", "?")
        entity_default, predecessor = DISTRICTS.get(dist, ("Unknown", None))
        entity_for_prompt = (doc.metadata_ or {}).get("entity_name") or entity_default

        print(f"\nFY{fy} dist={dist} ({entity_default}): {doc.filename}")

        # Truncate to fit Gemini's input window comfortably. ACFRs vary 200-630k
        # chars; the financial section is in the first 60-80% of the doc so
        # truncation at 90k keeps the key statements without exhausting tokens.
        markdown = (doc.extracted_text or "")[:90000]
        if len(markdown) < 1000:
            print("  SKIP: extracted_text too short")
            continue

        prompt = PROMPT.format(entity=entity_for_prompt, dist=dist, fy=fy, markdown=markdown)

        try:
            r = client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt, config=cfg
            )
            if not r or not r.text:
                print("  EMPTY response")
                continue

            text = r.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("\n", 1)[0]
            if text.startswith("json"):
                text = text[4:]
            result = json.loads(text.strip())

            inc = result.get("income_statement", {}) or {}
            bs = result.get("balance_sheet", {}) or {}
            debt = result.get("debt", {}) or {}

            # Key by document_id so each ACFR gets its own row
            existing = (
                db.query(FinancialStatement)
                .filter(FinancialStatement.document_id == doc.id)
                .first()
            )
            if existing:
                stmt = existing
                db.query(FinancialLineItem).filter(
                    FinancialLineItem.statement_id == stmt.id
                ).delete()
            else:
                stmt = FinancialStatement(
                    document_id=doc.id,
                    entity_type="school",
                    statement_type="acfr",
                    fiscal_year=fy,
                )
                db.add(stmt)

            stmt.entity_name = result.get("entity_name") or entity_default
            stmt.accounting_basis = "gaap"
            stmt.fiscal_calendar = "school_year"
            stmt.predecessor_entity = predecessor
            stmt.total_revenue = inc.get("total_revenue")
            stmt.total_expenditures = inc.get("total_expenditures")
            stmt.surplus_deficit = inc.get("surplus_deficit")
            stmt.fund_balance = bs.get("total_fund_balance")
            stmt.total_debt = debt.get("total_outstanding_debt")
            stmt.raw_extraction = result
            stmt.extraction_model = "gemini-2.5-flash"
            stmt.extraction_pass = (stmt.extraction_pass or 0) + 1
            stmt.status = "extracted"
            db.flush()

            order = 1
            for item in (inc.get("revenue_line_items") or [])[:50]:
                db.add(FinancialLineItem(
                    statement_id=stmt.id, section="Revenue",
                    line_name=item.get("name", f"Rev {order}"),
                    amount=item.get("amount"),
                    prior_year_amount=item.get("prior_year"),
                    budget_amount=item.get("budget"),
                    line_order=order,
                ))
                order += 1
            for item in (inc.get("expenditure_line_items") or [])[:50]:
                db.add(FinancialLineItem(
                    statement_id=stmt.id, section="Expenditures",
                    line_name=item.get("name", f"Exp {order}"),
                    amount=item.get("amount"),
                    prior_year_amount=item.get("prior_year"),
                    budget_amount=item.get("budget"),
                    line_order=order,
                ))
                order += 1
            for key, label in [
                ("cash_and_investments", "Cash & Investments"),
                ("receivables", "Receivables"),
                ("total_assets", "Total Assets"),
                ("total_liabilities", "Total Liabilities"),
                ("total_fund_balance", "Total Fund Balance"),
                ("unreserved_fund_balance", "Unreserved Fund Balance"),
            ]:
                val = bs.get(key)
                if val:
                    db.add(FinancialLineItem(
                        statement_id=stmt.id, section="Balance Sheet",
                        line_name=label, amount=val, line_order=order,
                    ))
                    order += 1

            db.commit()
            count += 1

            rev = inc.get("total_revenue")
            exp = inc.get("total_expenditures")
            fb = bs.get("total_fund_balance")
            td = debt.get("total_outstanding_debt")
            def _fmt(v):
                return f"${v:,.0f}" if v else "-"
            print(f"  Rev={_fmt(rev)} Exp={_fmt(exp)} FB={_fmt(fb)} Debt={_fmt(td)} ({order - 1} items)")
            time.sleep(0.5)

        except json.JSONDecodeError as e:
            print(f"  JSON ERR: {e}")
            db.rollback()
        except Exception as e:
            print(f"  ERR: {e}")
            db.rollback()

    db.close()
    print(f"\nDONE! Extracted {count}/{len(docs)} school ACFRs.")


if __name__ == "__main__":
    main()
