import json
from pathlib import Path

import duckdb
import pytest

from moneytrail import loaders, normalize as N, report, resolve, rules, schema

FX = Path(__file__).parent / "fixtures"
LOADS = [("contributions", "contributions.csv"), ("recipient_map", "recipient_map.csv"),
         ("be_disclosures", "be.csv"), ("awards", "awards.csv"), ("payments", "payments.csv"),
         ("employees", "employees.csv")]


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    schema.init(c)
    return c


@pytest.fixture
def loaded(con):
    for t, f in LOADS:
        loaders.load_csv(con, t, FX / f)
    resolve.resolve(con)
    rules.run_all(con)
    return con


def flags(con, rule):
    return [dict(zip(("entity_name", "score", "summary", "evidence"), r)) for r in
            con.execute("SELECT entity_name, score, summary, evidence FROM flags WHERE rule=?", [rule]).fetchall()]


# ─── normalize ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("ACME PAVING, L.L.C.", "Acme Paving Inc"),
    ("Shoreline Engineering Assoc.", "Shoreline Engineering Associates"),
    ("The Bayview Construction Co.", "Bayview Construction Company"),
])
def test_norm_org_equivalents(a, b):
    assert N.norm_org(a) == N.norm_org(b)


def test_norm_person_order_and_suffix():
    assert N.norm_person("SMITH, JOHN A. JR") == N.norm_person("John Smith") == "JOHN SMITH"


def test_norm_addr():
    assert N.norm_addr("100 Corporate Boulevard, Suite 200") == N.norm_addr("100 Corporate Blvd.") == "100 CORPORATE BLVD"
    assert N.norm_addr("P.O. Box 45") == "PO BOX 45"


def test_parse_amount_and_date():
    assert N.parse_amount("$1,234.50") == 1234.5
    assert N.parse_amount("(500)") == -500
    assert str(N.parse_date("03/01/2024")) == "2024-03-01"
    with pytest.raises(ValueError):
        N.parse_date("not-a-date")


# ─── loaders ─────────────────────────────────────────────────────────────────

def test_load_is_idempotent_by_hash(con):
    _, n1 = loaders.load_csv(con, "awards", FX / "awards.csv")
    _, n2 = loaders.load_csv(con, "awards", FX / "awards.csv")
    assert n1 == 9 and n2 is None
    assert con.execute("SELECT count(*) FROM awards").fetchone()[0] == 9


def test_bad_rows_abort_whole_file(con):
    with pytest.raises(ValueError, match="line 2"):
        loaders.load_csv(con, "awards", FX / "bad_awards.csv")
    assert con.execute("SELECT count(*) FROM source_files").fetchone()[0] == 0


def test_missing_required_column_fails_loudly(con):
    with pytest.raises(ValueError, match="public_body"):
        loaders.load_csv(con, "awards", FX / "missing_cols.csv")


def test_provenance_kept(con):
    loaders.load_csv(con, "contributions", FX / "contributions.csv")
    line, raw, kind = con.execute(
        "SELECT source_row, raw, contributor_kind FROM contributions WHERE contributor_name LIKE 'ACME%'").fetchone()
    assert line == 2 and json.loads(raw)["NonIndName"] == "ACME PAVING, L.L.C." and kind == "org"
    # first/last fallback when NonIndName is blank
    assert con.execute("SELECT count(*) FROM contributions WHERE contributor_name = 'John Q Builder'").fetchone()[0] == 1


# ─── entity resolution ───────────────────────────────────────────────────────

def _entity_of(con, table, name_like):
    return con.execute("""SELECT DISTINCT me.entity_id FROM mentions m JOIN mention_entity me USING (mention_id)
                          WHERE m.src_table=? AND m.raw_name ILIKE ?""", [table, name_like]).fetchall()


def test_er_merges_variants(loaded):
    assert _entity_of(loaded, "awards", "Rapid Response%") == _entity_of(loaded, "awards", "Rapid Response Tree Service")
    assert len(_entity_of(loaded, "awards", "Rapid Response%")) == 1
    assert len(_entity_of(loaded, "awards", "Bayview%")) == 1


def test_er_keeps_distinct_firms_apart(loaded):
    assert _entity_of(loaded, "contributions", "Acme Plumbing") != _entity_of(loaded, "awards", "Acme Paving LLC")


def test_er_links_employer_to_vendor(loaded):
    emp = loaded.execute("""SELECT me.entity_id FROM mentions m JOIN mention_entity me USING (mention_id)
                            WHERE m.role='employer' AND m.raw_name='Acme Paving Inc'""").fetchone()
    assert [emp] == _entity_of(loaded, "awards", "Acme Paving LLC")


def test_er_noise_employers_dropped(loaded):
    assert loaded.execute("SELECT count(*) FROM mentions WHERE role='employer' AND raw_name='Retired'").fetchone()[0] == 0


# ─── rules ───────────────────────────────────────────────────────────────────

def test_donation_near_award(loaded):
    [f] = flags(loaded, "donation_near_award")
    ev = json.loads(f["evidence"])
    assert f["entity_name"] == "Acme Paving LLC" and f["score"] == 70
    links = sorted(c["link"] for c in ev["contributions"])
    # ELEC + employer link; the BE copy of the same $2,600 is de-duplicated
    assert links == ["contributor", "employer"]
    assert "5,700" not in f["summary"] and "3,100" in f["summary"]
    # Acme Plumbing gave to the same committee but is a different firm
    assert all("Plumbing" not in json.dumps(c) for c in ev["contributions"])


def test_mapped_to_other_body_suppressed(loaded):
    # Shoreline gave to a committee mapped to the State, not the Borough
    assert not any("Shoreline" in (f["entity_name"] or "") for f in flags(loaded, "donation_near_award"))


def test_missing_be(loaded):
    names = {f["entity_name"] for f in flags(loaded, "missing_be_disclosure")}
    assert names == {"Bayview Construction Co", "Coastal Supply Corp", "Shoreline Engineering Associates"}


def test_missing_be_silent_without_be_coverage(con):
    loaders.load_csv(con, "awards", FX / "awards.csv")
    resolve.resolve(con)
    rules.run_all(con)
    assert flags(con, "missing_be_disclosure") == []


def test_aggregate_over_threshold(loaded):
    [f] = flags(loaded, "aggregate_over_bid_threshold")
    assert f["entity_name"] == "Coastal Supply Corp" and "55,000" in f["summary"]


def test_split_awards(loaded):
    [f] = flags(loaded, "split_awards")
    assert f["entity_name"] == "Shoreline Engineering Associates" and f["score"] == 40


def test_change_order_growth(loaded):
    [f] = flags(loaded, "change_order_growth")
    assert "+35%" in f["summary"]


def test_repeat_noncompetitive(loaded):
    by = {f["entity_name"]: f["score"] for f in flags(loaded, "repeat_noncompetitive")}
    assert by == {"Rapid Response Tree Service": 25, "Shoreline Engineering Associates": 20}


def test_employee_vendor_link(loaded):
    [f] = flags(loaded, "employee_vendor_link")
    assert f["entity_name"] == "Harborview Consulting" and f["score"] == 55


def test_shared_address(loaded):
    [f] = flags(loaded, "shared_vendor_address")
    assert "3 vendors at 100 CORPORATE BLVD" in f["summary"]


def test_payroll(loaded):
    assert len(flags(loaded, "overtime_outlier")) == 1
    [f] = flags(loaded, "multiple_public_payrolls")
    assert "Borough of Example, Monmouth County" in f["summary"]


def test_report_has_disclaimer_and_citations(loaded, tmp_path):
    fl = report.fetch(loaded)
    md = report.to_markdown(fl)
    assert report.DISCLAIMER in md and "awards.csv:2" in md
    out = tmp_path / "f.csv"
    report.write_csv(fl, out)
    assert out.read_text().count("\n") == len(fl) + 1
