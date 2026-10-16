"""
Integrity settings for the Atlantic Highlands deployment.

Mirrors the New Jersey rule pack in civic-lens (jurisdictions/us/nj): statutory
thresholds and citations the rules quote. Update here when DLGS re-indexes them.
"""
from __future__ import annotations

from dataclasses import dataclass

INTEGRITY: dict = {'bid_threshold': {'purchase': 53000, 'public_works': 53000, 'history': [{'from': '2015-07-01', 'purchase': 40000, 'public_works': 40000}, {'from': '2020-07-01', 'purchase': 44000, 'public_works': 44000}, {'from': '2025-07-01', 'purchase': 53000, 'public_works': 53000}], 'citation': 'N.J.S.A. 40A:11-3 — $53,000 with a QPA from July 1, 2025 (LFN 2025-08); $44,000 from 2020, $40,000 from 2015'}, 'emergency': {'citation': 'N.J.S.A. 40A:11-6 and N.J.A.C. 5:34-6 — emergency contracts need a written certification and a report to the governing body at its next meeting'}, 'near_threshold_ratio': 0.85, 'split_window_days': 90, 'concentration_months': 24, 'concentration_min_awards': 3, 'payout_review_amount': 25000, 'change_order': {'cap_pct': 20, 'citation': 'N.J.A.C. 5:30-11 — change orders cumulatively over 20% of the contract need additional approvals'}, 'pay_to_play': {'statutory': True, 'window_days': 365, 'contribution_threshold': 300, 'contract_threshold': 17500, 'annual_disclosure_threshold': 50000, 'citation': 'N.J.S.A. 19:44A-20.4 et seq. (local pay-to-play) — contributions over $300 in the prior year bar a non-fair-and-open contract over $17,500; local ordinances may be stricter'}}


@dataclass(frozen=True)
class _Entity:
    key: str


class _Deployment:
    primary_entity = _Entity("atlantic_highlands")
    integrity = INTEGRITY
    # HHRSD (and its predecessors) run July–June; the borough runs on the calendar year.
    _SCHOOL = {"hhrsd", "ahsd", "hsd", "hhrs"}

    def fiscal_year_for(self, year: int, month: int, entity_key: str | None = None) -> str:
        if (entity_key or "") not in self._SCHOOL:
            return str(year)
        first = year if month >= 7 else year - 1
        return f"{first}-{(first + 1) % 100:02d}"


_DEPLOYMENT = _Deployment()


def get_municipality() -> _Deployment:
    return _DEPLOYMENT
