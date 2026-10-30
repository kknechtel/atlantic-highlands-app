"""Resident-facing financial overview for one entity (town or school).

Picks ONE statement per fiscal year as that year's official numbers and takes
every metric from that statement, so a year never mixes an audit's revenue
with a budget's fund balance. Also used by /api/financial/fy-view for source
ranking, so the overview and the merged FY view agree on what's authoritative.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from municipality import TOWN

# Most authoritative first. Audits/ACFRs are actuals; the rest are plans.
SOURCE_PRIORITY = {
    "audit": 0, "acfr": 0, "annual_report": 1, "financial_statement": 1,
    "ufb": 2, "budget": 3,
}
ACTUAL_TYPES = {"audit", "acfr", "annual_report", "financial_statement"}
USABLE_STATUSES = {"extracted", "drilled", "verified"}

_COUNTY_WORD = TOWN.county.lower().replace(" county", "").strip()

# Town Current Fund balance as a share of spending. Same thresholds as
# services/financial_anomaly.py (target >=8%, warn <5%).
TOWN_RESERVE_TARGET_PCT = 8.0
TOWN_RESERVE_WARN_PCT = 5.0

# Statement-level anomaly codes, rewritten for residents. Per-line codes
# (yoy_swing_large, budget_variance_large) are counted, not listed.
FLAG_TITLES = {
    "school_fund_balance_over_cap": "Reserves above the state's 2% surplus cap",
    "municipal_fund_balance_low": "Reserves below the recommended 8% of spending",
    "negative_fund_balance": "Fund balance is negative",
    "operating_ratio_high": "Spending more than 5% above revenue",
    "operating_deficit": "Spending slightly above revenue",
    "debt_to_revenue_high": "Debt is larger than a year's revenue",
    "salary_concentration_high": "Salaries are a very large share of spending",
    "salary_concentration_elevated": "Salaries are a large share of spending",
}
LINE_FLAG_CODES = {"yoy_swing_large", "budget_variance_large"}


def doc_variant(entity_name: Optional[str]) -> str:
    n = (entity_name or "").lower()
    if "advertised" in n or "tentative" in n:
        return "advertised"
    if "adopted" in n or "final" in n:
        return "adopted"
    if _COUNTY_WORD and _COUNTY_WORD in n:
        return "dlgs_filing"
    if "presentation" in n:
        return "presentation"
    return "primary"


def statement_rank(s) -> tuple[int, int]:
    """Lower is more authoritative. Among same type:
    adopted > DLGS filing > primary > advertised > presentation."""
    type_pri = SOURCE_PRIORITY.get((s.statement_type or "").lower(), 9)
    variant_pri = {"adopted": 0, "dlgs_filing": 1, "primary": 2, "advertised": 3,
                   "presentation": 4}.get(doc_variant(s.entity_name), 5)
    return (type_pri, variant_pri)


def fy_sort_key(fy: str) -> tuple[int, str]:
    """'2024', '2024-2025' and '2024-25' all sort by their first year."""
    m = re.search(r"(19|20)\d{2}", fy or "")
    return (int(m.group(0)) if m else 0, fy or "")


def yearly_series(statements: Iterable) -> list[dict]:
    """One row per fiscal year, oldest first, from the best usable statement."""
    by_year: dict[str, list] = {}
    for s in statements:
        if not s.fiscal_year or s.status not in USABLE_STATUSES:
            continue
        if s.total_expenditures is None and s.total_revenue is None:
            continue
        by_year.setdefault(s.fiscal_year, []).append(s)

    rows = []
    for fy in sorted(by_year, key=fy_sort_key):
        p = sorted(by_year[fy], key=statement_rank)[0]
        stype = (p.statement_type or "").lower()
        rows.append({
            "fiscal_year": fy,
            "revenue": p.total_revenue,
            "expenditures": p.total_expenditures,
            "surplus": p.surplus_deficit,
            "fund_balance": p.fund_balance,
            "debt": p.total_debt,
            "kind": "actual" if stype in ACTUAL_TYPES else "budget",
            "statement_type": stype,
            "statement_id": str(p.id),
            "document_id": str(p.document_id),
        })
    return rows


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return round((new - old) / abs(old) * 100, 1)


def reserves(row: dict, entity_type: str) -> Optional[dict]:
    fb, exp = row.get("fund_balance"), row.get("expenditures")
    if fb is None or not exp or exp <= 0:
        return None
    pct = round(fb / exp * 100, 1)
    if entity_type == "school":
        # The extracted fund balance usually includes restricted reserves
        # (capital, maintenance), which legitimately exceed the 2% cap on
        # unassigned surplus — so no rating, just context.
        return {"pct": pct, "status": None,
                "note": "State law caps a district's unassigned surplus at 2% of spending. "
                        "Total fund balance also includes restricted reserves, so it is usually higher."}
    status = ("low" if pct < TOWN_RESERVE_WARN_PCT
              else "watch" if pct < TOWN_RESERVE_TARGET_PCT else "ok")
    return {"pct": pct, "status": status,
            "note": f"Reserves of {TOWN_RESERVE_TARGET_PCT:.0f}% of spending or more are generally "
                    f"considered healthy for a NJ municipality; under {TOWN_RESERVE_WARN_PCT:.0f}% is a warning sign."}


def plain_flags(anomaly_flags: list[dict] | None) -> tuple[list[dict], int]:
    """Statement-level flags with resident-facing titles, plus a count of
    per-line flags (large year-over-year or budget swings)."""
    out, line_count = [], 0
    for f in anomaly_flags or []:
        code = f.get("code")
        if code in LINE_FLAG_CODES:
            line_count += 1
            continue
        if f.get("severity") not in ("warn", "high"):
            continue
        out.append({"code": code, "severity": f.get("severity"),
                    "title": FLAG_TITLES.get(code, "Automated check flagged this year"),
                    "detail": f.get("message")})
    return out, line_count


_SECTION_KEYS = {"revenue": ("revenue",), "spending": ("expenditure", "appropriation")}


def top_lines(line_items: Iterable, n: int = 6) -> dict[str, list[dict]]:
    """Largest individual revenue and spending lines. Totals/subtotals are
    skipped; no shares are computed because extracted line items can nest."""
    out: dict[str, list[dict]] = {k: [] for k in _SECTION_KEYS}
    for it in line_items:
        if it.is_total_row or it.amount is None or it.amount <= 0:
            continue
        name = (it.line_name or "").strip()
        if not name or name.lower().startswith(("total", "subtotal")):
            continue
        section = (it.section or "").lower()
        for key, needles in _SECTION_KEYS.items():
            if any(nd in section for nd in needles):
                out[key].append({"name": name, "amount": it.amount})
                break
    for key in out:
        out[key] = sorted(out[key], key=lambda x: -x["amount"])[:n]
    return out
