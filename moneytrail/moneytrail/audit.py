"""Audit findings: extraction from audit report / minutes text, and the
category vocabulary shared by the loader and the rules.

Extraction is candidate-generating, not authoritative: every row keeps the
source sentence and page so it can be checked before it's relied on.
"""
import re

CATEGORIES = [
    ("financial_reporting", r"material\s+weakness|financial\s+reporting|misstatement"),
    ("procurement", r"\bbid|quot(e|ation)|purchas|procure|public contracts law|18A:18A|40A:11|pay[- ]to[- ]play|"
                    r"change order|competitive|sole source|emergency|\bQPA\b|contract"),
    ("payroll", r"payroll|overtime|time ?sheet|timecard|compensation|salar|stipend|longevity|sick|vacation|"
                r"pension|TPAF|PERS|employee"),
    ("cash", r"\bcash|deposit|bank|reconcil|petty|receipt|disburse|check|wire"),
    ("grants", r"grant|federal|single audit|uniform guidance|Title I|IDEA|ESSER|allowable"),
    ("budget", r"appropriation|over-?expend|dedication\s+by\s+rider|interfund|budget|transfer"),
    ("capital", r"capital|bond|debt|lease|construction|fixed asset|inventory"),
    ("governance", r"board|minutes|policy|approv|resolution|ethics|disclosure"),
]
PROCUREMENT_RULES = {"split_awards", "aggregate_over_bid_threshold", "repeat_noncompetitive",
                     "change_order_growth", "donation_near_award", "official_disclosed_business_vendor",
                     "official_vendor_link"}
PAYROLL_RULES = {"overtime_outlier", "multiple_public_payrolls", "employee_vendor_link"}


def categorize(text):
    for cat, pat in CATEGORIES:
        if re.search(pat, text or "", re.I):
            return cat
    return "other"


# "... ACCEPT the ANNUAL COMPREHENSIVE FINANCIAL REPORT AND THE AUDITORS MANAGEMENT REPORT for the
#  School District of Highlands for the fiscal year ending June 30, 2024, from Alvino & Shechter, L.L.C.
#  Certified Public Accountants with no audit recommendations."
_ACCEPT = re.compile(
    r"accept\w*\s+the\s+(?P<what>[^.]{0,160}?(?:MANAGEMENT\s+REPORT|AUDIT\w*|ACFR|CAFR)[^.]{0,40}?)\s+"
    r"for\s+the\s+(?P<body>[^,]{3,90}?)\s+for\s+the\s+fiscal\s+year\s+end(?:ing|ed)\s+"
    r"(?:June\s+30|December\s+31),?\s+(?P<fy>\d{4}),?", re.I)
# The clause after the fiscal year runs to the next agenda item ("N. To ...").
_NEXT_ITEM = re.compile(r"\s[A-Z]{1,2}\.\s+To\s|\s\d{1,2}\.\s+(?:To|That)\s")
_AUDITOR = re.compile(r"^\s*(?:from|by|prepared\s+by)\s+(?P<a>.+?)(?:,?\s+(?:Certified\s+Public\s+Accountants|CPAs?\b|"
                      r"Registered\s+Municipal\s+Accountants)|,?\s+with\s|$)", re.I)
_NONE = re.compile(r"\bno\s+(?:audit\s+)?(?:recommendations?|findings?|comments?)\b", re.I)
_NUM = re.compile(r"(?:(?<=\n)|^)\s*(?:Finding\s+)?(?P<no>(?:\d{2,4}-)?\d{1,3})[.)]\s+(?P<body>That\b.*?|[A-Z].*?)"
                  r"(?=(?:\n\s*(?:Finding\s+)?(?:\d{2,4}-)?\d{1,3}[.)]\s)|\n\s*\n|\Z)", re.S)
_REC_SECTION = re.compile(r"^\s*(RECOMMENDATIONS?|FINDINGS\s+AND\s+RECOMMENDATIONS|SCHEDULE\s+OF\s+FINDINGS)\s*$",
                          re.I | re.M)
_SIMILAR = re.compile(r"numbers?\s+(?P<ids>[\d\-,\s]+(?:and\s+[\d\-]+)?)\s+(?:is|are)\s+similar", re.I)
_REPEAT = re.compile(r"\brepeat\b|prior\s+year|previously\s+reported|not\s+(?:been\s+)?(?:resolved|corrected)", re.I)


def acceptances(text):
    """Audit acceptance statements in minutes/agendas. -> dicts with body,
    fiscal_year, auditor, category ('none' when 'no audit recommendations',
    None when findings or unstated)."""
    flat = " ".join((text or "").split())
    out = []
    for m in _ACCEPT.finditer(flat):
        tail = flat[m.end():m.end() + 400]
        n = _NEXT_ITEM.search(tail)
        clause = tail[:n.start()] if n else tail
        a = _AUDITOR.search(clause)
        out.append({
            "public_body": " ".join(m.group("body").split()),
            "fiscal_year": int(m.group("fy")),
            "auditor": a.group("a").strip(" ,") if a else None,
            "report_type": "AMR" if re.search(r"management\s+report", m.group("what"), re.I) else "audit",
            "category": "none" if _NONE.search(clause) else None,
            "finding": (m.group(0) + clause)[:600],
        })
    return out


# NJ municipal / school audit style: "2024-003*" (asterisk = prior-year
# recommendation not corrected), Comment/Condition ... Recommendation ...
_ID = re.compile(r"(?:(?<=\n)|^)\s*(?:Finding\s+(?:No\.\s*)?)?(?P<no>(?:19|20)\d{2}-\d{2,3})\s*(?P<rep>\*)?\s*\n")
_END = re.compile(r"Status\s+of\s+Prior\s+Year|The\s+aforementioned\s+comments|Summary\s+Schedule\s+of\s+Prior", re.I)
_RECO = re.compile(r"\n\s*Recommendations?\s*\n(?P<r>.*)", re.I | re.S)


def findings_by_id(pages):
    """pages: [(page_no, text)]. -> finding dicts with page, finding_no,
    finding, recommendation, category, is_repeat (asterisk)."""
    text, offsets = "", []
    for pg, t in pages:
        offsets.append((len(text), pg))
        text += t + "\n"
    end = _END.search(text)
    stop = len(text)
    hits = list(_ID.finditer(text))
    out = []
    for i, m in enumerate(hits):
        nxt = hits[i + 1].start() if i + 1 < len(hits) else stop
        e = _END.search(text, m.end(), nxt)
        body = text[m.end():e.start() if e else nxt]
        body = re.sub(r"BOROUGH OF .*?\n|COUNTY OF .*?\n|STATE OF NEW\s*JERSEY\s*\n|COMMENTS AND RECOMMENDATIONS\s*\n|"
                      r"YEAR ENDED .*?\n|\(Continued\)\s*\n|^\s*\d{1,3}\s*$", "", body, flags=re.M)
        if len(body.strip()) < 30:
            continue
        rec = _RECO.search(body)
        cond = body[:rec.start()] if rec else body
        page = max(pg for off, pg in offsets if off <= m.start())
        out.append({
            "page": page, "finding_no": m.group("no"),
            "finding": " ".join(cond.split())[:2000],
            "recommendation": " ".join(rec.group("r").split())[:1000] if rec else None,
            "category": categorize(" ".join(cond.split()) + " " + (rec.group("r") if rec else "")),
            "is_repeat": bool(m.group("rep")) or bool(_REPEAT.search(body)),
        })
    return out


def findings(text):
    """Numbered recommendations under the last RECOMMENDATIONS heading
    ("It is recommended: 12-01. That ..."). Repeats come from the auditor's
    "number 12-01 is similar to that reported in the 2011 audit" line or
    repeat wording. -> dicts with finding_no, finding, category, is_repeat."""
    heads = list(_REC_SECTION.finditer(text or ""))
    if not heads:
        return []
    section = text[heads[-1].end():]
    repeats = set()
    for m in _SIMILAR.finditer(section):
        repeats |= set(re.findall(r"\d{2,4}-\d{1,3}|\d{1,3}", m.group("ids")))
    out = []
    for n in _NUM.finditer(section):
        body = " ".join(n.group("body").split())
        if len(body) < 25:
            continue
        out.append({"finding_no": n.group("no"), "finding": body[:2000], "category": categorize(body),
                    "is_repeat": n.group("no") in repeats or bool(_REPEAT.search(body))})
    return out


def ingest(con, log=print):
    """Load findings from fetched audit reports and audit acceptances from
    fetched minutes/agendas into audit_findings. Idempotent per document."""
    from moneytrail.schema import bulk_insert
    import json
    loaded = {}
    docs = con.execute("""
        SELECT d.sha256, d.local_path, d.public_body, d.title, d.doc_class FROM documents d
        WHERE d.text_extracted AND (d.doc_class = 'audit' OR d.doc_class IN ('minutes', 'agenda'))
          AND d.sha256 NOT IN (SELECT sha256 FROM source_files)
    """).fetchall()
    seen = {(b, fy, no) for b, fy, no in con.execute(
        "SELECT public_body, fiscal_year, finding_no FROM audit_findings WHERE finding_no IS NOT NULL").fetchall()}
    for sha, path, body, title, cls in docs:
        pages = con.execute("SELECT page, text FROM doc_text WHERE sha256 = ? ORDER BY page", [sha]).fetchall()
        rows = []
        if cls == "audit" and not re.search(r"summary|synopsis|RFP|spec", title or "", re.I):
            full = "\n".join(t for _, t in pages)
            ye = re.findall(r"YEAR\s+ENDED\s+(?:DECEMBER\s+31|JUNE\s+30)[,.\s]*(\d{4})", full, re.I)
            doc_fy = int(max(set(ye), key=ye.count)) if ye else None
            fs = findings_by_id(pages)
            if not fs:
                tail_pages = pages[-15:]
                fs = [{**f, "page": tail_pages[-1][0]} for f in findings("\n".join(t for _, t in tail_pages))]
            for f in fs:
                no = f["finding_no"]
                fy = int(no[:4]) if re.match(r"\d{4}-", no) else 2000 + int(no[:2]) if re.match(r"\d{2}-", no) else doc_fy
                if fy is None:
                    continue
                if (body, fy, no) in seen:
                    continue
                seen.add((body, fy, no))
                rows.append([f["page"], json.dumps({"title": title, **f}), body, fy, None, "audit report",
                             no, f["category"], f["is_repeat"], f["finding"], f.get("recommendation")])
        elif cls in ("minutes", "agenda"):
            # Minutes record what the board actually accepted; agendas only propose.
            if cls == "agenda" and "minutes" not in (title or "").lower():
                continue
            for pg, t in pages:
                for a in acceptances(t):
                    rows.append([pg, json.dumps({"title": title, **a}), a["public_body"], a["fiscal_year"],
                                 a["auditor"], a["report_type"], None, a["category"] or "unstated", False,
                                 a["finding"], None])
        if not rows:
            continue
        fid = con.execute("INSERT INTO source_files (source_type, path, sha256, row_count, note) VALUES "
                          "('audit_findings', ?, ?, ?, ?) RETURNING file_id",
                          [path, sha, len(rows), f"extracted from {title}"]).fetchone()[0]
        bulk_insert(con, "audit_findings", ["file_id", "source_row", "raw", "public_body", "fiscal_year", "auditor",
                                            "report_type", "finding_no", "category", "is_repeat", "finding",
                                            "recommendation"], [[fid] + r for r in rows])
        loaded[title] = len(rows)
    return loaded
