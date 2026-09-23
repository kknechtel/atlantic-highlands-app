"""School Ethics Commission disclosure statements (N.J.S.A. 18A:12-25, -26).

NJ DOE publishes every filed Personal/Relative + Financial Disclosure
Statement through the public search at homeroom6.doe.nj.gov/secpublic,
backed by an open JSON API. The API sits behind Incapsula and only answers
requests that carry the search page's Origin/Referer.

Statements come in two shapes:
- fillable PDFs: values are AcroForm widgets;
- "Adobe Fill & Sign" PDFs: values are drawn as vector outlines inside form
  XObjects, so there is no text to extract; each overlay box is OCR'd.
Both are reduced to (page, bbox, value) and assigned to fields by position
against the template's text layer, which is identical across filings.
"""
import os
import re

import requests

from moneytrail import fetch

API = "https://homeroom4.doe.nj.gov/schoolethics"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://homeroom6.doe.nj.gov",
    "Referer": "https://homeroom6.doe.nj.gov/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}
MONMOUTH = 25


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def districts(s, county=MONMOUTH):
    r = s.get(f"{API}/county/{county}/districts", timeout=30)
    r.raise_for_status()
    return r.json()


def filings(s, district_code):
    r = s.get(f"{API}/filings", params={"districtCode": district_code}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_district(con, root, district_code, body, years=None, log=print):
    """Download every statement for a district into the custody log.
    Returns [(filing, sha256)]."""
    fetch.init(con)
    s = session()
    out = []
    listing = f"{API}/filings?districtCode={district_code}"
    for f in filings(s, district_code):
        if years and f["year"] not in years:
            continue
        url = f"{API}/filing/{f['id']}/disclosure"
        title = f"School ethics disclosure {f['year']}: {f['firstName']} {f['lastName']}, {f['position']}"
        hit = con.execute("SELECT sha256 FROM retrievals WHERE url = ? AND sha256 IS NOT NULL "
                          "ORDER BY retrieved_at DESC LIMIT 1", [url]).fetchone()
        if not hit:
            import time
            time.sleep(fetch.DELAY)
            res = fetch._download(con, s, root, "sec_disclosures", body, url, title, listing)
            if res == "errors":
                log(f"  failed {title}")
                continue
            hit = con.execute("SELECT sha256 FROM retrievals WHERE url = ? AND sha256 IS NOT NULL "
                              "ORDER BY retrieved_at DESC LIMIT 1", [url]).fetchone()
        con.execute("UPDATE documents SET doc_class = 'disclosure' WHERE sha256 = ?", [hit[0]])
        out.append((f, hit[0]))
    return out


# ─── Parsing ─────────────────────────────────────────────────────────────────

# Page index -> (item, [(column, header text)]). Template is the same every year.
TABLES = {
    1: ("relative_employed", [("related_person", "FULL NAME OF THE"), ("relationship", "RELATIONSHIP"),
                              ("district", "NAME OF THE LOCAL"), ("detail", "POSITION HELD BY")]),
    2: ("relative_contract", [("related_person", "FULL NAME OF THE"), ("relationship", "RELATIONSHIP"),
                              ("district", "NAME OF THE LOCAL"), ("detail", "THE NATURE OF")]),
    3: ("contract_business", [("business_name", "FULL NAME OF BUSINESS"), ("district", "NAME OF THE LOCAL"),
                              ("detail", "THE NATURE OF THE")]),
    4: ("income_source", [("business_name", "NAME OF SOURCE"), ("address", "ADDRESS FOR"),
                          ("related_person", "RECIPIENT OF"), ("relationship", "RELATIONSHIP")]),
    5: ("income_source", [("business_name", "NAME OF SOURCE"), ("address", "ADDRESS FOR"),
                          ("related_person", "RECIPIENT OF"), ("relationship", "RELATIONSHIP")]),
    6: ("fee", [("business_name", "NAME OF SOURCE"), ("address", "ADDRESS FOR"),
                ("related_person", "RECIPIENT OF"), ("relationship", "RELATIONSHIP")]),
    7: ("gift", [("business_name", "NAME OF SOURCE"), ("address", "ADDRESS FOR"),
                 ("related_person", "RECIPIENT OF"), ("relationship", "RELATIONSHIP")]),
    8: ("business_interest", [("business_name", "NAME OF BUSINESS"), ("address", "ADDRESS FOR BUSINESS")]),
}
# Page index -> question whose YES/NO checkbox sits on that page.
QUESTIONS = {1: "relative_employed", 2: "relative_contract", 3: "contract_business", 4: "income_source",
             6: "fee", 7: "gift", 8: "business_interest"}
_NOISE = re.compile(r"^[\W_]+$|^[eo]$")


def _items_widgets(page):
    items, checks = [], []
    for w in page.widgets():
        v = w.field_value
        if w.field_type_string == "CheckBox":
            if v not in (None, "", "Off", False):
                checks.append(w.rect)
        elif v not in (None, ""):
            items.append((w.rect, str(v).replace("\r", "\n").strip()))
    return items, checks


def _is_template(rect, word, tmpl):
    c = (rect.tl + rect.br) / 2
    return any(c in tr and (word is None or tw == word) for tr, tw in tmpl)


def _phrases(words):
    """Join words into phrases: same line, gap < 12pt."""
    words = sorted(words, key=lambda w: (round(w[0].y0 / 4), w[0].x0))
    out = []
    for r, t in words:
        if out:
            pr, pt = out[-1]
            if abs(pr.y0 - r.y0) < 4 and 0 <= r.x0 - pr.x1 < 12:
                out[-1] = (pr | r, f"{pt} {t}")
                continue
        out.append((r, t))
    return out


def _template(page, ref_page):
    """Blank-form words for this page. A fillable filing's text layer also
    carries its widget values, so words inside widget rects are removed."""
    import pymupdf
    src = ref_page if ref_page is not None else page
    wr = [w.rect + (-1, -1, 1, 1) for w in src.widgets()]
    out = []
    for w in src.get_text("words"):
        r = pymupdf.Rect(w[:4])
        c = (r.tl + r.br) / 2
        if not any(c in x for x in wr):
            out.append((r + (-2, -2, 2, 2), w[4]))
    return out


def _items_text(page, ref_page):
    """Flattened-to-text filings: the values are ordinary text. Keep words that
    the blank template (a fillable filing's text layer) doesn't have."""
    import pymupdf
    tmpl = _template(page, ref_page)
    words = [(pymupdf.Rect(w[:4]), w[4]) for w in page.get_text("words")]
    return [(r, t) for r, t in words if not _is_template(r, t, tmpl)], []


def _items_ocr(page, ref_page=None, dpi=300):
    """Fill & Sign filings: values are vector outlines. OCR the page and drop
    words that sit on template text."""
    import io

    import pymupdf
    import pytesseract
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    data = pytesseract.image_to_data(Image.open(io.BytesIO(pix.tobytes("png"))),
                                     output_type=pytesseract.Output.DICT)
    k = 72 / dpi
    tmpl = _template(page, ref_page)
    words = []
    for i, t in enumerate(data["text"]):
        t = t.strip()
        if not t or float(data["conf"][i]) < 30 or _NOISE.match(t):
            continue
        r = pymupdf.Rect(data["left"][i] * k, data["top"][i] * k,
                         (data["left"][i] + data["width"][i]) * k, (data["top"][i] + data["height"][i]) * k)
        if _is_template(r, None, tmpl):
            continue
        words.append((r, t))
    return words, []


def _header_x(page, headers):
    """x-centre of each column header; pick matches on a common row."""
    found = {}
    first = page.search_for(headers[0][1])
    if not first:
        return None
    y = first[-1].y0
    for col, text in headers:
        hits = page.search_for(text)
        if not hits:
            return None
        r = min(hits, key=lambda h: abs(h.y0 - y))
        found[col] = r
    return found


def _table_rows(page, items, headers):
    hx = _header_x(page, headers)
    if not hx:
        return []
    top = max(r.y1 for r in hx.values())
    cols = sorted(hx.items(), key=lambda kv: kv[1].x0)
    # Column edges come from the table's vertical rules (cells are left-aligned,
    # headers centred, so header positions alone misplace wrapped lines).
    vx = set()
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].x - it[2].x) < 1 and abs(it[1].y - it[2].y) > 15 \
                    and max(it[1].y, it[2].y) > top:
                vx.add(round(it[1].x))
            elif it[0] == "re" and it[1].width < 2 and it[1].height > 15 and it[1].y1 > top:
                vx.add(round(it[1].x0))
    edges = sorted(vx)
    if len(edges) >= len(cols) + 1:
        # map each interval to the header whose centre falls inside it
        col_by_interval = []
        for a, b in zip(edges, edges[1:]):
            inside = [c for c, r in cols if a <= (r.x0 + r.x1) / 2 < b]
            col_by_interval.append((a, b, inside[0] if inside else None))

        def col_of(rect):
            x = rect.x0 + 2
            for a, b, c in col_by_interval:
                if a <= x < b:
                    return c
            return None
    else:
        starts = [r.x0 - 6 for _, r in cols]

        def col_of(rect):
            x = (rect.x0 + rect.x1) / 2
            return cols[max([i for i, st in enumerate(starts) if x >= st] or [0])][0]

    cells = [(r, c, t) for r, t in items if r.y0 > top for c in [col_of(r)] if c]
    hy = set()
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 1 and abs(it[1].x - it[2].x) > 50:
                hy.add(round(it[1].y))
            elif it[0] == "re" and it[1].height < 2 and it[1].width > 50:
                hy.add(round(it[1].y0))
    bounds = sorted(y for y in hy if y >= top - 4)
    if len(bounds) >= 2:
        def row_of(r):
            return sum(1 for b in bounds if b <= r.y0 + 1)
    else:  # no ruling: a new first-column line starts a row
        first_col = cols[0][0]
        anchors = sorted({round(r.y0) for r, c, _ in cells if c == first_col})

        def row_of(r):
            return max([i for i, a in enumerate(anchors) if a <= r.y0 + 3] or [-1])
    grid = {}
    for r, c, t in cells:
        grid.setdefault(row_of(r), {}).setdefault(c, []).append((r, t))
    out = []
    for ri in sorted(k for k in grid if k >= 0):
        row = {}
        for c, ws in grid[ri].items():
            lines = []
            for r, t in sorted(ws, key=lambda w: (round(w[0].y0 / 4), w[0].x0)):
                if lines and abs(lines[-1][0] - r.y0) < 4:
                    lines[-1][1].append(t)
                else:
                    lines.append([r.y0, [t]])
            row[c] = "\n".join(" ".join(ts) for _, ts in lines)
        out.append(row)
    return out


def _labelled(page, items, labels):
    """Values to the right of labels on the same line. Repeated labels are
    numbered in reading order (First Name#1 = official, #2 = spouse)."""
    lab = []
    for key in labels:
        for i, r in enumerate(sorted(page.search_for(key), key=lambda r: r.y0)):
            lab.append((f"{key}#{i + 1}", r))
    out = {}
    for r, t in _phrases(items):
        cy = (r.y0 + r.y1) / 2
        cands = [(r.x0 - lr.x1, k) for k, lr in lab if abs((lr.y0 + lr.y1) / 2 - cy) < 8 and lr.x1 <= r.x0 + 2]
        if cands:
            out.setdefault(min(cands)[1], t)
    return out


def _answer(page, checks):
    ans = None
    for cr in checks:
        cy = (cr.y0 + cr.y1) / 2
        labs = [(cr.x0 - lr.x1, w) for w in ("YES", "NO") for lr in page.search_for(w)
                if abs((lr.y0 + lr.y1) / 2 - cy) < 8 and lr.x1 <= cr.x0 + 2]
        if labs:
            ans = min(labs)[1]
    return ans


_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def parse(path, template_path=None):
    """-> dict(method, official{...}, rows[{item, business_name, address, related_person, relationship, detail, page}])

    template_path: any fillable filing; its text layer is the blank template
    used to tell typed values from form text in flattened filings."""
    import pymupdf
    doc = pymupdf.open(path)
    ref = pymupdf.open(template_path) if template_path else None
    fillable = any(True for pg in doc for _ in pg.widgets())
    if fillable:
        method = "widgets"
    else:
        # Values present as real text? Compare page 1 against the template.
        p0 = doc[0]
        extra, _ = _items_text(p0, ref[0] if ref else None)
        # Real text values if the official's first name reads from the text layer.
        named = _labelled(p0, extra, ["First Name:"]).get("First Name:#1")
        method = "text" if ref is not None and named else "ocr"
    rows, official = [], {}
    for idx, page in enumerate(doc):
        if idx not in (0, 9) and idx not in TABLES and idx not in QUESTIONS:
            continue
        rp = ref[idx] if ref is not None and idx < len(ref) else None
        if method == "widgets":
            items, checks = _items_widgets(page)
        elif method == "text":
            items, checks = _items_text(page, rp)
        else:
            items, checks = _items_ocr(page, rp)
        if idx == 0:
            v = _labelled(page, items, ["Role of School Official:", "First Name:", "Middle Initial:", "Last Name:"])
            official = {"role": v.get("Role of School Official:#1"),
                        "name": " ".join(x for x in (v.get("First Name:#1"), v.get("Last Name:#1")) if x),
                        "spouse": " ".join(x for x in (v.get("First Name:#2"), v.get("Last Name:#2")) if x) or None}
        elif idx == 9:
            v = _labelled(page, items, ["Certified by:", "Date of Certification:"])
            official["certified_by"] = v.get("Certified by:#1")
            official["certified_on"] = v.get("Date of Certification:#1")
        if idx in QUESTIONS and fillable:
            a = _answer(page, checks)
            if a:
                rows.append({"item": f"answer:{QUESTIONS[idx]}", "detail": a, "page": idx + 1})
        if idx in TABLES:
            item, headers = TABLES[idx]
            for r in _table_rows(page, items, headers):
                row = {"item": item, "page": idx + 1, **r}
                if item in ("relative_employed", "relative_contract") and not row.get("related_person"):
                    continue
                if item not in ("relative_employed", "relative_contract") and not row.get("business_name"):
                    continue
                rows.append(row)
    for r in rows:
        addr = r.get("address") or ""
        lines = [x.strip() for x in addr.split("\n") if x.strip()]
        r["street"] = lines[0] if lines else None
        m = _ZIP.search(addr)
        r["zip"] = m.group(1) if m else None
    return {"method": method, "official": official, "rows": rows}


def load_parsed(con, filing, sha, local_path, body, parsed):
    """Write parsed rows into disclosures, keyed by the PDF's sha256 in
    source_files (so re-loading is a no-op). source_row = PDF page."""
    import json
    hit = con.execute("SELECT file_id FROM source_files WHERE sha256 = ?", [sha]).fetchone()
    if hit:
        return 0
    con.execute("BEGIN")
    try:
        n = _load_parsed(con, filing, sha, local_path, body, parsed)
        con.execute("COMMIT")
        return n
    except Exception:
        con.execute("ROLLBACK")
        raise


def _load_parsed(con, filing, sha, local_path, body, parsed):
    import json
    fid = con.execute("INSERT INTO source_files (source_type, path, sha256, row_count, note) VALUES "
                      "('disclosures', ?, ?, ?, ?) RETURNING file_id",
                      [local_path, sha, len(parsed["rows"]), f"school ethics filing {filing['id']} ({parsed['method']})"]
                      ).fetchone()[0]
    off = parsed["official"]
    name = off.get("name") or f"{filing['firstName']} {filing['lastName']}"
    vals = []
    for r in parsed["rows"]:
        raw = json.dumps({"filing_id": filing["id"], "method": parsed["method"], "spouse": off.get("spouse"), **r})
        vals.append([fid, r["page"], raw, body, name, off.get("role") or filing["position"],
                     r.get("business_name"), r.get("street"), r.get("zip"), r.get("relationship"),
                     filing["year"], r["item"], r.get("related_person"), r.get("detail")])
    if not vals:  # keep a marker row so the filing is visibly "loaded, nothing disclosed"
        vals.append([fid, 1, json.dumps({"filing_id": filing["id"], "method": parsed["method"]}), body, name,
                     off.get("role") or filing["position"], None, None, None, None, filing["year"],
                     "no_disclosures", None, None])
    from moneytrail.schema import bulk_insert
    bulk_insert(con, "disclosures", ["file_id", "source_row", "raw", "public_body", "official_name", "role",
                                     "business_name", "business_street", "business_zip", "relationship",
                                     "filing_year", "item", "related_person", "detail"], vals)
    return len(vals)


def ingest(con, root, district_code, body, years=None, log=print):
    """Fetch, parse and load every statement for a district. Returns a
    summary including filings that parsed to nothing (need manual review)."""
    got = fetch_district(con, root, district_code, body, years, log)
    paths = {sha: con.execute("SELECT local_path FROM documents WHERE sha256 = ?", [sha]).fetchone()[0]
             for _, sha in got}
    import pymupdf
    template = next((os.path.join(root, p) for p in paths.values()
                     if any(True for pg in pymupdf.open(os.path.join(root, p)) for _ in pg.widgets())), None)
    loaded, review = 0, []
    for filing, sha in got:
        if con.execute("SELECT 1 FROM source_files WHERE sha256 = ?", [sha]).fetchone():
            continue
        parsed = parse(os.path.join(root, paths[sha]), template)
        if not parsed["official"].get("name"):
            review.append(f"{filing['year']} {filing['firstName']} {filing['lastName']} ({parsed['method']}): "
                          f"{paths[sha]}")
        loaded += load_parsed(con, filing, sha, paths[sha], body, parsed)
    return {"filings": len(got), "rows_loaded": loaded, "needs_review": review}
