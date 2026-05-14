"""Re-run reconcile on every drilled/extracted statement using the fixed reconciler."""
from database import SessionLocal
from models.financial import FinancialStatement
from services.financial_reconcile import reconcile_statement

db = SessionLocal()
stmts = db.query(FinancialStatement).filter(
    FinancialStatement.status.in_(["drilled", "extracted", "verified"])
).all()
print(f"Re-reconciling {len(stmts)} statements...")
changed = 0
unchanged = 0
for s in stmts:
    prev = s.reconcile_status or "?"
    new_status, new_details = reconcile_statement(s, db)
    if new_status != prev:
        s.reconcile_status = new_status
        s.reconcile_details = new_details
        changed += 1
        print(f"  {str(s.id)[:8]} {s.entity_type:6} FY{s.fiscal_year:10} {s.statement_type:18}  {prev:14} -> {new_status}")
    else:
        s.reconcile_details = new_details
        unchanged += 1
db.commit()
print(f"\nDone: {changed} changed, {unchanged} unchanged.")
db.close()
