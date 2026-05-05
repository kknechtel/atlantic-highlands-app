"""
Reconciliation: do the extracted line items add up to the reported summary totals?

Sums non-total lines per section, compares to summary totals from the header pass.
Returns a status + details JSONB. Bands:
  balanced     |delta| < 0.5%
  off_lt_1pct  0.5% <= |delta| < 1%
  off_gt_1pct  1% <= |delta| < 5%
  unbalanced   |delta| >= 5% OR delta is unknown
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def reconcile_statement(stmt, db: Session) -> Tuple[str, Dict]:
    from models.financial import FinancialLineItem

    items = (
        db.query(FinancialLineItem)
        .filter(FinancialLineItem.statement_id == stmt.id)
        .all()
    )

    # Sum non-total lines by section
    sums: Dict[str, float] = {}
    for it in items:
        if it.is_total_row:
            continue
        if it.amount is None:
            continue
        section = (it.section or "Other").strip()
        sums[section] = sums.get(section, 0.0) + float(it.amount)

    # Compare to reported summary
    targets = {
        "Revenue": stmt.total_revenue,
        "Expenditures": stmt.total_expenditures,
    }

    detail = {"sums_by_section": {k: round(v, 2) for k, v in sums.items()}, "checks": []}
    worst_status = "balanced"

    for section_name, reported in targets.items():
        extracted = sums.get(section_name)
        if reported is None:
            detail["checks"].append({
                "section": section_name,
                "status": "no_target",
                "extracted": round(extracted, 2) if extracted is not None else None,
                "reported": None,
            })
            worst_status = _worse(worst_status, "off_lt_1pct")  # unknown target — mild flag
            continue
        if extracted is None:
            detail["checks"].append({
                "section": section_name, "status": "no_lines",
                "extracted": None, "reported": float(reported),
            })
            worst_status = _worse(worst_status, "unbalanced")
            continue

        delta = extracted - float(reported)
        pct = (abs(delta) / abs(float(reported)) * 100) if reported else 100.0
        status = _band(pct)
        detail["checks"].append({
            "section": section_name,
            "status": status,
            "extracted": round(extracted, 2),
            "reported": round(float(reported), 2),
            "delta": round(delta, 2),
            "delta_pct": round(pct, 2),
        })
        worst_status = _worse(worst_status, status)

    return worst_status, detail


def _band(pct: float) -> str:
    if pct < 0.5:
        return "balanced"
    if pct < 1.0:
        return "off_lt_1pct"
    if pct < 5.0:
        return "off_gt_1pct"
    return "unbalanced"


_RANK = {
    "balanced": 0,
    "no_target": 1,
    "off_lt_1pct": 2,
    "off_gt_1pct": 3,
    "unbalanced": 4,
}


def _worse(a: str, b: str) -> str:
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b
