"""DuckDB schema. Every source row keeps (file_id, source_row, raw) so any
flag can be traced back to the exact line of the exact file it came from."""

DDL = """
CREATE SEQUENCE IF NOT EXISTS file_seq;
CREATE SEQUENCE IF NOT EXISTS rec_seq;

CREATE TABLE IF NOT EXISTS source_files (
    file_id INTEGER PRIMARY KEY DEFAULT nextval('file_seq'),
    source_type VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL UNIQUE,
    row_count INTEGER,
    loaded_at TIMESTAMP DEFAULT current_timestamp,
    note VARCHAR
);

-- ELEC contribution search exports (and any other contribution source).
CREATE TABLE IF NOT EXISTS contributions (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    contributor_name VARCHAR, contributor_kind VARCHAR,  -- org | person
    street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR,
    employer VARCHAR, occupation VARCHAR,
    recipient VARCHAR, amount DOUBLE, contribution_date DATE, election_year INTEGER
);

-- Form BE (pay-to-play annual business entity disclosure). One row per
-- reported contract or reported contribution.
CREATE TABLE IF NOT EXISTS be_disclosures (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    business_name VARCHAR, street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR,
    filing_year INTEGER, record_kind VARCHAR,          -- contract | contribution
    counterparty VARCHAR,                              -- public entity or recipient committee
    amount DOUBLE, record_date DATE
);

-- Awards from resolutions / bid tabs, including change orders.
CREATE TABLE IF NOT EXISTS awards (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    public_body VARCHAR, vendor_name VARCHAR,
    street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR,
    amount DOUBLE, award_date DATE, award_type VARCHAR,
    resolution_no VARCHAR, contract_ref VARCHAR, parent_contract_ref VARCHAR,
    description VARCHAR
);

-- Check registers / bills lists.
CREATE TABLE IF NOT EXISTS payments (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    public_body VARCHAR, vendor_name VARCHAR,
    street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR,
    amount DOUBLE, payment_date DATE, check_no VARCHAR, description VARCHAR
);

-- Payroll (OPRA / pension data).
CREATE TABLE IF NOT EXISTS employees (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    public_body VARCHAR, name VARCHAR, title VARCHAR,
    street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR,
    pay_year INTEGER, base_pay DOUBLE, overtime DOUBLE, total_pay DOUBLE
);

-- Which committee "belongs" to which awarding body (e.g. a county party
-- committee or a commissioner's candidate committee -> the County). Analyst
-- maintained; nothing in the public data gives this mapping cleanly.
CREATE TABLE IF NOT EXISTS recipient_map (
    recipient VARCHAR, recipient_norm VARCHAR, public_body VARCHAR,
    committee_type VARCHAR,   -- candidate | party | pac | other
    note VARCHAR
);

-- Public bodies: type drives which statute is cited and the fiscal year
-- (schools run July-June). body_group ties related bodies (shared-services
-- partners, a consolidated district's predecessors) so splitting across
-- them is visible. aliases: ';'-separated spellings seen in source files.
CREATE TABLE IF NOT EXISTS public_bodies (
    name VARCHAR, body_type VARCHAR, fy_start_month INTEGER,
    body_group VARCHAR, successor VARCHAR, aliases VARCHAR,
    has_qpa BOOLEAN, note VARCHAR
);

-- Official disclosure statements: School Ethics Act personal/relative and
-- financial disclosures (N.J.S.A. 18A:12-25, -26) and Local Government
-- Ethics Law FDS (N.J.S.A. 40A:9-22.6). One row per disclosed business.
CREATE TABLE IF NOT EXISTS disclosures (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    public_body VARCHAR, official_name VARCHAR, role VARCHAR,
    street VARCHAR, city VARCHAR, state VARCHAR, zip VARCHAR,
    business_name VARCHAR, business_street VARCHAR, business_zip VARCHAR,
    relationship VARCHAR, filing_year INTEGER,
    -- item: income_source | business_interest | contract_business | fee | gift |
    --       relative_employed | relative_contract | answer:<question>
    item VARCHAR, related_person VARCHAR, detail VARCHAR
);

-- Audit findings: school Auditor's Management Report (AMR), municipal audit
-- "General Comments and Recommendations", single-audit findings. A row with
-- category 'none' records an audit reported with no findings (so absence is
-- evidence, not a gap). fiscal_year = FY end year.
CREATE TABLE IF NOT EXISTS audit_findings (
    id BIGINT PRIMARY KEY DEFAULT nextval('rec_seq'),
    file_id INTEGER, source_row INTEGER, raw JSON,
    public_body VARCHAR, fiscal_year INTEGER, auditor VARCHAR, report_type VARCHAR,
    finding_no VARCHAR, category VARCHAR, is_repeat BOOLEAN,
    finding VARCHAR, recommendation VARCHAR, vendor VARCHAR
);

-- Board-approved bills totals from minutes/agendas ("To approve the BILLS &
-- CLAIMS for January 2025 in the amount of $2,206,520.53"). Control totals:
-- an OPRA'd itemized bills list for that month must foot to this.
CREATE TABLE IF NOT EXISTS bill_approvals (
    public_body VARCHAR, meeting_date DATE, period VARCHAR, period_month DATE,
    kind VARCHAR,              -- bills | payroll
    amount DOUBLE, doc_class VARCHAR, sha256 VARCHAR, page INTEGER, text VARCHAR
);

-- Entity resolution output.
CREATE TABLE IF NOT EXISTS mentions (
    mention_id BIGINT, src_table VARCHAR, src_id BIGINT, role VARCHAR, kind VARCHAR,
    raw_name VARCHAR, norm_name VARCHAR, norm_addr VARCHAR, zip5 VARCHAR
);
CREATE TABLE IF NOT EXISTS er_edges (
    a BIGINT, b BIGINT, score DOUBLE, method VARCHAR
);
CREATE TABLE IF NOT EXISTS mention_entity (
    mention_id BIGINT, entity_id BIGINT
);
CREATE TABLE IF NOT EXISTS entities (
    entity_id BIGINT, kind VARCHAR, canonical_name VARCHAR, n_mentions INTEGER
);

-- Fetched documents and their custody log (fetch.py).
CREATE TABLE IF NOT EXISTS documents (
    sha256 VARCHAR PRIMARY KEY, source VARCHAR, public_body VARCHAR, url VARCHAR, title VARCHAR,
    doc_class VARCHAR, doc_date DATE, content_type VARCHAR, bytes BIGINT, local_path VARCHAR,
    first_seen TIMESTAMP, text_extracted BOOLEAN DEFAULT false
);
CREATE TABLE IF NOT EXISTS retrievals (
    url VARCHAR, referrer VARCHAR, title VARCHAR, retrieved_at TIMESTAMP, http_status INTEGER,
    etag VARCHAR, last_modified VARCHAR, sha256 VARCHAR, error VARCHAR
);
CREATE TABLE IF NOT EXISTS doc_text (
    sha256 VARCHAR, page INTEGER, text VARCHAR
);

CREATE TABLE IF NOT EXISTS flags (
    rule VARCHAR, score DOUBLE, public_body VARCHAR, entity_id BIGINT,
    entity_name VARCHAR, summary VARCHAR, evidence JSON,
    created_at TIMESTAMP DEFAULT current_timestamp
);
"""


# Columns added after a table first shipped. CREATE IF NOT EXISTS won't add
# them to an existing database file.
MIGRATIONS = [
    ("public_bodies", "has_qpa", "BOOLEAN"),
    ("recipient_map", "committee_type", "VARCHAR"),
    ("disclosures", "item", "VARCHAR"),
    ("disclosures", "related_person", "VARCHAR"),
    ("disclosures", "detail", "VARCHAR"),
]


def init(con):
    con.execute(DDL)
    for table, col, typ in MIGRATIONS:
        con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")


def bulk_insert(con, table, cols, rows):
    """executemany in DuckDB is ~1ms/row; go through a DataFrame instead."""
    if not rows:
        return
    import pandas as pd
    df = pd.DataFrame(rows, columns=cols, dtype=object)  # object: keep None/date/str as-is
    con.register("_bulk", df)
    try:
        con.execute(f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _bulk")
    finally:
        con.unregister("_bulk")
