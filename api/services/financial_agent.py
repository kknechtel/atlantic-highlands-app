"""
Financial agent orchestrator: deep-dive drills on extracted statements.

Four parallel drill agents, each focused:
  - revenue_drill        — property tax composition, state aid, local revenue, federal
  - expenditure_drill    — by function (instruction/admin/facilities) + by object (salaries/benefits/services)
  - debt_drill           — outstanding debt, debt service ratio, capital reserve
  - fund_balance_drill   — multi-year fund balance trajectory, restricted/assigned/unassigned

Then a synthesis agent ties them together.

Results land in FinancialStatement.drill_results JSONB:
  {
    "revenue":     {findings: [...], narrative: "...", run_at: ...},
    "expenditure": {...},
    "debt":        {...},
    "fund_balance":{...},
    "synthesis":   {executive_summary: "...", red_flags: [...], questions_to_ask: [...]}
  }
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)


# ─── Drill prompts ───────────────────────────────────────────────────────────

REVENUE_PROMPT_SCHOOL = """You are an analyst examining REVENUE on a NJ school district financial statement
(GAAP/GASB basis under SFRA — School Funding Reform Act, P.L. 2007 c.260).

ENTITY: {entity_name}
FISCAL YEAR: {fiscal_year}  (NJ schools FY = July 1 to June 30)
TYPE: {statement_type}
TOTAL REVENUE: {total_revenue}

PRIOR YEAR REVENUE (context):
{prior_year_summary}

REVENUE LINE ITEMS:
{line_items_json}

NJ SCHOOL REVENUE STRUCTURE:
- Local Tax Levy (the main local source — board-set, capped at 2% by N.J.S.A. 18A:7F-37 with adjustment exclusions)
- State Aid (SFRA categorical aid):
    * Equalization Aid (largest, formula-based on local fair share)
    * Special Education Categorical Aid (per-pupil + census-based)
    * Security Aid
    * Transportation Aid
    * Preschool Education Aid (PEA) — only for districts with state-approved preschool
    * School Choice Aid — for Interdistrict Public School Choice districts
    * Extraordinary Special Education Aid — paid in arrears for individual SpEd students >$40K (lumpy)
    * Adjustment Aid — LARGELY PHASED OUT under S2 (2018); FY26 budget eliminated for most. Don't expect for HHRSD.
    * Stabilization / Hold-Harmless Aid (created FY25/FY26 to limit cuts to losing districts)
    * Educational Adequacy Aid (former Abbotts, narrow)
- Federal Aid: IDEA, Title I-IV, Perkins (in Special Revenue Fund 20, NOT counted as state aid)
- Other Local: Tuition received, interest, rental, miscellaneous

Produce JSON:
{{
  "composition": [
    {{"category": "Local Tax Levy|Equalization Aid|Special Ed Categorical|Security Aid|Transportation Aid|Preschool Ed Aid|Choice Aid|Extraordinary SpEd Aid|Stabilization Aid|Federal IDEA|Federal Title I|Tuition Received|Other",
      "amount": 0, "pct_of_total": 0, "yoy_change_pct": 0}}
  ],
  "tax_levy_within_2pct_cap": true,
  "tax_levy_cap_analysis": "narrative — was the 2% cap respected? any banked cap used?",
  "state_aid_total": 0,
  "state_aid_yoy_pct": 0,
  "key_findings": [{{"finding": "...", "evidence": "...", "concern_level": "info|warn|high"}}],
  "trends": "narrative paragraph",
  "questions": ["specific questions a board member or resident should ask"]
}}

Output ONLY valid JSON. No fences."""


REVENUE_PROMPT_MUNI = """You are an analyst examining REVENUE on a NJ MUNICIPAL financial statement (Borough of Atlantic Highlands).

CRITICAL: NJ municipalities use REGULATORY BASIS accounting (per N.J.A.C. 5:30, NOT GAAP). The Annual Financial Statement (AFS) is filed with DLGS each February 10 for calendar-year municipalities.

ENTITY: {entity_name}
FISCAL YEAR: {fiscal_year}  (NJ municipalities default to Calendar Year, Jan-Dec; AH is calendar year)
TYPE: {statement_type}
TOTAL REVENUE: {total_revenue}

PRIOR YEAR REVENUE (context):
{prior_year_summary}

REVENUE LINE ITEMS:
{line_items_json}

NJ MUNICIPAL CURRENT FUND REVENUE STRUCTURE:
- Local Property Tax (current year levy — this is the largest line for most NJ towns)
- "Surplus Anticipated" — fund balance USED as anticipated revenue (don't double-count as new revenue)
- State Aid:
    * Energy Tax Receipts (ETR) — historically split with CMPTRA but for FY26+ CMPTRA was FULLY CONSOLIDATED INTO ETR; expect $0 CMPTRA on FY26+ AFS without flagging it as a decline
    * Garden State Trust (small, dedicated)
    * Transitional Aid (only for distressed municipalities — NOT typical for AH)
    * Highlands Protection Fund Aid (NW NJ Highlands Council municipalities ONLY — NOT Atlantic Highlands; the name is coincidence)
- Local Revenue / Misc Anticipated:
    * Licenses, Fees, Permits, Construction Code, Beach/Harbor fees, Rental
    * Interest on Investments / Deposits
    * PILOT (Payment in Lieu of Taxes) from tax-exempt entities
    * Court fines, parking enforcement
- Dedicated Grants (small but recurring):
    * Recycling Tonnage Grant
    * Clean Communities Grant
    * Body Armor Replacement
    * Drunk Driving Enforcement Fund
    * NJDOT Local Aid / Municipal Aid (capital grants)
- Receivables / Reserve for Receivables (regulatory-basis quirk; not new revenue)

Produce JSON:
{{
  "composition": [
    {{"category": "Local Property Tax|Surplus Anticipated|ETR/CMPTRA|Local Permits & Fees|PILOT|Interest|Recycling Grant|Clean Communities|NJDOT Local Aid|Other",
      "amount": 0, "pct_of_total": 0, "yoy_change_pct": 0}}
  ],
  "etr_cmptra_status": "Note CMPTRA fully consolidated into ETR for FY26+; no separate CMPTRA expected.",
  "key_findings": [{{"finding": "...", "evidence": "...", "concern_level": "info|warn|high"}}],
  "trends": "narrative paragraph",
  "questions": ["specific questions"]
}}

Output ONLY valid JSON. No fences."""


EXPENDITURE_PROMPT = """You are a municipal finance analyst examining EXPENDITURES on a NJ {entity_type} financial statement.

ENTITY: {entity_name}
FISCAL YEAR: {fiscal_year}
TOTAL EXPENDITURES: {total_expenditures}

PRIOR YEAR (context if available):
{prior_year_summary}

EXPENDITURE LINE ITEMS:
{line_items_json}

Produce JSON:
{{
  "by_function": [
    {{"function": "Regular Programs - Instruction", "amount": 0, "pct_of_total": 0, "yoy_change_pct": 0}}
  ],
  "by_object": [
    {{"object": "Salaries", "amount": 0, "pct_of_total": 0}},
    {{"object": "Benefits", ...}},
    {{"object": "Purchased Services", ...}},
    {{"object": "Supplies", ...}},
    {{"object": "Capital Outlay", ...}}
  ],
  "salary_to_total_ratio": 0.0,
  "benefits_to_salary_ratio": 0.0,
  "key_findings": [{{"finding": "...", "evidence": "...", "concern_level": "info|warn|high"}}],
  "trends": "narrative paragraph",
  "questions": ["..."]
}}

NJ SCHOOL FUNCTION CODES (parse from `function_code` field if present):
  100=Regular Instruction, 200=Special Ed, 218=Speech, 230=Basic Skills,
  240=Bilingual, 401=Co-curricular, 402=Athletics,
  211=Tuition, 213=Health Services, 216=Speech/OT/PT,
  301=Guidance, 302=Child Study Team, 303=Improvement of Instruction,
  310=Educational Media/Library, 320=General Admin, 321=School Admin,
  330=Central Services, 331=Admin Info Tech, 332=Required Maint, 333=Other Plant,
  340=Care/Upkeep of Grounds, 350=Security, 360=Pupil Transportation,
  401=Food Services, 700=Special Schools, 800=Charter, 900=Choice

NJ OBJECT CODES:
  100/101=Salaries, 200/270=Benefits/FICA, 300=Purchased Professional Services,
  400=Repairs/Rentals, 500=Other Purchased Services, 600=Supplies/Materials,
  700=Capital Outlay/Equipment, 800=Other Objects (debt service)

Output ONLY valid JSON."""


DEBT_PROMPT = """Analyze DEBT and CAPITAL position of this NJ {entity_type} financial statement ({accounting_basis}).

ENTITY: {entity_name}
FY: {fiscal_year}
TOTAL DEBT: {total_debt}
FUND BALANCE: {fund_balance}
TOTAL REVENUE: {total_revenue}

DEBT-RELATED LINE ITEMS:
{line_items_json}

NJ STATUTORY DEBT CAPS (use these, not generic ratios):
- NJ MUNICIPALITIES: Net debt cannot exceed 3.5% of Equalized Valuation (3-year average) — N.J.S.A. 40A:2-6. Excess requires Local Finance Board approval.
- NJ SCHOOLS: Net debt cannot exceed 4% of Equalized Valuation (county-equalized) — N.J.S.A. 18A:24-19.
- ANNUAL DEBT STATEMENT: Towns file an ADS by Jan 31; SDS before each new bond ordinance.
- For schools, debt service is in Fund 40 (Debt Service Fund), separate from operating Fund 11 — do NOT mix them.

Produce JSON:
{{
  "outstanding_debt": 0,
  "annual_debt_service": 0,
  "debt_to_revenue_ratio": 0.0,
  "debt_to_eq_valuation_pct": "if eq valuation visible in document, compute; else null",
  "statutory_cap_pct": 3.5,
  "within_statutory_cap": "true|false|unknown — needs equalized valuation data",
  "debt_per_capita": 0,
  "capital_reserve": 0,
  "debt_components": [
    {{"name": "General Obligation Bonds|BANs|Refunding Bonds|Capital Lease|Loan", "amount": 0, "maturity": "YYYY"}}
  ],
  "deferred_charges_or_emergency_authorizations": 0,
  "key_findings": [{{"finding": "...", "evidence": "...", "concern_level": "info|warn|high"}}],
  "trends": "narrative",
  "questions": ["..."]
}}

For Atlantic Highlands borough use ~4318 population; for HHRSD report debt per pupil (use ~725 students).

Output ONLY valid JSON."""


FUND_BALANCE_PROMPT_SCHOOL = """Analyze FUND BALANCE on a NJ SCHOOL DISTRICT financial statement (GAAP/GASB 54).

ENTITY: {entity_name}
FY: {fiscal_year}
FUND BALANCE: {fund_balance}
TOTAL EXPENDITURES: {total_expenditures}

FUND BALANCE / EQUITY LINE ITEMS:
{line_items_json}

PRIOR YEAR FUND BALANCES:
{prior_fund_balances}

CRITICAL NJ RULES (do NOT use GFOA's 16% benchmark for schools):
- Unrestricted general fund balance is STATUTORILY CAPPED at the GREATER of 2% of general fund expenditures OR $250,000 (N.J.S.A. 18A:7F-7).
- For a small district like Henry Hudson Regional (~725 students, ~$15-20M budget), the $250K floor often binds, not the 2% percent.
- Excess can be moved (with board action / commissioner approval where required) to:
    * Capital Reserve (N.J.S.A. 18A:21-2; -3; -4 / N.J.A.C. 6A:23A-14.1)
    * Maintenance Reserve (N.J.S.A. 18A:7F-41 / N.J.A.C. 6A:23A-14.2)
    * Current Expense Emergency Reserve (capped at $250K or 1% of GF up to $1M)
    * Tuition Reserve (sending districts, 2-year rolling)
    * Impact Aid Reserve (federal, narrow)

Produce JSON:
{{
  "total_fund_balance": 0,
  "gasb54_components": {{
    "nonspendable": 0, "restricted": 0, "committed": 0, "assigned": 0, "unassigned": 0
  }},
  "reserves": {{
    "capital_reserve": 0, "maintenance_reserve": 0, "emergency_reserve": 0,
    "tuition_reserve": 0, "impact_aid_reserve": 0
  }},
  "unrestricted_fund_balance": 0,
  "statutory_cap": 0,
  "cap_status": "under_cap|at_cap|over_cap_with_reserves|over_cap_violation",
  "cap_analysis": "narrative — calc 2% of expenditures vs $250K floor; identify if excess moved to reserves",
  "trajectory": "growing|stable|declining|volatile",
  "appropriated_for_next_year": 0,
  "key_findings": [{{"finding": "...", "evidence": "...", "concern_level": "info|warn|high"}}],
  "narrative": "Plain-English assessment",
  "questions": ["..."]
}}

Output ONLY valid JSON."""


FUND_BALANCE_PROMPT_MUNI = """Analyze FUND BALANCE on a NJ MUNICIPAL financial statement (regulatory basis, NOT GAAP).

ENTITY: {entity_name}
FY: {fiscal_year}
CURRENT FUND BALANCE: {fund_balance}
TOTAL EXPENDITURES: {total_expenditures}

FUND BALANCE / RESERVE LINE ITEMS:
{line_items_json}

PRIOR YEAR FUND BALANCES:
{prior_fund_balances}

NJ MUNICIPAL CONTEXT:
- NJ towns are NOT on GASB 54. They report regulatory-basis "Fund Balance" in the Current Fund as a single number, with reservations (e.g., "Reserve for Receivables" — a regulatory-basis quirk that doesn't represent unspent cash).
- Key health metric: ratio of UNRESERVED Current Fund balance to expenditures. DLGS Best Practices guidance flags <5% as concerning; healthy NJ Current Fund typically 8-15%.
- "Surplus regenerated" = excess of revenue realized over expenditures + reserves canceled. This is the operational signal — NOT raw revenue minus expenditures, because towns intentionally anticipate fund balance as revenue.
- "Surplus anticipated as revenue" in next year's budget = how much fund balance is being USED. Pay attention to whether the town is depleting or building.
- Atlantic Highlands operates a Water/Sewer Utility — that has SEPARATE fund balance (Utility Operating + Utility Capital) which should be analyzed separately.

Produce JSON:
{{
  "total_current_fund_balance": 0,
  "reserved_components": [
    {{"name": "Reserve for Receivables|Reserve for Encumbrances|Other", "amount": 0}}
  ],
  "unreserved_fund_balance": 0,
  "fund_balance_to_expenditure_ratio": 0.0,
  "surplus_regenerated_current_year": 0,
  "surplus_anticipated_next_year": 0,
  "fund_balance_health": "strong|adequate|concerning|critical",
  "utility_fund_balance_separate": "if water/sewer fund balance is shown, summarize separately",
  "trajectory": "growing|stable|declining|volatile",
  "key_findings": [{{"finding": "...", "evidence": "...", "concern_level": "info|warn|high"}}],
  "narrative": "Plain-English assessment using NJ municipal benchmarks (warn <5%, target ≥8% of Current Fund expenditures)",
  "questions": ["..."]
}}

Output ONLY valid JSON."""


SYNTHESIS_PROMPT = """You are senior municipal finance analyst writing an executive summary for community members reviewing the financial health of {entity_name} for FY{fiscal_year}.

You have four drill reports below. Synthesize them.

REVENUE DRILL:
{revenue_drill}

EXPENDITURE DRILL:
{expenditure_drill}

DEBT DRILL:
{debt_drill}

FUND BALANCE DRILL:
{fund_balance_drill}

DETECTED RULE-BASED ANOMALIES:
{anomaly_flags}

RECONCILIATION STATUS:
{reconcile_status}

Produce JSON:
{{
  "headline": "One-line description of the entity's financial position",
  "executive_summary": "3-5 sentence plain-English summary",
  "strengths": ["...", "..."],
  "concerns": ["...", "..."],
  "red_flags": [
    {{"flag": "...", "evidence": "...", "severity": "info|warn|high"}}
  ],
  "questions_to_ask": [
    "Specific questions a board member or resident should ask the {entity_type} administration"
  ],
  "opra_followups": [
    "Specific records a citizen could request via OPRA to investigate further"
  ]
}}

Be specific. Cite numbers. Output ONLY valid JSON."""


# ─── LLM call ────────────────────────────────────────────────────────────────


async def _call_llm(prompt: str, max_output: int = 16000) -> Optional[Dict]:
    """Try Claude first for analytical work (Sonnet 4.6 is stronger at reasoning),
    fall back to Gemini."""
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            msg = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_output,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_json(msg.content[0].text) if msg and msg.content else None
        except Exception as exc:
            logger.warning("claude drill failed: %s", exc)

    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            cfg = types.GenerateContentConfig(temperature=0.1, max_output_tokens=max_output,
                                              thinking_config=types.ThinkingConfig(thinking_budget=0))
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=cfg),
            )
            return _parse_json(response.text) if response and response.text else None
        except Exception as exc:
            logger.warning("gemini drill failed: %s", exc)
    return None


def _parse_json(text: str) -> Optional[Dict]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.startswith("json"):
            text = text[4:].strip()
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return None
        return None


# ─── Helpers to assemble inputs ──────────────────────────────────────────────


def _serialize_lines(items, max_items: int = 200) -> str:
    rows = []
    for it in items[:max_items]:
        rows.append({
            "section": it.section, "subsection": it.subsection,
            "line_name": it.line_name[:120] if it.line_name else "",
            "amount": it.amount, "prior_year_amount": it.prior_year_amount,
            "budget_amount": it.budget_amount, "variance_pct": it.variance_pct,
            "fund": it.fund, "function_code": it.function_code, "object_code": it.object_code,
            "yoy_change_pct": it.yoy_change_pct,
            "is_total_row": it.is_total_row,
        })
    return json.dumps(rows, default=str)


def _prior_year_summary(stmt, db: Session) -> str:
    from models.financial import FinancialStatement
    fy = stmt.fiscal_year
    if not fy:
        return "N/A"
    try:
        prior_fy = str(int(re.sub(r"[^0-9]", "", fy)[:4]) - 1)
    except Exception:
        return "N/A"
    prior = (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.entity_type == stmt.entity_type,
            FinancialStatement.statement_type == stmt.statement_type,
            FinancialStatement.fiscal_year.like(f"%{prior_fy}%"),
        )
        .first()
    )
    if not prior:
        return "N/A"
    return json.dumps({
        "fiscal_year": prior.fiscal_year,
        "total_revenue": prior.total_revenue,
        "total_expenditures": prior.total_expenditures,
        "fund_balance": prior.fund_balance,
        "total_debt": prior.total_debt,
    })


def _prior_fund_balances(stmt, db: Session, n: int = 5) -> str:
    from models.financial import FinancialStatement
    rows = (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.entity_type == stmt.entity_type,
            FinancialStatement.id != stmt.id,
            FinancialStatement.fund_balance.isnot(None),
        )
        .order_by(FinancialStatement.fiscal_year.desc())
        .limit(n)
        .all()
    )
    return json.dumps([{"fy": r.fiscal_year, "fund_balance": r.fund_balance} for r in rows])


# ─── Drill runners ───────────────────────────────────────────────────────────

import re  # used by _prior_year_summary


def _is_school(stmt) -> bool:
    return (stmt.accounting_basis or "").lower() == "gaap" or (stmt.entity_type or "").lower() == "school"


async def run_revenue_drill(stmt, db: Session) -> Dict:
    from models.financial import FinancialLineItem
    items = (db.query(FinancialLineItem)
             .filter(FinancialLineItem.statement_id == stmt.id,
                     FinancialLineItem.section.in_(["Revenue", "Aid"]))
             .all())
    prompt_template = REVENUE_PROMPT_SCHOOL if _is_school(stmt) else REVENUE_PROMPT_MUNI
    prompt = prompt_template.format(
        entity_name=stmt.entity_name or "?",
        fiscal_year=stmt.fiscal_year, statement_type=stmt.statement_type,
        total_revenue=stmt.total_revenue,
        prior_year_summary=_prior_year_summary(stmt, db),
        line_items_json=_serialize_lines(items),
    )
    result = await _call_llm(prompt)
    return {**(result or {"error": "drill failed"}), "run_at": datetime.utcnow().isoformat()}


async def run_expenditure_drill(stmt, db: Session) -> Dict:
    from models.financial import FinancialLineItem
    items = (db.query(FinancialLineItem)
             .filter(FinancialLineItem.statement_id == stmt.id,
                     FinancialLineItem.section.in_(["Expenditures", "Personnel", "Capital"]))
             .all())
    prompt = EXPENDITURE_PROMPT.format(
        entity_type=stmt.entity_type, entity_name=stmt.entity_name or "?",
        fiscal_year=stmt.fiscal_year,
        total_expenditures=stmt.total_expenditures,
        prior_year_summary=_prior_year_summary(stmt, db),
        line_items_json=_serialize_lines(items, max_items=300),
    )
    result = await _call_llm(prompt, max_output=24000)
    return {**(result or {"error": "drill failed"}), "run_at": datetime.utcnow().isoformat()}


async def run_debt_drill(stmt, db: Session) -> Dict:
    from models.financial import FinancialLineItem
    items = (db.query(FinancialLineItem)
             .filter(FinancialLineItem.statement_id == stmt.id)
             .filter((FinancialLineItem.section == "Debt Service") |
                     (FinancialLineItem.subsection.ilike("%debt%")) |
                     (FinancialLineItem.line_name.ilike("%debt%")) |
                     (FinancialLineItem.line_name.ilike("%bond%")))
             .all())
    prompt = DEBT_PROMPT.format(
        entity_type=stmt.entity_type, entity_name=stmt.entity_name or "?",
        accounting_basis=stmt.accounting_basis or ("gaap" if _is_school(stmt) else "nj_regulatory"),
        fiscal_year=stmt.fiscal_year,
        total_debt=stmt.total_debt, fund_balance=stmt.fund_balance, total_revenue=stmt.total_revenue,
        line_items_json=_serialize_lines(items),
    )
    result = await _call_llm(prompt)
    return {**(result or {"error": "drill failed"}), "run_at": datetime.utcnow().isoformat()}


async def run_fund_balance_drill(stmt, db: Session) -> Dict:
    from models.financial import FinancialLineItem
    items = (db.query(FinancialLineItem)
             .filter(FinancialLineItem.statement_id == stmt.id)
             .filter((FinancialLineItem.section == "Fund Balance") |
                     (FinancialLineItem.line_name.ilike("%fund balance%")) |
                     (FinancialLineItem.line_name.ilike("%reserve%")) |
                     (FinancialLineItem.line_name.ilike("%surplus%")))
             .all())
    prompt_template = FUND_BALANCE_PROMPT_SCHOOL if _is_school(stmt) else FUND_BALANCE_PROMPT_MUNI
    prompt = prompt_template.format(
        entity_name=stmt.entity_name or "?",
        fiscal_year=stmt.fiscal_year,
        fund_balance=stmt.fund_balance, total_expenditures=stmt.total_expenditures,
        line_items_json=_serialize_lines(items),
        prior_fund_balances=_prior_fund_balances(stmt, db),
    )
    result = await _call_llm(prompt)
    return {**(result or {"error": "drill failed"}), "run_at": datetime.utcnow().isoformat()}


async def run_synthesis(stmt, drills: Dict[str, Dict]) -> Dict:
    prompt = SYNTHESIS_PROMPT.format(
        entity_name=stmt.entity_name or "?",
        entity_type=stmt.entity_type,
        fiscal_year=stmt.fiscal_year,
        revenue_drill=json.dumps(drills.get("revenue", {}))[:8000],
        expenditure_drill=json.dumps(drills.get("expenditure", {}))[:8000],
        debt_drill=json.dumps(drills.get("debt", {}))[:6000],
        fund_balance_drill=json.dumps(drills.get("fund_balance", {}))[:6000],
        anomaly_flags=json.dumps(stmt.anomaly_flags or [])[:4000],
        reconcile_status=stmt.reconcile_status or "unknown",
    )
    result = await _call_llm(prompt, max_output=12000)
    return {**(result or {"error": "synthesis failed"}), "run_at": datetime.utcnow().isoformat()}


# ─── Public entry point ──────────────────────────────────────────────────────


async def run_full_drill(statement_id: str) -> Dict[str, Any]:
    """Background task: run all four drill agents in parallel + synthesis. Persists to drill_results."""
    from database import SessionLocal
    from models.financial import FinancialStatement

    db = SessionLocal()
    try:
        stmt = db.query(FinancialStatement).filter(FinancialStatement.id == statement_id).first()
        if not stmt:
            return {"error": "statement_not_found"}

        # Parallel drills
        revenue, expenditure, debt, fund_balance = await asyncio.gather(
            run_revenue_drill(stmt, db),
            run_expenditure_drill(stmt, db),
            run_debt_drill(stmt, db),
            run_fund_balance_drill(stmt, db),
            return_exceptions=False,
        )

        drills = {
            "revenue": revenue, "expenditure": expenditure,
            "debt": debt, "fund_balance": fund_balance,
        }

        synthesis = await run_synthesis(stmt, drills)
        drills["synthesis"] = synthesis

        stmt.drill_results = drills
        stmt.status = "drilled"
        db.commit()

        return drills
    except Exception as exc:
        logger.exception("run_full_drill failed for %s", statement_id)
        return {"error": str(exc)[:300]}
    finally:
        db.close()
