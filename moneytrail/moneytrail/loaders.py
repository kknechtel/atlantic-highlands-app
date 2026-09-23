"""CSV loaders with header aliasing.

Source files are messy and column names drift between exports, so each
canonical field lists header aliases (compared case/space/punctuation
insensitive). Required fields that can't be mapped fail loudly: a silent
mis-map is worse than no load.

Files are identified by sha256; re-loading the same file is a no-op.
"""
import csv
import hashlib
import json
import re

from moneytrail import normalize as N
from moneytrail.schema import bulk_insert

SPECS = {
    "contributions": {
        "fields": {
            "contributor_name": ["contributor_name", "contributor", "name", "noninidname", "nonindname", "entity_name"],
            "first_name": ["first_name", "firstname", "first"],
            "last_name": ["last_name", "lastname", "last"],
            "contributor_kind": ["contributor_kind", "contributor_type", "contype", "type_of_contributor"],
            "street": ["street", "street1", "address", "address1", "contributor_address"],
            "city": ["city"], "state": ["state"], "zip": ["zip", "zipcode", "zip_code", "postal_code"],
            "employer": ["employer", "empname", "employer_name"],
            "occupation": ["occupation", "occupationname", "occupation_name"],
            "recipient": ["recipient", "recipient_name", "committee", "committee_name", "candidate", "entityname_recipient"],
            "amount": ["amount", "contribution_amount", "contributionamount", "contamt"],
            "contribution_date": ["contribution_date", "contributiondate", "date", "contdate"],
            "election_year": ["election_year", "electionyear", "year"],
        },
        "required": ["recipient", "amount", "contribution_date"],
        "dates": ["contribution_date"], "amounts": ["amount"], "ints": ["election_year"],
    },
    "be_disclosures": {
        "fields": {
            "business_name": ["business_name", "business_entity", "entity_name", "name", "vendor"],
            "street": ["street", "address", "address1"], "city": ["city"], "state": ["state"],
            "zip": ["zip", "zipcode", "zip_code"],
            "filing_year": ["filing_year", "year", "report_year"],
            "record_kind": ["record_kind", "kind", "type"],
            "counterparty": ["counterparty", "public_entity", "recipient", "agency", "committee"],
            "amount": ["amount", "contract_amount", "contribution_amount"],
            "record_date": ["record_date", "date", "contribution_date", "contract_date"],
        },
        "required": ["business_name", "filing_year", "record_kind", "counterparty"],
        "dates": ["record_date"], "amounts": ["amount"], "ints": ["filing_year"],
    },
    "awards": {
        "fields": {
            "public_body": ["public_body", "entity", "agency", "municipality", "awarding_body"],
            "vendor_name": ["vendor_name", "vendor", "contractor", "awardee", "payee"],
            "street": ["street", "address", "vendor_address"], "city": ["city"], "state": ["state"],
            "zip": ["zip", "zipcode", "zip_code"],
            "amount": ["amount", "award_amount", "contract_amount", "not_to_exceed"],
            "award_date": ["award_date", "date", "resolution_date", "adopted"],
            "award_type": ["award_type", "type", "contract_type", "procurement_method"],
            "resolution_no": ["resolution_no", "resolution", "resolution_number"],
            "contract_ref": ["contract_ref", "contract_no", "contract_number", "bid_no"],
            "parent_contract_ref": ["parent_contract_ref", "original_contract", "parent_contract"],
            "description": ["description", "title", "purpose"],
        },
        "required": ["public_body", "vendor_name", "amount", "award_date"],
        "dates": ["award_date"], "amounts": ["amount"], "ints": [],
    },
    "payments": {
        "fields": {
            "public_body": ["public_body", "entity", "agency", "municipality"],
            "vendor_name": ["vendor_name", "vendor", "payee", "name"],
            "street": ["street", "address"], "city": ["city"], "state": ["state"],
            "zip": ["zip", "zipcode", "zip_code"],
            "amount": ["amount", "check_amount", "payment_amount"],
            "payment_date": ["payment_date", "check_date", "date"],
            "check_no": ["check_no", "check_number", "check"],
            "description": ["description", "purpose", "memo", "account"],
        },
        "required": ["public_body", "vendor_name", "amount", "payment_date"],
        "dates": ["payment_date"], "amounts": ["amount"], "ints": [],
    },
    "employees": {
        "fields": {
            "public_body": ["public_body", "entity", "agency", "employer"],
            "name": ["name", "employee", "employee_name"],
            "first_name": ["first_name", "firstname"], "last_name": ["last_name", "lastname"],
            "title": ["title", "position", "job_title"],
            "street": ["street", "address"], "city": ["city"], "state": ["state"],
            "zip": ["zip", "zipcode", "zip_code"],
            "pay_year": ["pay_year", "year", "calendar_year"],
            "base_pay": ["base_pay", "salary", "base_salary"],
            "overtime": ["overtime", "overtime_pay", "ot"],
            "total_pay": ["total_pay", "gross_pay", "total"],
        },
        "required": ["public_body"],
        "dates": [], "amounts": ["base_pay", "overtime", "total_pay"], "ints": ["pay_year"],
    },
    "public_bodies": {
        "fields": {
            "name": ["name", "public_body", "entity"],
            "body_type": ["body_type", "type"],
            "fy_start_month": ["fy_start_month", "fiscal_year_start_month"],
            "body_group": ["body_group", "group"],
            "successor": ["successor", "successor_body"],
            "aliases": ["aliases", "alias", "aka"],
            "note": ["note", "notes"],
        },
        "required": ["name"],
        "dates": [], "amounts": [], "ints": ["fy_start_month"],
    },
    "disclosures": {
        "fields": {
            "public_body": ["public_body", "board", "entity", "agency"],
            "official_name": ["official_name", "official", "name", "filer"],
            "role": ["role", "position", "title", "office"],
            "street": ["street", "address", "home_address"], "city": ["city"], "state": ["state"],
            "zip": ["zip", "zipcode", "zip_code"],
            "business_name": ["business_name", "business", "disclosed_business", "income_source", "entity_name"],
            "business_street": ["business_street", "business_address"],
            "business_zip": ["business_zip"],
            "relationship": ["relationship", "relation", "whose_interest"],
            "filing_year": ["filing_year", "year"],
        },
        "required": ["public_body", "official_name"],
        "dates": [], "amounts": [], "ints": ["filing_year"],
    },
    "recipient_map": {
        "fields": {
            "recipient": ["recipient", "committee", "recipient_name"],
            "public_body": ["public_body", "entity", "agency"],
            "note": ["note", "notes"],
        },
        "required": ["recipient", "public_body"],
        "dates": [], "amounts": [], "ints": [],
    },
}

PERSON_NAME_TABLES = {"contributions": "contributor_name", "employees": "name"}


def _key(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _map_headers(headers, spec):
    keyed = {_key(h): h for h in headers}
    out = {}
    for field, aliases in spec["fields"].items():
        for a in aliases:
            if _key(a) in keyed:
                out[field] = keyed[_key(a)]
                break
    return out


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(con, source_type, path, note=None):
    """Load one CSV. Returns (file_id, rows_loaded); rows_loaded is None when
    the identical file was already loaded."""
    if source_type not in SPECS:
        raise ValueError(f"unknown source type {source_type!r}; one of {sorted(SPECS)}")
    spec = SPECS[source_type]
    digest = _sha256(path)
    hit = con.execute("SELECT file_id FROM source_files WHERE sha256 = ?", [digest]).fetchone()
    if hit:
        return hit[0], None

    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        colmap = _map_headers(reader.fieldnames or [], spec)
        name_field = PERSON_NAME_TABLES.get(source_type)
        missing = [r for r in spec["required"] if r not in colmap]
        if name_field and name_field not in colmap and "last_name" not in colmap:
            missing.append(f"{name_field} (or first_name/last_name)")
        if missing:
            raise ValueError(f"{path}: cannot map required column(s) {missing}; headers were {reader.fieldnames}")
        rows = list(reader)

    table_cols = [c for c in spec["fields"] if c not in ("first_name", "last_name")]
    if source_type == "recipient_map":
        table_cols.append("recipient_norm")

    records, errors = [], []
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        rec = {c: (row.get(colmap[c]) or "").strip() or None if c in colmap else None for c in table_cols}
        if name_field and not rec.get(name_field):
            first = (row.get(colmap.get("first_name", ""), "") or "").strip()
            last = (row.get(colmap.get("last_name", ""), "") or "").strip()
            rec[name_field] = f"{first} {last}".strip() or None
        try:
            for c in spec["dates"]:
                rec[c] = N.parse_date(rec[c])
            for c in spec["amounts"]:
                rec[c] = N.parse_amount(rec[c])
            for c in spec["ints"]:
                rec[c] = int(float(rec[c])) if rec[c] else None
        except ValueError as e:
            errors.append(f"line {i}: {e}")
            continue
        if source_type == "contributions":
            kind = (rec.get("contributor_kind") or "").lower()
            if kind.startswith("ind") or kind == "person":
                rec["contributor_kind"] = "person"
            elif kind:
                rec["contributor_kind"] = "org"
            else:
                rec["contributor_kind"] = "org" if N.looks_like_org(rec["contributor_name"]) else "person"
        if source_type == "be_disclosures":
            rec["record_kind"] = "contribution" if "contrib" in (rec["record_kind"] or "").lower() else "contract"
        if source_type in ("awards",) and rec.get("award_type"):
            rec["award_type"] = re.sub(r"[^a-z]+", "_", rec["award_type"].lower()).strip("_")
        if source_type == "recipient_map":
            rec["recipient_norm"] = N.norm_org(rec["recipient"])
        if source_type == "public_bodies" and rec.get("body_type"):
            rec["body_type"] = rec["body_type"].lower()
        rec["_line"] = i
        rec["_raw"] = json.dumps(row)
        records.append(rec)

    if errors:
        raise ValueError(f"{path}: {len(errors)} bad row(s), nothing loaded:\n  " + "\n  ".join(errors[:20]))

    file_id = con.execute(
        "INSERT INTO source_files (source_type, path, sha256, row_count, note) VALUES (?, ?, ?, ?, ?) RETURNING file_id",
        [source_type, str(path), digest, len(records), note],
    ).fetchone()[0]
    if source_type in ("recipient_map", "public_bodies"):
        cols, vals = table_cols, [[r[c] for c in table_cols] for r in records]
    else:
        cols = ["file_id", "source_row", "raw"] + table_cols
        vals = [[file_id, r["_line"], r["_raw"]] + [r[c] for c in table_cols] for r in records]
    bulk_insert(con, source_type, cols, vals)
    return file_id, len(records)
