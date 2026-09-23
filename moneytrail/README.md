# moneytrail

Links public money **out** (awards, check-register payments, payroll) to money
**in** (political contributions, Form BE pay-to-play disclosures) through entity
resolution, then scores red flags. Standalone: DuckDB file, no dependency on the
app's Postgres.

**Every flag is a lead, not a finding.** Scores rank what to review first. They
are not probabilities of wrongdoing, and most hits have lawful explanations.

## Quick start

```bash
pip install -r requirements.txt
python -m moneytrail load contributions elec_export.csv
python -m moneytrail load be_disclosures be_2024.csv
python -m moneytrail load awards county_resolutions_2024.csv
python -m moneytrail load payments bills_list_2024.csv
python -m moneytrail load employees payroll_2024.csv
python -m moneytrail load recipient_map recipient_map.csv
python -m moneytrail load public_bodies public_bodies.csv
python -m moneytrail load disclosures school_ethics_disclosures.csv
python -m moneytrail resolve
python -m moneytrail flag
python -m moneytrail report --md flags.md --csv flags.csv --min-score 30
python -m moneytrail entity "Acme Paving"     # explain a cluster edge by edge
```

The DB defaults to `data/moneytrail.duckdb` (gitignored). Use `--db` to change it.

## Inputs

All sources load from CSV. Headers are matched against alias lists in
`loaders.py:SPECS`, ignoring case and punctuation. A required column that can't
be mapped, or any unparseable date or amount, aborts the whole file. A partial
load is never written silently. Each file is keyed by sha256, so reloading the
same file does nothing. Every row keeps `file_id`, `source_row` and the raw row
as JSON, so every flag cites `file:line`.

| type | source | required |
|---|---|---|
| `contributions` | ELEC contribution search export | recipient, amount, date, contributor name (or first/last) |
| `be_disclosures` | Form BE (N.J.S.A. 19:44A-20.27), one row per reported contract or contribution | business_name, filing_year, record_kind, counterparty |
| `audit_findings` | Audit report findings (or `extract` from fetched audits) | public_body, fiscal_year |
| `awards` | Resolutions / bid tabs, incl. change orders (`award_type=change_order`, `parent_contract_ref`) | public_body, vendor, amount, award_date |
| `payments` | Bills lists / check registers (OPRA) | public_body, vendor, amount, payment_date |
| `employees` | Payroll (OPRA) | public_body, name |
| `recipient_map` | **Analyst-maintained**: committee to the public body it's tied to | recipient, public_body |
| `public_bodies` | **Analyst-maintained**: type, fiscal-year start, group, successor, aliases | name |
| `disclosures` | Board-member / official disclosure statements: School Ethics Act (N.J.S.A. 18A:12-25, -26) and Local Government Ethics Law FDS (40A:9-22.6). One row per disclosed business. | public_body, official_name |

**ELEC is behind Incapsula bot protection.** Scripted pulls get a challenge
page, so export CSVs by hand from the ELEC search UI. The ELEC aliases in
`SPECS` (`NonIndName`, `ContributionAmount`, …) are best guesses and still need
checking against a real export. Map `award_type` values to: `bid`,
`sole_source`, `emergency`, `professional_services`, `fair_and_open`,
`state_contract`, `coop`, `change_order`, ….

## School districts

Loading school awards, bills lists and payroll works the same way as for towns.
The differences are handled through `public_bodies` (`bodies.py`):

- **Type.** A body not listed in `public_bodies` gets a type from its name
  (Board of Education / School District / ESC → `school`). School flags cite
  the Public School Contracts Law (N.J.S.A. 18A:18A-3) instead of 40A:11-3,
  and the School Ethics Act instead of the Local Government Ethics Law.
- **Fiscal year.** Schools default to July–June, and aggregation uses the body's
  fiscal year. Two $30k payments in May and August of the same calendar year
  fall in different school FYs and do not flag.
- **Aliases.** "Example Regional BOE", "…Board of Education" and "…School
  District" collapse to one canonical name at `resolve` time. The original
  spelling stays in each row's raw JSON.
- **Groups and successors.** Split-award and repeat-sole-source detection
  groups by `body_group`, falling back to `successor`. Awards spread across a
  consolidated district's predecessors, or across shared-services partners, are
  evaluated together. This matters for Henry Hudson Regional, formed 7/1/2024
  from AHSD, HHRS and HSD.
- **Officials.** `official_vendor_link` flags a vendor that is a business an
  official disclosed (self or relative). It scores higher when the official's
  own body is the one paying. It also flags a vendor that shares a home
  address with an official, or whose name matches one. Board members are
  unpaid, so they don't appear on payroll and the employee rule misses them.

School data sources: monthly bills lists approved in BOE minutes, bid and
contract resolutions, the Auditor's Management Report (AMR) findings, ACFRs
(already extracted by `api/scripts/extract_school_acfrs.py`), payroll via OPRA,
and School Ethics Commission disclosure statements.

## Pulling documents

```bash
python -m moneytrail fetch                 # crawl sources.py pages, download linked PDFs
python -m moneytrail text                  # PDF text per page (lists scanned files needing OCR)
python -m moneytrail ethics --district 1456 --body "Henry Hudson Regional School District"
python -m moneytrail extract               # audit findings + board-approved bills totals
python -m moneytrail docs [--class audit]  # inventory
python -m moneytrail manifest              # custody manifest -> reference/custody_manifest.csv
```

**Custody.** Every download is logged in `retrievals`: URL, the page that
linked it, time, HTTP status, ETag/Last-Modified and sha256. Content is stored
by hash in `data/raw/`, and a changed file under the same URL becomes a new
version instead of overwriting the old one. `data/` is gitignored and the cloud
container doesn't persist, so `reference/custody_manifest.csv` is committed.
Anyone can re-fetch a URL and check its hash. For evidentiary use, run the
fetch on durable storage.

**Sources** (`sources.py`): HHRSD BOE agendas and minutes (2023–24 through
2026–27), the ahnj.com budget, audit and records tree, and the Highlands budget,
reports, bids and Municode agendas.

**Bills lists.** HHRSD agendas and minutes approve a monthly "BILLS & CLAIMS …
in the amount of $X" but don't attach the itemized list. That list is an
immediate-access OPRA record. `extract` loads the approved totals into
`bill_approvals`, and `payments_vs_approved` reconciles an OPRA'd list to them.
Atlantic Highlands minutes from before 2013 do include itemized bills lists
(vendor, PO, amount), as scanned tables; they aren't parsed yet.
Current ahnj agendas and minutes are on ecode360, which returns 403 to scripted
access from here.

**Ethics disclosures** (`ethics.py`). NJ DOE's public School Ethics Commission
search runs on an open JSON API, which answers only with the search page's
Origin/Referer headers. Statements come in three formats: fillable form fields,
forms flattened to text (compared against a blank template), and Adobe
Fill & Sign vector overlays (OCR). Values are mapped to fields by the table's
own ruling lines. Yes/No answers are kept as `answer:<question>` rows. Town
officials' LGEL statements are at fds.dca.nj.gov, an ASP.NET form behind
Incapsula; that isn't automated yet.

**Audits** (`audit.py`). Findings are extracted from NJ audit reports in both the
current "2024-003*" format (asterisk = repeat) and the pre-2013 "12-01. That …"
format, where repeats come from the "number 12-01 is similar to that reported in
2011" line. For scanned audits only the last 15 pages are OCR'd. Minutes that
accept an ACFR/AMR "with no audit recommendations" become `category='none'`
rows, so a clean audit is recorded as data.

**Reference lists** (`reference/`): `public_bodies.csv` covers HHRSD, its three
predecessors, the two boroughs and the county. An alias can be limited by date
(`name@until=2024-06-30`) when a successor reuses a name. Loading a new version
of a reference list replaces the old one.

## Entity resolution (`resolve.py`)

Every name becomes a mention (contributor, donor's employer, BE filer, vendor,
employee). Normalization removes corporate suffixes, expands abbreviations
(ASSOC→ASSOCIATES), reorders "LAST, FIRST", and standardizes USPS street
abbreviations and units. Mentions are blocked by first name token and by zip5,
then scored with rapidfuzz `token_sort_ratio`:

- ≥ 93 → match on name alone
- ≥ 86 → match only if the zip5 or street address is the same
- ≥ 75 → match only if the street address is the same (PO boxes never count)

Clusters come from union-find. Each accepted pair is stored in `er_edges` with
its score and method, so a merge can be defended or challenged. A donor's
**employer** field links individual donors to vendors. Those links are scored
lower than direct contributions.

Known gaps: blocking misses first-token typos where neither side has a zip. There
is no business-registry data yet, so officers and registered agents don't link
entities.

## Rules (`rules.py`)

| rule | fires when |
|---|---|
| `donation_near_award` | A vendor-linked contribution falls between one year before an award and one year after it (the assumed contract term). For counties and municipalities (19:44A-20.4 / 20.5 as amended by P.L.2023 c.30) the statutory bonus needs: an award over $17,500 not made through a fair-and-open process (public bidding now counts as fair and open), and a *reportable* contribution (over $200 after 4/3/2023, over $300 before) to a *candidate committee* of an official of that body. Party-committee contributions no longer disqualify a vendor. Boards of education get the 19:44A-20.26 disclosure check instead. Contributions to committees mapped to a different body are dropped, and a BE copy of an ELEC contribution is counted once. |
| `missing_be_disclosure` | A vendor received ≥ $50k in a year per loaded data and no Form BE was found for that year. Runs only if BE data is loaded. |
| `aggregate_over_bid_threshold` | Fiscal-year payments to one vendor exceed the bid threshold and the body has no bid or exempt award on file for it. Runs only for bodies that have award data. |
| `split_awards` | Two or more awards from one body or body group to one vendor, each 80–100% of the bid threshold, within 365 days. |
| `change_order_growth` | Cumulative change orders exceed 20% of the original contract (N.J.A.C. 5:30-11). |
| `repeat_noncompetitive` | Two or more sole-source/emergency awards to one vendor within 730 days. |
| `employee_vendor_link` | A vendor's street address matches an employee's, or a sole-prop vendor's name matches an employee's name. |
| `shared_vendor_address` | Three or more distinct vendors share one street address. |
| `official_disclosed_business_vendor` / `official_vendor_link` | A business an official disclosed is a vendor, or an official's address or name matches a vendor. |
| `audit_vendor_named` / `repeat_audit_finding` | A vendor is named in an audit finding, or a body has findings in the same area in consecutive years or marked repeat. Other flags on a body get +10 when it has findings in the matching area (procurement or payroll), and a zero-point note when its audits were clean. |
| `payments_vs_approved` | An itemized bills list for a month doesn't foot to the board-approved total (tolerance 0.5%). |
| `overtime_outlier` / `multiple_public_payrolls` | Overtime above 50% of base pay, or one person on two or more public payrolls in the same year. |

Thresholds and citations are in `config.py`. They were checked against primary
sources on 2026-09-23: LFN 2025-08, LFN 2023-14, and the text of P.L.2023 c.30.
Bid thresholds depend on the date:

| | with QPA | LPCL, no QPA | PSCL, no QPA |
|---|---|---|---|
| from 7/1/2025 | $53,000 | $17,500 | $39,000 |
| 7/1/2020 to 6/30/2025 | $44,000 | $17,500 | $32,000 |

Set `has_qpa` per body in `public_bodies`. If it's missing, a QPA is assumed.
That uses the higher threshold, so it produces fewer flags. The next adjustment
is due 7/1/2030.

## Tests

```bash
python -m pytest -q tests
```

The fixtures in `tests/fixtures/` are synthetic. Names are fictional.

## Next

1. OPRA HHRSD's itemized bills lists (immediate access) and load them as `payments`. `payments_vs_approved` then reconciles them to the 36 months of approved totals already extracted.
2. Parse the itemized bills tables in pre-2013 Atlantic Highlands minutes, which are already OCR'd.
3. Build a DCA LGEL disclosure scraper (fds.dca.nj.gov) for borough and county officials.
4. Build an awards extractor for "To approve the proposal from X … $Y" items in BOE minutes.
5. OCR the 75 remaining scanned documents (mostly pre-2013 borough minutes and budgets).
6. Add NJ business registry officers/agents; BE ↔ ELEC mismatch; federal data.
