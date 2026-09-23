"""Red-flag rules. Each rule returns flag dicts; run_all() writes them.

Scores are additive and every component is recorded in evidence["score_parts"]
so the number can be defended line by line. A score ranks leads for review;
it is not a probability of wrongdoing, and most hits will have lawful
explanations (disclosed contributions, fair-and-open awards, legitimate
emergencies). Treat accordingly before anything leaves the building.
"""
import json
from collections import defaultdict
from datetime import timedelta

from moneytrail import config as C
from moneytrail import normalize as N
from moneytrail.schema import bulk_insert

REC_ENTITY_VIEW = """
CREATE OR REPLACE VIEW rec_entity AS
SELECT m.src_table, m.src_id, m.role, m.kind, m.norm_name, m.norm_addr, m.zip5, me.entity_id
FROM mentions m JOIN mention_entity me USING (mention_id);
"""


def _setup(con):
    try:
        con.create_function("norm_org", N.norm_org, ["VARCHAR"], "VARCHAR")
    except Exception:
        pass  # already registered on this connection
    con.execute(REC_ENTITY_VIEW)


def _names(con):
    return dict(con.execute("SELECT entity_id, canonical_name FROM entities").fetchall())


def _cite(con, table, ids):
    if not ids:
        return []
    q = f"""SELECT t.id, sf.path, t.source_row FROM {table} t JOIN source_files sf USING (file_id)
            WHERE t.id IN ({','.join('?' * len(ids))}) ORDER BY t.id"""
    return [{"table": table, "id": i, "file": p, "line": ln} for i, p, ln in con.execute(q, list(ids)).fetchall()]


def _flag(rule, parts, body, eid, names, summary, **evidence):
    score = max(0, min(100, sum(v for _, v in parts)))
    evidence["score_parts"] = parts
    return {"rule": rule, "score": score, "public_body": body, "entity_id": eid,
            "entity_name": names.get(eid), "summary": summary, "evidence": evidence}


def _has_rows(con, table, where="TRUE"):
    return con.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0] > 0


# ─── 1. Contributions near awards ────────────────────────────────────────────

def donation_near_award(con, names):
    mapped_any = _has_rows(con, "recipient_map")
    rows = con.execute(f"""
        WITH aw AS (
            SELECT a.id, a.public_body, a.amount, a.award_date, a.award_type, re.entity_id
            FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
        ), ct AS (
            SELECT 'contributions' AS tbl, c.id, c.recipient, c.amount, c.contribution_date AS d,
                   re.role AS link, re.entity_id
            FROM contributions c JOIN rec_entity re
              ON re.src_table='contributions' AND re.src_id=c.id AND re.role IN ('contributor','employer')
            UNION ALL
            SELECT 'be_disclosures', b.id, b.counterparty, b.amount, b.record_date, 'be_self_report', re.entity_id
            FROM be_disclosures b JOIN rec_entity re ON re.src_table='be_disclosures' AND re.src_id=b.id
            WHERE b.record_kind='contribution' AND b.record_date IS NOT NULL
              -- the same contribution usually appears in ELEC too; count it once
              AND NOT EXISTS (
                SELECT 1 FROM contributions c2 JOIN rec_entity r2
                  ON r2.src_table='contributions' AND r2.src_id=c2.id AND r2.role='contributor'
                WHERE r2.entity_id = re.entity_id AND c2.amount = b.amount AND c2.contribution_date = b.record_date)
        )
        SELECT aw.id, aw.public_body, aw.amount, aw.award_date, aw.award_type, aw.entity_id,
               ct.tbl, ct.id, ct.recipient, ct.amount, ct.d, ct.link,
               date_diff('day', ct.d, aw.award_date) AS days_before,
               rm.public_body AS mapped_body
        FROM aw JOIN ct ON ct.entity_id = aw.entity_id
         AND ct.d BETWEEN aw.award_date - INTERVAL {C.P2P_LOOKBACK_DAYS} DAY
                      AND aw.award_date + INTERVAL {C.P2P_LOOKAHEAD_DAYS} DAY
        LEFT JOIN recipient_map rm ON rm.recipient_norm = norm_org(ct.recipient)
        ORDER BY aw.id, ct.d
    """).fetchall()

    by_award = defaultdict(list)
    for r in rows:
        by_award[r[:6]].append(r[6:])
    flags = []
    for (aid, body, amt, adate, atype, eid), cts in by_award.items():
        if mapped_any:
            # Drop contributions to committees mapped to some *other* body.
            cts = [c for c in cts if c[7] is None or c[7] == body]
            if not cts:
                continue
        direct = [c for c in cts if c[5] != "employer"]
        before = [c for c in direct if c[6] >= 0 and (c[3] or 0) > C.P2P_CONTRIBUTION_MIN]
        parts = [("vendor-linked contribution within window", 30)]
        if (amt or 0) > C.P2P_CONTRACT_MIN and before:
            parts.append((f"award > ${C.P2P_CONTRACT_MIN:,} with contribution > ${C.P2P_CONTRIBUTION_MIN} "
                          f"in prior {C.P2P_LOOKBACK_DAYS} days (N.J.S.A. 19:44A-20.5 pattern)", 25))
        if atype == "fair_and_open":
            parts.append(("award recorded as fair-and-open (pay-to-play limits don't apply)", -20))
        if any(c[7] == body for c in cts):
            parts.append(("recipient committee mapped to awarding body", 15))
        if not direct:
            parts.append(("linked only via donor's stated employer", -15))
        total = sum(c[3] or 0 for c in cts)
        flags.append(_flag(
            "donation_near_award", parts, body, eid, names,
            f"{names.get(eid)}: ${amt or 0:,.0f} {atype or 'award'} on {adate}; "
            f"{len(cts)} linked contribution(s) totaling ${total:,.0f}",
            award=_cite(con, "awards", [aid]),
            contributions=[{**_cite(con, c[0], [c[1]])[0], "recipient": c[2], "amount": c[3],
                            "date": str(c[4]), "link": c[5], "days_before_award": c[6]} for c in cts],
        ))
    return flags


# ─── 2. Missing Form BE ──────────────────────────────────────────────────────

def missing_be_disclosure(con, names):
    if not _has_rows(con, "be_disclosures"):
        return []  # no BE coverage loaded; absence would mean nothing
    rows = con.execute("""
        WITH money AS (
            SELECT re.entity_id, year(a.award_date) AS yr, 'awards' AS tbl, a.id, a.amount
            FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
            UNION ALL
            SELECT re.entity_id, year(p.payment_date), 'payments', p.id, p.amount
            FROM payments p JOIN rec_entity re ON re.src_table='payments' AND re.src_id=p.id AND re.role='vendor'
        ), per AS (
            SELECT entity_id, yr, tbl, sum(amount) AS total, list(id) AS ids
            FROM money GROUP BY ALL
        ), best AS (
            -- awards and payments double count the same money; take the larger
            SELECT entity_id, yr, arg_max(tbl, total) AS tbl, max(total) AS total, arg_max(ids, total) AS ids
            FROM per GROUP BY ALL
        )
        SELECT b.* FROM best b
        WHERE b.total >= ? AND NOT EXISTS (
            SELECT 1 FROM be_disclosures d JOIN rec_entity re
              ON re.src_table='be_disclosures' AND re.src_id=d.id
            WHERE re.entity_id = b.entity_id AND d.filing_year = b.yr)
    """, [C.BE_ANNUAL_MIN]).fetchall()
    return [_flag(
        "missing_be_disclosure",
        [(f"received >= ${C.BE_ANNUAL_MIN:,} in {yr} per loaded {tbl}; no Form BE found for {yr}", 35)],
        None, eid, names,
        f"{names.get(eid)}: ${total:,.0f} in {yr} ({tbl}) with no matching BE disclosure",
        records=_cite(con, tbl, ids),
        caveat="Only as good as BE coverage loaded and entity matching; confirm on ELEC before relying.",
    ) for eid, yr, tbl, total, ids in rows]


# ─── 3. Aggregate spend over bid threshold with no competitive award ────────

def aggregate_over_threshold(con, names):
    rows = con.execute(f"""
        WITH pay AS (
            SELECT p.public_body, year(p.payment_date) AS yr, re.entity_id, sum(p.amount) AS total, list(p.id) AS ids
            FROM payments p JOIN rec_entity re ON re.src_table='payments' AND re.src_id=p.id AND re.role='vendor'
            GROUP BY ALL
        )
        SELECT pay.* FROM pay
        WHERE pay.total > ?
          AND pay.public_body IN (SELECT DISTINCT public_body FROM awards)   -- only where award coverage exists
          AND NOT EXISTS (
            SELECT 1 FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id
            WHERE re.entity_id = pay.entity_id AND a.public_body = pay.public_body
              AND a.award_type IN ({','.join(repr(t) for t in C.COMPETITIVE_TYPES + C.BID_EXEMPT_TYPES)}))
    """, [C.BID_THRESHOLD]).fetchall()
    return [_flag(
        "aggregate_over_bid_threshold",
        [(f"paid > ${C.BID_THRESHOLD:,} in {yr} with no bid/exempt award on file", 30)],
        body, eid, names,
        f"{names.get(eid)}: ${total:,.0f} paid by {body} in {yr}, no competitive or exempt award found",
        payments=_cite(con, "payments", ids),
        caveat="Calendar-year aggregation; N.J.S.A. 40A:11-2 aggregates by commodity over the contract year. "
               "State-contract/co-op purchases may be missing from the awards data.",
    ) for body, yr, eid, total, ids in rows]


# ─── 4. Awards clustered just under the bid threshold ───────────────────────

def split_awards(con, names):
    lo = C.BID_THRESHOLD * C.SPLIT_BAND_LOW
    rows = con.execute("""
        SELECT a.public_body, re.entity_id, a.id, a.award_date, a.amount
        FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
        WHERE a.amount >= ? AND a.amount < ? AND coalesce(a.award_type,'') <> 'change_order'
        ORDER BY 1, 2, 4
    """, [lo, C.BID_THRESHOLD]).fetchall()
    groups = defaultdict(list)
    for body, eid, aid, d, amt in rows:
        groups[(body, eid)].append((aid, d, amt))
    flags, window = [], timedelta(days=C.SPLIT_WINDOW_DAYS)
    for (body, eid), aws in groups.items():
        best = []
        for i in range(len(aws)):
            run = [a for a in aws[i:] if a[1] - aws[i][1] <= window]
            if len(run) > len(best):
                best = run
        if len(best) >= 2:
            total = sum(a[2] for a in best)
            parts = [(f"{len(best)} awards each ${lo:,.0f}-${C.BID_THRESHOLD:,} within {C.SPLIT_WINDOW_DAYS} days", 25)]
            if total > C.BID_THRESHOLD:
                parts.append(("combined value exceeds bid threshold", 15))
            flags.append(_flag("split_awards", parts, body, eid, names,
                               f"{names.get(eid)}: {len(best)} just-under-threshold awards from {body} "
                               f"totaling ${total:,.0f}",
                               awards=_cite(con, "awards", [a[0] for a in best])))
    return flags


# ─── 5. Change-order growth ──────────────────────────────────────────────────

def change_order_growth(con, names):
    rows = con.execute("""
        SELECT o.id, o.public_body, o.contract_ref, o.amount, re.entity_id,
               sum(co.amount) AS co_total, list(co.id) AS co_ids
        FROM awards o
        JOIN awards co ON co.award_type='change_order' AND co.parent_contract_ref = o.contract_ref
                      AND co.public_body = o.public_body
        LEFT JOIN rec_entity re ON re.src_table='awards' AND re.src_id=o.id AND re.role='vendor'
        WHERE coalesce(o.award_type,'') <> 'change_order' AND o.amount > 0
        GROUP BY ALL
    """).fetchall()
    flags = []
    for oid, body, ref, orig, eid, co_total, co_ids in rows:
        pct = co_total / orig
        if pct <= C.CHANGE_ORDER_PCT:
            continue
        parts = [(f"cumulative change orders {pct:.0%} of original (> {C.CHANGE_ORDER_PCT:.0%}, N.J.A.C. 5:30-11)", 25)]
        if pct > 0.5:
            parts.append(("change orders exceed 50% of original", 15))
        if orig < C.BID_THRESHOLD <= orig + co_total:
            parts.append(("original under bid threshold, total over it", 20))
        flags.append(_flag("change_order_growth", parts, body, eid, names,
                           f"{names.get(eid)}: contract {ref} grew ${orig:,.0f} -> ${orig + co_total:,.0f} ({pct:+.0%})",
                           original=_cite(con, "awards", [oid]), change_orders=_cite(con, "awards", co_ids)))
    return flags


# ─── 6. Repeat sole-source / emergency ───────────────────────────────────────

def repeat_noncompetitive(con, names):
    rows = con.execute(f"""
        SELECT a.public_body, re.entity_id, a.id, a.award_date, a.award_type, a.amount
        FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
        WHERE a.award_type IN ({','.join(repr(t) for t in C.NONCOMPETITIVE_TYPES)})
        ORDER BY 1, 2, 4
    """).fetchall()
    groups = defaultdict(list)
    for body, eid, aid, d, t, amt in rows:
        groups[(body, eid)].append((aid, d, t, amt))
    flags, window = [], timedelta(days=C.REPEAT_NONCOMPETITIVE_DAYS)
    for (body, eid), aws in groups.items():
        best = max(([a for a in aws[i:] if a[1] - aws[i][1] <= window] for i in range(len(aws))), key=len)
        if len(best) >= C.REPEAT_NONCOMPETITIVE_MIN:
            parts = [(f"{len(best)} sole-source/emergency awards within {C.REPEAT_NONCOMPETITIVE_DAYS} days", 20 + 5 * (len(best) - 2))]
            flags.append(_flag("repeat_noncompetitive", parts, body, eid, names,
                               f"{names.get(eid)}: {len(best)} non-competitive awards from {body}, "
                               f"${sum(a[3] or 0 for a in best):,.0f}",
                               awards=_cite(con, "awards", [a[0] for a in best])))
    return flags


# ─── 7. Vendor ↔ public employee overlap ─────────────────────────────────────

def employee_vendor_link(con, names):
    from rapidfuzz import fuzz
    vendors = con.execute("""
        SELECT DISTINCT re.entity_id, re.norm_addr, re.src_table, re.src_id, t.public_body, t.vendor_name
        FROM rec_entity re
        JOIN (SELECT 'awards' AS tbl, id, public_body, vendor_name FROM awards
              UNION ALL SELECT 'payments', id, public_body, vendor_name FROM payments) t
          ON t.tbl = re.src_table AND t.id = re.src_id
        WHERE re.role='vendor'
    """).fetchall()
    emps = con.execute("""
        SELECT e.id, e.public_body, e.name, e.title, re.norm_addr, re.norm_name, re.entity_id
        FROM employees e JOIN rec_entity re ON re.src_table='employees' AND re.src_id=e.id
    """).fetchall()
    emp_by_addr = defaultdict(list)
    for e in emps:
        if e[4] and not N.is_po_box(e[4]):
            emp_by_addr[e[4]].append(e)
    hits = {}
    for veid, vaddr, vtbl, vid, vbody, vname in vendors:
        matches = [(e, "same street address") for e in emp_by_addr.get(vaddr, [])] if vaddr else []
        if not N.looks_like_org(vname):
            pn = N.norm_person(vname)
            matches += [(e, "vendor name matches employee name") for e in emps
                        if pn and fuzz.token_sort_ratio(pn, e[5]) >= C.ER_NAME_ALONE]
        for e, why in matches:
            key = (veid, e[0], why)
            h = hits.setdefault(key, {"vbodies": set(), "vrecs": [], "emp": e, "why": why})
            h["vbodies"].add(vbody)
            h["vrecs"].append((vtbl, vid))
    flags = []
    for (veid, _, why), h in hits.items():
        e = h["emp"]
        same_body = e[1] in h["vbodies"]
        parts = [(f"{why}", 30)]
        if same_body:
            parts.append(("employee works for the paying/awarding body", 25))
        recs = []
        for tbl in ("awards", "payments"):
            recs += _cite(con, tbl, sorted({i for t, i in h["vrecs"] if t == tbl}))
        flags.append(_flag("employee_vendor_link", parts, e[1] if same_body else None, veid, names,
                           f"{names.get(veid)} ↔ employee {e[2]} ({e[3] or 'n/a'}, {e[1]}): {why}",
                           employee=_cite(con, "employees", [e[0]]), vendor_records=recs))
    return flags


# ─── 8. Address clustering / PO-box vendors ──────────────────────────────────

def shared_address(con, names):
    rows = con.execute("""
        SELECT norm_addr, zip5, list(DISTINCT entity_id) AS eids
        FROM rec_entity
        WHERE role='vendor' AND norm_addr <> '' AND NOT starts_with(norm_addr, 'PO BOX')
        GROUP BY ALL HAVING count(DISTINCT entity_id) >= ?
    """, [C.SHARED_ADDRESS_MIN_VENDORS]).fetchall()
    return [_flag("shared_vendor_address",
                  [(f"{len(eids)} distinct vendors at one address", 15 + 5 * (len(eids) - C.SHARED_ADDRESS_MIN_VENDORS))],
                  None, None, names,
                  f"{len(eids)} vendors at {addr} {z}: " + "; ".join(sorted(names.get(e) or '?' for e in eids)),
                  address=addr, zip5=z, entity_ids=eids,
                  caveat="Office buildings and registered-agent addresses produce benign hits.")
            for addr, z, eids in rows]


# ─── 9. Payroll ──────────────────────────────────────────────────────────────

def payroll_anomalies(con, names):
    flags = []
    for eid_row, body, name, title, yr, base, ot in con.execute("""
        SELECT e.id, e.public_body, e.name, e.title, e.pay_year, e.base_pay, e.overtime
        FROM employees e WHERE e.base_pay > 0 AND e.overtime > e.base_pay * ?
    """, [C.OVERTIME_RATIO]).fetchall():
        ratio = ot / base
        flags.append(_flag("overtime_outlier", [(f"overtime {ratio:.0%} of base pay", 15 + min(25, int((ratio - C.OVERTIME_RATIO) * 50)))],
                           body, None, names,
                           f"{name} ({title or 'n/a'}, {body}, {yr}): OT ${ot:,.0f} on base ${base:,.0f}",
                           employee=_cite(con, "employees", [eid_row])))
    for eid, yr, bodies, ids in con.execute("""
        SELECT re.entity_id, e.pay_year, list(DISTINCT e.public_body), list(e.id)
        FROM employees e JOIN rec_entity re ON re.src_table='employees' AND re.src_id=e.id
        GROUP BY ALL HAVING count(DISTINCT e.public_body) >= 2
    """).fetchall():
        flags.append(_flag("multiple_public_payrolls", [(f"on {len(bodies)} public payrolls in {yr}", 15)],
                           None, eid, names,
                           f"{names.get(eid)}: on payroll of {', '.join(sorted(bodies))} in {yr}",
                           employees=_cite(con, "employees", ids),
                           caveat="Often lawful (part-time roles, shared services). Check hours/pension enrollment."))
    return flags


RULES = [donation_near_award, missing_be_disclosure, aggregate_over_threshold, split_awards,
         change_order_growth, repeat_noncompetitive, employee_vendor_link, shared_address, payroll_anomalies]


def run_all(con, only=None):
    _setup(con)
    names = _names(con)
    con.execute("DELETE FROM flags")
    counts = {}
    for rule in RULES:
        if only and rule.__name__ not in only:
            continue
        fs = rule(con, names)
        counts[rule.__name__] = len(fs)
        bulk_insert(con, "flags", ["rule", "score", "public_body", "entity_id", "entity_name", "summary", "evidence"],
                    [(f["rule"], f["score"], f["public_body"], f["entity_id"], f["entity_name"], f["summary"],
                      json.dumps(f["evidence"], default=str)) for f in fs])
    return counts
