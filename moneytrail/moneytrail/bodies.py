"""Public-body metadata: type, fiscal year, related-body groups, aliases.

Bodies not listed in public_bodies get a type inferred from the name. School
districts default to a July-June fiscal year, everything else to calendar.
"""
import re
from datetime import date

from moneytrail import config as C
from moneytrail import normalize as N

_SCHOOL = re.compile(r"\b(BOARD OF EDUCATION|BOE|SCHOOLS?|SCHOOL DISTRICT|REGIONAL SCHOOL|"
                     r"EDUCATIONAL SERVICES COMMISSION|ESC|CHARTER|VOCATIONAL)\b")
_COUNTY = re.compile(r"\bCOUNTY\b")
_AUTH = re.compile(r"\b(AUTHORITY|MUA|SEWERAGE|UTILITIES)\b")
_FIRE = re.compile(r"\bFIRE DISTRICT\b")


def infer_type(name):
    u = N._clean(name)
    if _SCHOOL.search(u):
        return "school"
    if _FIRE.search(u):
        return "fire_district"
    if _AUTH.search(u):
        return "authority"
    if _COUNTY.search(u):
        return "county"
    return "municipal"


def _key(name):
    return N._clean(name)


# Date each table's rows are "as of", for date-scoped aliases.
_ASOF = {
    "awards": "award_date", "payments": "payment_date",
    "employees": "make_date(pay_year, 12, 31)", "disclosures": "make_date(filing_year, 1, 1)",
    # school FY ends June 30; for calendar-year bodies this is conservative
    "audit_findings": "make_date(fiscal_year, 6, 30)",
}
_SCOPE = re.compile(r"^(?P<alias>.+?)\s*@(?P<op>from|until)=(?P<d>\d{4}-\d{2}-\d{2})$")


def _parse_aliases(name, aliases):
    """'X;Y@until=2024-06-30' -> [(key, canonical, op, date)]. A scoped alias
    only applies to rows dated inside its range (a name reused by a successor)."""
    out = [(_key(name), name, None, None)]
    for a in (aliases or "").split(";"):
        a = a.strip()
        if not a:
            continue
        m = _SCOPE.match(a)
        if m:
            out.append((_key(m.group("alias")), name, m.group("op"), date.fromisoformat(m.group("d"))))
        else:
            out.append((_key(a), name, None, None))
    return out


def canonicalize(con):
    """Rewrite public_body in every source table to the canonical name from
    public_bodies (matching name or any alias). The original spelling stays in
    each row's raw JSON."""
    rules = []
    for name, aliases in con.execute("SELECT name, aliases FROM public_bodies").fetchall():
        rules += _parse_aliases(name, aliases)
    if not rules:
        return 0
    plain = {k: n for k, n, op, _ in rules if op is None}
    scoped = [(k, n, op, d) for k, n, op, d in rules if op]
    changed = 0
    for table in ("awards", "payments", "employees", "disclosures", "audit_findings"):
        for (raw,) in con.execute(f"SELECT DISTINCT public_body FROM {table} WHERE public_body IS NOT NULL").fetchall():
            k = _key(raw)
            for sk, canon, op, d in scoped:
                if sk == k:
                    cmp = ">=" if op == "from" else "<="
                    changed += con.execute(
                        f"UPDATE {table} SET public_body = ? WHERE public_body = ? AND {_ASOF[table]} {cmp} ?",
                        [canon, raw, d]).fetchone()[0] or 0
            canon = plain.get(k)
            if canon and canon != raw:
                con.execute(f"UPDATE {table} SET public_body = ? WHERE public_body = ?", [canon, raw])
                changed += 1
    # recipient_map targets use the same vocabulary
    for (raw,) in con.execute("SELECT DISTINCT public_body FROM recipient_map").fetchall():
        canon = plain.get(_key(raw))
        if canon and canon != raw:
            con.execute("UPDATE recipient_map SET public_body = ? WHERE public_body = ?", [canon, raw])
    return changed


class Bodies:
    def __init__(self, con):
        self.rows = {r[0]: r for r in con.execute(
            "SELECT name, body_type, fy_start_month, body_group, successor, has_qpa FROM public_bodies").fetchall()}

    def type(self, body):
        r = self.rows.get(body)
        return (r and r[1]) or infer_type(body or "")

    def fy_start(self, body):
        r = self.rows.get(body)
        if r and r[2]:
            return r[2]
        return 7 if self.type(body) == "school" else 1

    def fiscal_year(self, body, d):
        """FY labelled by the calendar year it ends in (NJ school FY2024 = 7/1/2023-6/30/2024)."""
        start = self.fy_start(body)
        return d.year + 1 if start > 1 and d.month >= start else d.year

    def fy_label(self, body, fy):
        start = self.fy_start(body)
        return f"FY{fy}" if start == 1 else f"FY{fy} ({start}/1/{fy - 1}-{start - 1 or 12}/30/{fy})"

    def group(self, body):
        """Grouping key for cross-body patterns: explicit group, else successor
        (so a consolidated district's predecessors group with it), else self."""
        r = self.rows.get(body)
        if r:
            return r[3] or r[4] or body
        return body

    def has_qpa(self, body):
        r = self.rows.get(body)
        return C.DEFAULT_HAS_QPA if not r or r[5] is None else r[5]

    def bid_threshold(self, body, on):
        law = "PSCL" if self.type(body) == "school" else "LPCL"
        return C.bid_threshold(law, self.has_qpa(body), on)

    def threshold_note(self, body, on):
        qpa = self.has_qpa(body)
        src = "" if self.rows.get(body) and self.rows[body][5] is not None else ", QPA assumed"
        return f"${self.bid_threshold(body, on):,} on {on} ({'with' if qpa else 'no'} QPA{src}; {self.bid_law(body)})"

    def bid_law(self, body):
        return C.BID_LAW.get(self.type(body), C.BID_LAW["default"])

    def change_order_rule(self, body):
        return C.CHANGE_ORDER_RULE.get(self.type(body), C.CHANGE_ORDER_RULE["default"])
