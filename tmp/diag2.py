from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
# Find the absurd "Other" amounts in the SCHOOL DIST BUDGET
print("=== SCHOOL DIST BUDGET: highest 'Other' amounts ===")
for r in db.execute(text("""
    SELECT line_name, amount, prior_year_amount, account_code, section, subsection
    FROM financial_line_items
    WHERE statement_id = '1786a4f4-09db-426e-9fd8-543dd56641bb'
      AND section = 'Other'
    ORDER BY amount DESC NULLS LAST LIMIT 15
""")):
    print(f"  ${r.amount or 0:>20,.0f}  [{r.section}/{r.subsection or '-'}]  '{r.line_name[:80]}'  acct={r.account_code}")
print()
print("=== 2025-26 PRES: highest 'Other' ===")
for r in db.execute(text("""
    SELECT line_name, amount, prior_year_amount, account_code, section
    FROM financial_line_items
    WHERE statement_id = 'd3db9ea0-5dae-4d50-a389-cdbd772f8a29'
      AND section = 'Other'
    ORDER BY amount DESC NULLS LAST LIMIT 10
""")):
    print(f"  ${r.amount or 0:>20,.0f}  [{r.section}]  '{r.line_name[:80]}'  acct={r.account_code}")
print()
print("=== 2025-26 PRES: total revenue lines ===")
for r in db.execute(text("""
    SELECT line_name, amount, prior_year_amount, is_total_row, section
    FROM financial_line_items
    WHERE statement_id = 'd3db9ea0-5dae-4d50-a389-cdbd772f8a29'
      AND section = 'Revenue'
    ORDER BY amount DESC NULLS LAST LIMIT 15
""")):
    print(f"  ${r.amount or 0:>15,.0f}  prior=${r.prior_year_amount or 0:>15,.0f}  total={r.is_total_row}  '{r.line_name[:80]}'")
db.close()
