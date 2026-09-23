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
from moneytrail.bodies import Bodies
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
               rm.public_body AS mapped_body, rm.committee_type
        FROM aw JOIN ct ON ct.entity_id = aw.entity_id
         AND ct.d BETWEEN aw.award_date - INTERVAL {C.P2P_LOOKBACK_DAYS} DAY
                      AND aw.award_date + INTERVAL {C.P2P_LOOKAHEAD_DAYS} DAY
        LEFT JOIN recipient_map rm ON rm.recipient_norm = norm_org(ct.recipient)
        ORDER BY aw.id, ct.d
    """).fetchall()

    B = Bodies(con)
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
        btype = B.type(body)
        direct = [c for c in cts if c[5] != "employer"]
        not_bid = atype not in ("fair_and_open", "bid", "competitive_contracting")
        parts = [("vendor-linked contribution within window", 30)]
        if btype in C.P2P_BODY_TYPES:
            law = C.P2P_BODY_TYPES[btype]
            # Reportable contribution to a candidate committee of this body's
            # officials, in the year before award or during the term.
            hits = [c for c in direct if c[7] == body and c[8] == "candidate"
                    and (c[3] or 0) > C.p2p_reportable_min(c[4])]
            if (amt or 0) > C.P2P_CONTRACT_MIN and not_bid and hits:
                parts.append((f"award > ${C.P2P_CONTRACT_MIN:,}, not fair-and-open, with reportable contribution to a "
                              f"candidate committee of this body within 1 yr before / during term ({law})", 30))
            elif (amt or 0) > C.P2P_CONTRACT_MIN and hits:
                parts.append((f"candidate-committee contribution, but award recorded as {atype} "
                              f"(fair-and-open process; {law} bar not triggered)", 0))
            party = [c for c in direct if c[7] == body and c[8] == "party"]
            if party and all(c[4] >= C.ETA_DATE for c in party) and not hits:
                parts.append(("party-committee contribution only; no longer disqualifying after P.L.2023 c.30", -10))
        else:
            if (amt or 0) > C.P2P_CONTRACT_MIN and not_bid:
                parts.append((f"{btype} contract > ${C.P2P_CONTRACT_MIN:,} not publicly bid: vendor's contribution "
                              f"disclosure due >= 10 days before award ({C.DISCLOSURE_2026}); check it was filed "
                              f"and lists these", 15))
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
    """Fiscal-year spend per body+vendor over the bid threshold with no bid or
    exempt award on file. Schools aggregate July-June."""
    B = Bodies(con)
    covered = {r[0] for r in con.execute("SELECT DISTINCT public_body FROM awards").fetchall()}
    procured = {(r[0], r[1]) for r in con.execute(f"""
        SELECT a.public_body, re.entity_id FROM awards a
        JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
        WHERE a.award_type IN ({','.join(repr(t) for t in C.COMPETITIVE_TYPES + C.BID_EXEMPT_TYPES)})
    """).fetchall()}
    agg = defaultdict(lambda: [0.0, [], None])
    for body, eid, pid, d, amt in con.execute("""
        SELECT p.public_body, re.entity_id, p.id, p.payment_date, p.amount
        FROM payments p JOIN rec_entity re ON re.src_table='payments' AND re.src_id=p.id AND re.role='vendor'
    """).fetchall():
        a = agg[(body, eid, B.fiscal_year(body, d))]
        a[0] += amt or 0
        a[1].append(pid)
        a[2] = max(a[2] or d, d)
    flags = []
    for (body, eid, fy), (total, ids, last) in agg.items():
        # Only where award coverage exists for the body; otherwise absence means nothing.
        thr = B.bid_threshold(body, last)
        if total <= thr or body not in covered or (body, eid) in procured:
            continue
        fyl = B.fy_label(body, fy)
        flags.append(_flag(
            "aggregate_over_bid_threshold",
            [(f"paid ${total:,.0f} in {fyl}, over bid threshold {B.threshold_note(body, last)}, "
              f"with no bid/exempt award on file", 30)],
            body, eid, names,
            f"{names.get(eid)}: ${total:,.0f} paid by {body} in {fyl}, no competitive or exempt award found",
            payments=_cite(con, "payments", ids), body_type=B.type(body),
            caveat="N.J.S.A. 40A:11-2(19) / 18A:18A-2 aggregate payments for the same immediate purpose or similar "
                   "goods/services over the contract year (12 months from award); this sums all payments to the "
                   "vendor by fiscal year. State-contract/co-op purchases may be missing from the awards data.",
        ))
    return flags


# ─── 4. Awards clustered just under the bid threshold ───────────────────────

def split_awards(con, names):
    """Just-under-threshold awards to one vendor, grouped by body_group so a
    split across related bodies (shared services, a consolidated district's
    predecessors) shows up too."""
    B = Bodies(con)
    rows = []
    for body, eid, aid, d, amt in con.execute("""
        SELECT a.public_body, re.entity_id, a.id, a.award_date, a.amount
        FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
        WHERE coalesce(a.award_type,'') <> 'change_order' AND a.amount > 0
        ORDER BY 4
    """).fetchall():
        thr = B.bid_threshold(body, d)
        if thr * C.SPLIT_BAND_LOW <= amt < thr:
            rows.append((body, eid, aid, d, amt))
    groups = defaultdict(list)
    for body, eid, aid, d, amt in rows:
        groups[(B.group(body), eid)].append((aid, d, amt, body))
    flags, window = [], timedelta(days=C.SPLIT_WINDOW_DAYS)
    for (grp, eid), aws in groups.items():
        best = []
        for i in range(len(aws)):
            run = [a for a in aws[i:] if a[1] - aws[i][1] <= window]
            if len(run) > len(best):
                best = run
        if len(best) >= 2:
            total = sum(a[2] for a in best)
            bodies = sorted({a[3] for a in best})
            thr = B.bid_threshold(bodies[0], best[-1][1])
            parts = [(f"{len(best)} awards each {C.SPLIT_BAND_LOW:.0%}-100% of the bid threshold within "
                      f"{C.SPLIT_WINDOW_DAYS} days", 25)]
            if total > thr:
                parts.append((f"combined value exceeds bid threshold {B.threshold_note(bodies[0], best[-1][1])}", 15))
            if len(bodies) > 1:
                parts.append((f"split across related bodies in group '{grp}'", 10))
            flags.append(_flag("split_awards", parts, bodies[0] if len(bodies) == 1 else grp, eid, names,
                               f"{names.get(eid)}: {len(best)} just-under-threshold awards from "
                               f"{', '.join(bodies)} totaling ${total:,.0f}",
                               awards=_cite(con, "awards", [a[0] for a in best])))
    return flags


# ─── 5. Change-order growth ──────────────────────────────────────────────────

def change_order_growth(con, names):
    B = Bodies(con)
    rows = con.execute("""
        SELECT o.id, o.public_body, o.contract_ref, o.amount, o.award_date, re.entity_id,
               sum(co.amount) AS co_total, list(co.id) AS co_ids
        FROM awards o
        JOIN awards co ON co.award_type='change_order' AND co.parent_contract_ref = o.contract_ref
                      AND co.public_body = o.public_body
        LEFT JOIN rec_entity re ON re.src_table='awards' AND re.src_id=o.id AND re.role='vendor'
        WHERE coalesce(o.award_type,'') <> 'change_order' AND o.amount > 0
        GROUP BY ALL
    """).fetchall()
    flags = []
    for oid, body, ref, orig, odate, eid, co_total, co_ids in rows:
        pct = co_total / orig
        if pct <= C.CHANGE_ORDER_PCT:
            continue
        parts = [(f"cumulative change orders {pct:.0%} of original (> {C.CHANGE_ORDER_PCT:.0%}, {B.change_order_rule(body)})", 25)]
        if pct > 0.5:
            parts.append(("change orders exceed 50% of original", 15))
        if orig < B.bid_threshold(body, odate) <= orig + co_total:
            parts.append(("original under bid threshold, total over it", 20))
        flags.append(_flag("change_order_growth", parts, body, eid, names,
                           f"{names.get(eid)}: contract {ref} grew ${orig:,.0f} -> ${orig + co_total:,.0f} ({pct:+.0%})",
                           original=_cite(con, "awards", [oid]), change_orders=_cite(con, "awards", co_ids)))
    return flags


# ─── 6. Repeat sole-source / emergency ───────────────────────────────────────

def repeat_noncompetitive(con, names):
    B = Bodies(con)
    rows = con.execute(f"""
        SELECT a.public_body, re.entity_id, a.id, a.award_date, a.award_type, a.amount
        FROM awards a JOIN rec_entity re ON re.src_table='awards' AND re.src_id=a.id AND re.role='vendor'
        WHERE a.award_type IN ({','.join(repr(t) for t in C.NONCOMPETITIVE_TYPES)})
        ORDER BY 4
    """).fetchall()
    groups = defaultdict(list)
    for body, eid, aid, d, t, amt in rows:
        groups[(B.group(body), eid)].append((aid, d, t, amt, body))
    flags, window = [], timedelta(days=C.REPEAT_NONCOMPETITIVE_DAYS)
    for (grp, eid), aws in groups.items():
        best = max(([a for a in aws[i:] if a[1] - aws[i][1] <= window] for i in range(len(aws))), key=len)
        if len(best) >= C.REPEAT_NONCOMPETITIVE_MIN:
            bodies = sorted({a[4] for a in best})
            parts = [(f"{len(best)} sole-source/emergency awards within {C.REPEAT_NONCOMPETITIVE_DAYS} days", 20 + 5 * (len(best) - 2))]
            if len(bodies) > 1:
                parts.append((f"across related bodies in group '{grp}'", 5))
            flags.append(_flag("repeat_noncompetitive", parts, bodies[0] if len(bodies) == 1 else grp, eid, names,
                               f"{names.get(eid)}: {len(best)} non-competitive awards from {', '.join(bodies)}, "
                               f"${sum(a[3] or 0 for a in best):,.0f}",
                               awards=_cite(con, "awards", [a[0] for a in best])))
    return flags


# ─── 7. Vendor ↔ public employee overlap ─────────────────────────────────────

def _vendor_records(con):
    return con.execute("""
        SELECT DISTINCT re.entity_id, re.norm_addr, re.src_table, re.src_id, t.public_body, t.vendor_name
        FROM rec_entity re
        JOIN (SELECT 'awards' AS tbl, id, public_body, vendor_name FROM awards
              UNION ALL SELECT 'payments', id, public_body, vendor_name FROM payments) t
          ON t.tbl = re.src_table AND t.id = re.src_id
        WHERE re.role='vendor'
    """).fetchall()


def _person_vendor_links(con, names, rule, people, who, body_part):
    """people: rows (id, table, public_body, name, title, norm_addr, norm_name).
    Flags vendors sharing a street address with, or (for sole-prop vendors)
    the name of, a person on a public body."""
    from rapidfuzz import fuzz
    by_addr = defaultdict(list)
    for p in people:
        if p[5] and not N.is_po_box(p[5]):
            by_addr[p[5]].append(p)
    hits = {}
    for veid, vaddr, vtbl, vid, vbody, vname in _vendor_records(con):
        matches = [(p, "same street address") for p in by_addr.get(vaddr, [])] if vaddr else []
        if not N.looks_like_org(vname):
            pn = N.norm_person(vname)
            matches += [(p, f"vendor name matches {who} name") for p in people
                        if pn and fuzz.token_sort_ratio(pn, p[6]) >= C.ER_NAME_ALONE]
        for p, why in matches:
            h = hits.setdefault((veid, p[1], p[0], why), {"vbodies": set(), "vrecs": [], "p": p, "why": why})
            h["vbodies"].add(vbody)
            h["vrecs"].append((vtbl, vid))
    flags = []
    for (veid, _, _, why), h in hits.items():
        p = h["p"]
        same_body = p[2] in h["vbodies"]
        parts = [(why, 30)]
        if same_body:
            parts.append((body_part, 25))
        recs = []
        for tbl in ("awards", "payments"):
            recs += _cite(con, tbl, sorted({i for t, i in h["vrecs"] if t == tbl}))
        flags.append(_flag(rule, parts, p[2] if same_body else None, veid, names,
                           f"{names.get(veid)} ↔ {who} {p[3]} ({p[4] or 'n/a'}, {p[2]}): {why}",
                           person=_cite(con, p[1], [p[0]]), vendor_records=recs))
    return flags


def employee_vendor_link(con, names):
    people = con.execute("""
        SELECT e.id, 'employees', e.public_body, e.name, e.title, re.norm_addr, re.norm_name
        FROM employees e JOIN rec_entity re ON re.src_table='employees' AND re.src_id=e.id
    """).fetchall()
    return _person_vendor_links(con, names, "employee_vendor_link", people, "employee",
                                "employee works for the paying/awarding body")


def official_vendor_link(con, names):
    """Board members / officials. Two paths:
    1. a business the official disclosed (self or relative) is a vendor;
    2. the official's home address or name matches a vendor."""
    B = Bodies(con)
    flags = []
    rows = con.execute("""
        SELECT d.id, d.public_body, d.official_name, d.role, d.relationship, d.filing_year, rb.entity_id
        FROM disclosures d
        JOIN rec_entity rb ON rb.src_table='disclosures' AND rb.src_id=d.id AND rb.role='disclosed_business'
    """).fetchall()
    vend = defaultdict(list)
    for veid, _, tbl, vid, vbody, _ in _vendor_records(con):
        vend[veid].append((tbl, vid, vbody))
    for did, body, oname, role, rel, fy, beid in rows:
        vrecs = vend.get(beid)
        if not vrecs:
            continue
        same_body = any(v[2] == body for v in vrecs)
        parts = [(f"business disclosed by official ({rel or 'relationship n/a'}) is a public vendor", 35)]
        if same_body:
            parts.append((f"paid/awarded by the body the official serves ({C.ETHICS_LAW.get(B.type(body), C.ETHICS_LAW['default'])})", 30))
        recs = []
        for tbl in ("awards", "payments"):
            recs += _cite(con, tbl, sorted({v[1] for v in vrecs if v[0] == tbl and (v[2] == body or not same_body)}))
        flags.append(_flag("official_disclosed_business_vendor", parts, body if same_body else None, beid, names,
                           f"{names.get(beid)}: disclosed by {oname} ({role or 'official'}, {body}, {fy or 'n/a'}; "
                           f"{rel or 'relationship n/a'}); vendor to "
                           f"{', '.join(sorted({v[2] for v in vrecs}))}",
                           disclosure=_cite(con, "disclosures", [did]), vendor_records=recs,
                           caveat="Disclosure means it was reported; check abstention on the votes and whether "
                                  "the interest is covered by an exception."))
    people = con.execute("""
        SELECT DISTINCT ON (d.official_name, d.public_body)
               d.id, 'disclosures', d.public_body, d.official_name, d.role, re.norm_addr, re.norm_name
        FROM disclosures d JOIN rec_entity re ON re.src_table='disclosures' AND re.src_id=d.id AND re.role='official'
        ORDER BY d.official_name, d.public_body, d.filing_year DESC NULLS LAST
    """).fetchall()
    flags += _person_vendor_links(con, names, "official_vendor_link", people, "official",
                                  "official serves the paying/awarding body")
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
         change_order_growth, repeat_noncompetitive, employee_vendor_link, official_vendor_link,
         shared_address, payroll_anomalies]


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
