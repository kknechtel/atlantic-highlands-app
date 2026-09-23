"""School districts: July-June fiscal year, Public School Contracts Law
citations, predecessor/successor grouping, and board-member disclosures."""
import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from moneytrail import bodies, loaders, resolve, rules, schema

FX = Path(__file__).parent / "fixtures" / "school"


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    schema.init(c)
    for t, f in [("public_bodies", "public_bodies.csv"), ("awards", "awards.csv"),
                 ("payments", "payments.csv"), ("disclosures", "disclosures.csv"),
                 ("contributions", "contributions.csv"), ("recipient_map", "recipient_map.csv")]:
        loaders.load_csv(c, t, FX / f)
    resolve.resolve(c)
    rules.run_all(c)
    return c


def flags(con, rule):
    return [dict(zip(("public_body", "entity_name", "score", "summary", "evidence"), r)) for r in con.execute(
        "SELECT public_body, entity_name, score, summary, evidence FROM flags WHERE rule=? ORDER BY public_body",
        [rule]).fetchall()]


@pytest.mark.parametrize("name,t", [
    ("Henry Hudson Regional Board of Education", "school"),
    ("Atlantic Highlands School District", "school"),
    ("Monmouth-Ocean Educational Services Commission", "school"),
    ("Monmouth County", "county"),
    ("Township of Middletown Sewerage Authority", "authority"),
    ("Borough of Atlantic Highlands", "municipal"),
])
def test_infer_type(name, t):
    assert bodies.infer_type(name) == t


def test_school_fiscal_year_unlisted_body():
    c = duckdb.connect(":memory:")
    schema.init(c)
    B = bodies.Bodies(c)
    assert B.fiscal_year("Some Board of Education", date(2024, 6, 30)) == 2024
    assert B.fiscal_year("Some Board of Education", date(2024, 7, 1)) == 2025
    assert B.fiscal_year("Borough of Somewhere", date(2024, 7, 1)) == 2024


def test_aliases_canonicalized_raw_kept(con):
    bodies_seen = {r[0] for r in con.execute("SELECT DISTINCT public_body FROM awards UNION SELECT DISTINCT public_body FROM payments").fetchall()}
    assert "Example Regional BOE" not in bodies_seen and "Example Regional Board of Education" not in bodies_seen
    raw = con.execute("SELECT raw FROM awards WHERE source_row = 2").fetchone()[0]
    assert json.loads(raw)["public_body"] == "Example Regional BOE"


def test_aggregate_uses_school_fiscal_year(con):
    fl = flags(con, "aggregate_over_bid_threshold")
    by = {f["public_body"]: f for f in fl}
    # Borough (calendar): 30k + 30k in 2024 -> flagged.
    assert "60,000" in by["Borough of Example"]["summary"]
    # District: calendar 2024 would be 60k, but FY2024 = 30k and FY2025 = 30k + 20k = 50k.
    school = by["Example Regional School District"]
    assert "50,000" in school["summary"] and "FY2025 (7/1/2024-6/30/2025)" in school["summary"]
    assert "18A:18A-3" in json.dumps(json.loads(school["evidence"])["score_parts"])
    assert len([f for f in fl if f["public_body"] == "Example Regional School District"]) == 1


def test_split_across_predecessor_districts(con):
    [f] = flags(con, "split_awards")
    parts = json.loads(f["evidence"])["score_parts"]
    assert f["public_body"] == "Example Regional School District"   # grouped under successor
    assert "Other Borough School District, Sample Borough School District" in f["summary"]
    assert any("related bodies" in p for p, _ in parts) and f["score"] == 50
    [r] = flags(con, "repeat_noncompetitive")
    assert "related bodies" in r["evidence"]


def test_official_disclosed_business_is_vendor(con):
    [f] = flags(con, "official_disclosed_business_vendor")
    assert f["score"] == 80 and "Chris Trustee" in f["summary"] and "spouse" in f["summary"]
    assert "answered NO" in f["evidence"]
    assert "18A:12-24" in f["evidence"]


def test_official_home_address_matches_vendor(con):
    [f] = flags(con, "official_vendor_link")
    assert f["entity_name"] == "Maple Consulting" and "Robin Member" in f["summary"] and f["score"] == 55


def test_blank_disclosed_business_ignored(con):
    assert con.execute("SELECT count(*) FROM mentions WHERE role='disclosed_business'").fetchone()[0] == 1


def test_school_award_gets_2026_disclosure_not_p2p_bar(con):
    [f] = flags(con, "donation_near_award")
    parts = json.loads(f["evidence"])["score_parts"]
    assert any("19:44A-20.26" in p for p, _ in parts)
    assert not any("19:44A-20.4" in p or "19:44A-20.5" in p for p, _ in parts)


def test_bid_threshold_effective_dated(con):
    B = bodies.Bodies(con)
    assert B.bid_threshold("Example Regional School District", date(2025, 6, 30)) == 44_000
    assert B.bid_threshold("Example Regional School District", date(2025, 7, 1)) == 53_000
    con.execute("UPDATE public_bodies SET has_qpa = false WHERE name = 'Example Regional School District'")
    con.execute("UPDATE public_bodies SET has_qpa = false WHERE name = 'Borough of Example'")
    B = bodies.Bodies(con)
    assert B.bid_threshold("Example Regional School District", date(2025, 7, 1)) == 39_000
    assert B.bid_threshold("Borough of Example", date(2025, 7, 1)) == 17_500


def test_audit_acceptance_extraction():
    from moneytrail import audit
    txt = ("M. To accept the ANNUAL COMPREHENSIVE FINANCIAL REPORT AND THE AUDITORS\n MANAGEMENT REPORT for the "
           "School District of Highlands for the fiscal year ending June 30, 2024,\n from Alvino & Shechter, L.L.C. "
           "Certified Public Accountants with no audit recommendations.\n N. To approve")
    [a] = audit.acceptances(txt)
    assert a["public_body"] == "School District of Highlands" and a["fiscal_year"] == 2024
    assert a["category"] == "none" and a["report_type"] == "AMR" and a["auditor"].startswith("Alvino")


def test_audit_numbered_findings():
    from moneytrail import audit
    txt = ("GENERAL COMMENTS\nblah\nRECOMMENDATIONS\n1. That all purchases exceeding the quote threshold be "
           "supported by quotations.\n2. That payroll overtime be approved in advance by the department head. "
           "This is a repeat finding from the prior year.\n")
    fs = audit.findings(txt)
    assert [(f["finding_no"], f["category"], f["is_repeat"]) for f in fs] == [
        ("1", "procurement", False), ("2", "payroll", True)]


def test_bill_approvals_parse():
    from moneytrail import minutes
    t = ("A. To approve the BILLS & CLAIMS for January 2025 in the amount of $2,206,520.53 B. To approve the "
         "BILLS & CLAIMS for December 2024 Payrolls in the amount of $1,251,733.19 C. To approve the BILLS & "
         "CLAIMS for June 30, 2025 and July 2025 in the amount of $2,402,435.30")
    a = minutes.bill_approvals(t)
    assert [(x["kind"], x["amount"], str(x["period_month"])) for x in a] == [
        ("bills", 2206520.53, "2025-01-01"), ("payroll", 1251733.19, "2024-12-01"), ("bills", 2402435.30, "None")]


def test_payments_vs_approved(con):
    con.execute("""INSERT INTO bill_approvals VALUES ('Example Regional School District', '2024-10-16', 'October 2024',
                   '2024-10-01', 'bills', 17000.00, 'minutes', 'abc', 5, 'x'),
                  ('Example Regional School District', '2024-11-20', 'November 2024',
                   '2024-11-01', 'bills', 9000.00, 'minutes', 'abc', 6, 'x')""")
    rules.run_all(con)
    [f] = flags(con, "payments_vs_approved")
    assert "October 2024" in f["summary"] and "+1,000.00" in f["summary"] and f["score"] == 40


def test_date_scoped_alias():
    c = duckdb.connect(":memory:")
    schema.init(c)
    c.execute("""INSERT INTO public_bodies (name, body_type, successor, aliases) VALUES
        ('New Regional SD', 'school', NULL, 'School District of Old Name@from=2024-07-01'),
        ('Old Name HS District', 'school', 'New Regional SD', 'School District of Old Name@until=2024-06-30')""")
    c.execute("""INSERT INTO audit_findings (public_body, fiscal_year, category) VALUES
        ('School District of Old Name', 2024, 'none'), ('School District of Old Name', 2025, 'none')""")
    bodies.canonicalize(c)
    assert c.execute("SELECT fiscal_year, public_body FROM audit_findings ORDER BY 1").fetchall() == [
        (2024, "Old Name HS District"), (2025, "New Regional SD")]
