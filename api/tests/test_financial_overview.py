"""Resident financial overview: one statement per year, the headline guard,
and the school iCal parser."""
from datetime import date
from types import SimpleNamespace

from services import financial_headline as fh
from services import financial_overview as fo
from services.school_calendar import parse_ics


def _stmt(fy, stype, name="Sample District", status="extracted", **nums):
    base = dict(total_revenue=None, total_expenditures=None, surplus_deficit=None,
                fund_balance=None, total_debt=None)
    base.update(nums)
    return SimpleNamespace(id=f"{fy}-{stype}-{name}", document_id="doc", fiscal_year=fy,
                           statement_type=stype, entity_name=name, status=status, **base)


def test_audit_beats_budget_and_metrics_are_not_mixed():
    rows = fo.yearly_series([
        _stmt("2024", "budget", "Adopted Budget", total_expenditures=10e6, fund_balance=1e6),
        _stmt("2024", "audit", total_expenditures=9.5e6),
        _stmt("2023", "budget", "Advertised Budget", total_expenditures=8e6),
        _stmt("2023", "budget", "Adopted Budget", total_expenditures=8.5e6),
        _stmt("2022", "audit", status="needs_reextraction", total_expenditures=1),
    ])
    assert [r["fiscal_year"] for r in rows] == ["2023", "2024"]
    assert rows[0]["expenditures"] == 8.5e6 and rows[0]["kind"] == "budget"
    # The audit wins 2024 and its missing fund balance is NOT filled from the budget.
    assert rows[1]["expenditures"] == 9.5e6 and rows[1]["fund_balance"] is None
    assert rows[1]["kind"] == "actual"


def test_school_years_sort_by_first_year():
    rows = fo.yearly_series([_stmt("2025-2026", "budget", total_expenditures=1),
                             _stmt("2024-25", "budget", total_expenditures=1)])
    assert [r["fiscal_year"] for r in rows] == ["2024-25", "2025-2026"]


def test_town_reserves_rated_school_not():
    assert fo.reserves({"fund_balance": 4, "expenditures": 100}, "town")["status"] == "low"
    assert fo.reserves({"fund_balance": 6, "expenditures": 100}, "town")["status"] == "watch"
    assert fo.reserves({"fund_balance": 9, "expenditures": 100}, "town")["status"] == "ok"
    school = fo.reserves({"fund_balance": 9, "expenditures": 100}, "school")
    assert school["pct"] == 9.0 and school["status"] is None


def test_top_lines_skip_totals():
    items = [SimpleNamespace(line_name=n, amount=a, section=s, is_total_row=t)
             for n, a, s, t in [("Tax levy", 5, "Revenue", False), ("Total revenue", 9, "Revenue", False),
                                ("Subtotal", 8, "Revenue", True), ("Salaries", 7, "Expenditures", False)]]
    out = fo.top_lines(items)
    assert [x["name"] for x in out["revenue"]] == ["Tax levy"]
    assert [x["name"] for x in out["spending"]] == ["Salaries"]


FACTS = fh.build_facts("Bank A Town", [
    {"fiscal_year": "2024", "kind": "actual", "expenditures": 10_000_000, "revenue": 10_200_000, "debt": None},
    {"fiscal_year": "2025", "kind": "actual", "expenditures": 10_400_000, "revenue": 10_500_000, "debt": 3_000_000},
], reserves_pct=8.2)


def test_facts_are_preformatted():
    assert FACTS[0] == "Bank A Town spending in FY 2025 was $10.4M, up 4.0% from FY 2024."
    assert "Fund balance equals 8.2% of spending." in FACTS


def test_guard_accepts_faithful_rewording():
    ok = ("In FY 2025 Bank A Town spent $10.4M, up 4.0% from FY 2024, and took in $10.5M. "
          "Fund balance equals 8.2% of spending and debt was $3.0M.")
    assert fh.passes_guard(ok, FACTS)


def test_guard_rejects_new_numbers_and_judgements():
    assert not fh.passes_guard("Bank A Town spent $10.4M, about $600K more than before.", FACTS)
    assert not fh.passes_guard("Spending rose 4.0% to $10.4M, a concerning trend.", FACTS)
    assert not fh.passes_guard("Reserves are healthy at 8.2% of spending.", FACTS)
    assert not fh.passes_guard("x" * 500, FACTS)


ICS = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0",
    "BEGIN:VEVENT", "UID:1", "DTSTART;VALUE=DATE:20261126", "DTEND;VALUE=DATE:20261128",
    "SUMMARY:Schools Closed - Holiday", "END:VEVENT",
    "BEGIN:VEVENT", "UID:2", "DTSTART:20261118T000000Z", "DTEND:20261118T010000Z",
    "SUMMARY:Board of Education Meeting\\, Regular", "LOCATION:Sample High School",
    "DESCRIPTION:Agenda posted\\nin advance and this line is fol", " ded",
    "END:VEVENT",
    "BEGIN:VEVENT", "UID:3", "DTSTART;TZID=America/New_York:20261203T183000",
    "SUMMARY:Winter Concert", "END:VEVENT",
    "END:VCALENDAR",
])


def test_parse_ics_dates_times_and_escapes():
    ev = parse_ics(ICS, "America/New_York")
    assert len(ev) == 3
    assert ev[0]["date"] == date(2026, 11, 26) and ev[0]["time"] is None
    # 00:00Z on the 18th is 7 PM Eastern on the 17th.
    assert ev[1]["date"] == date(2026, 11, 17) and ev[1]["time"] == "7:00 PM"
    assert ev[1]["end_time"] == "8:00 PM"
    assert ev[1]["title"] == "Board of Education Meeting, Regular"
    assert ev[1]["description"] == "Agenda posted\nin advance and this line is folded"
    assert ev[2]["time"] == "6:30 PM"
