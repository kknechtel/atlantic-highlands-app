from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
for sid, label in [
    ('c7be8471-a48f-4a50-aedd-3db49ea77273', 'ADV BUDGET'),
    ('1786a4f4-09db-426e-9fd8-543dd56641bb', 'SCHOOL DIST BUDGET'),
    ('53bd64e7-04a5-4522-a5bb-b7f780f3db3a', 'PRESENTATION'),
    ('d3db9ea0-5dae-4d50-a389-cdbd772f8a29', '2025-26 PRES'),
]:
    print(f"=== {label} ===")
    rs = db.execute(text("SELECT reconcile_details, total_revenue, total_expenditures FROM financial_statements WHERE id = :id"), {"id": sid}).fetchone()
    if not rs:
        continue
    rd = rs.reconcile_details or {}
    print(f"  reported_rev={rs.total_revenue}  reported_exp={rs.total_expenditures}")
    for k, v in (rd.get("sums_by_section") or {}).items():
        print(f"  section_sum[{k}] = {v:,.0f}")
    for c in (rd.get("checks") or []):
        ext = c.get("extracted")
        ext_s = f"{ext:,.0f}" if isinstance(ext, (int, float)) else str(ext)
        rep = c.get("reported")
        rep_s = f"{rep:,.0f}" if isinstance(rep, (int, float)) else str(rep)
        print(f"  check {c.get('section'):14} status={c.get('status'):14} extracted={ext_s} reported={rep_s} delta_pct={c.get('delta_pct')}")
    n_total = db.execute(text("SELECT count(*) FROM financial_line_items WHERE statement_id = :id AND is_total_row = true"), {"id": sid}).scalar()
    n_non = db.execute(text("SELECT count(*) FROM financial_line_items WHERE statement_id = :id AND is_total_row = false"), {"id": sid}).scalar()
    print(f"  is_total_row=true: {n_total}, false: {n_non}")
db.close()
