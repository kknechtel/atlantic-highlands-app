"""Structured facts from board minutes/agendas: approved bills totals."""
import re
from datetime import date, datetime

_BILLS = re.compile(
    r"BILLS?\s*(?:&|and)\s*CLAIMS\s+for\s+(?:the\s+)?(?P<period>[^$]{3,70}?)\s+in\s+the\s+amount\s+of\s+"
    r"\$\s?(?P<amt>[\d,]+\.\d{2})", re.I)
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_MONTH = re.compile(rf"\b({_MONTHS})\b(?:\s+\d{{1,2}},)?\s+(\d{{4}})", re.I)


def period_month(period):
    """'January 2025' / 'June 30, 2026' -> first of month; None if the period
    names more than one month (combined approvals can't be reconciled monthly)."""
    ms = {(m.group(1).lower(), m.group(2)) for m in _MONTH.finditer(period)}
    if len(ms) != 1:
        return None
    mon, yr = ms.pop()
    return datetime.strptime(f"1 {mon} {yr}", "%d %B %Y").date()


def bill_approvals(text):
    flat = " ".join((text or "").split())
    out = []
    for m in _BILLS.finditer(flat):
        period = m.group("period").strip()
        out.append({"period": period, "period_month": period_month(period),
                    "kind": "payroll" if re.search(r"payroll", period, re.I) else "bills",
                    "amount": float(m.group("amt").replace(",", "")),
                    "text": flat[max(0, m.start() - 40):m.end() + 10]})
    return out


def ingest(con):
    """Rebuild bill_approvals from all fetched minutes/agendas."""
    from moneytrail.schema import bulk_insert
    con.execute("DELETE FROM bill_approvals")
    rows = []
    for sha, body, ddate, cls, page, text in con.execute("""
        SELECT d.sha256, d.public_body, d.doc_date, d.doc_class, t.page, t.text
        FROM documents d JOIN doc_text t USING (sha256)
        WHERE d.doc_class IN ('minutes', 'agenda')
    """).fetchall():
        for a in bill_approvals(text):
            rows.append([body, ddate, a["period"], a["period_month"], a["kind"], a["amount"], cls, sha, page, a["text"]])
    bulk_insert(con, "bill_approvals", ["public_body", "meeting_date", "period", "period_month", "kind", "amount",
                                        "doc_class", "sha256", "page", "text"], rows)
    return len(rows)
