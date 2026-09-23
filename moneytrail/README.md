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
| `donation_near_award` | A vendor-linked contribution falls 365 days before to 90 days after an award. Bonus points for the 19:44A-20.5 pattern (award > $17.5k, contribution > $300 before it) and for a recipient mapped to the awarding body. Contributions to committees mapped to a *different* body are dropped. A BE copy of an ELEC contribution is counted once. |
| `missing_be_disclosure` | A vendor received ≥ $50k in a year per loaded data and no Form BE was found for that year. Runs only if BE data is loaded. |
| `aggregate_over_bid_threshold` | Fiscal-year payments to one vendor exceed the bid threshold and the body has no bid or exempt award on file for it. Runs only for bodies that have award data. |
| `split_awards` | Two or more awards from one body or body group to one vendor, each 80–100% of the bid threshold, within 365 days. |
| `change_order_growth` | Cumulative change orders exceed 20% of the original contract (N.J.A.C. 5:30-11). |
| `repeat_noncompetitive` | Two or more sole-source/emergency awards to one vendor within 730 days. |
| `employee_vendor_link` | A vendor's street address matches an employee's, or a sole-prop vendor's name matches an employee's name. |
| `shared_vendor_address` | Three or more distinct vendors share one street address. |
| `official_disclosed_business_vendor` / `official_vendor_link` | A business an official disclosed is a vendor, or an official's address or name matches a vendor. |
| `overtime_outlier` / `multiple_public_payrolls` | Overtime above 50% of base pay, or one person on two or more public payrolls in the same year. |

Thresholds are in `config.py`. **Check the bid threshold against the current
Local Finance Notice.**

## Tests

```bash
python -m pytest -q tests
```

The fixtures in `tests/fixtures/` are synthetic. Names are fictional.

## Next

1. Get a real ELEC export and a year of Monmouth County resolutions, then fix the header aliases.
2. Add a resolution PDF → `awards` extractor (reuse `api/services/pdfplumber_service.py`).
3. Add NJ business registry officers/agents as mentions, for shell and officer-overlap rules.
4. Add a BE ↔ ELEC mismatch rule: a contribution reported on one form but not the other.
5. Add cross-municipality professional overlap once more than one town is loaded.
6. Load federal data: USAspending, SAM exclusions, FAC single audits.
