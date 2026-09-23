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


def canonicalize(con):
    """Rewrite public_body in every source table to the canonical name from
    public_bodies (matching name or any alias). The original spelling stays in
    each row's raw JSON."""
    amap = {}
    for name, aliases in con.execute("SELECT name, aliases FROM public_bodies").fetchall():
        for a in [name] + [x for x in (aliases or "").split(";") if x.strip()]:
            amap[_key(a)] = name
    if not amap:
        return 0
    changed = 0
    for table in ("awards", "payments", "employees", "disclosures"):
        for (raw,) in con.execute(f"SELECT DISTINCT public_body FROM {table} WHERE public_body IS NOT NULL").fetchall():
            canon = amap.get(_key(raw))
            if canon and canon != raw:
                con.execute(f"UPDATE {table} SET public_body = ? WHERE public_body = ?", [canon, raw])
                changed += 1
    # recipient_map targets use the same vocabulary
    for (raw,) in con.execute("SELECT DISTINCT public_body FROM recipient_map").fetchall():
        canon = amap.get(_key(raw))
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
