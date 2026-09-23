"""Document fetcher with a custody log.

For every seed page in sources.py, collect links to documents and download
them to data/raw/<source>/<sha256[:2]>/<sha256>.<ext>. Each retrieval is
logged in `documents` (one row per distinct content) and `retrievals` (one
row per HTTP fetch): URL, link text, the page it was linked from, time, HTTP
status, ETag/Last-Modified, byte size, sha256. Re-runs skip URLs already
held unless --refresh; a changed file under the same URL is kept as a new
version, never overwritten.
"""
import hashlib
import mimetypes
import os
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

from moneytrail.sources import DOC_CLASSES, SOURCES

UA = "moneytrail/0.1 (public-records research; contact via repository owner)"
DOC_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv")
DOC_HOSTS = ("files.edl.io",)  # Edlio file CDN: no extension-less surprises, but always documents
DELAY = 1.0


_A = re.compile(r"""<a\b[^>]*href\s*=\s*(?:"([^"]+)"|'([^']+)')[^>]*>(.*?)</a>""", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_IN_TITLE = re.compile(rf"({_MONTHS})\s*(\d{{1,2}}),?\s*(\d{{4}})", re.I)


def init(con):
    from moneytrail import schema
    schema.init(con)


def classify(title, url=""):
    s = f"{title} {url}"
    for cls, pat in DOC_CLASSES:
        if re.search(pat, s, re.I):
            return cls
    return "other"


def title_date(title):
    m = _DATE_IN_TITLE.search(title or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
    except ValueError:
        return None


def is_doc_link(url):
    p = urlparse(url)
    return p.path.lower().endswith(DOC_EXT) or any(p.netloc.endswith(h) for h in DOC_HOSTS)


def _anchors(html, base):
    for dq, sq, inner in _A.findall(html):
        url = urljoin(base, unescape((dq or sq).strip())).split("#")[0]
        if url.startswith("http"):
            yield url, " ".join(unescape(_TAG.sub(" ", inner)).split())


def links(html, base):
    out, seen = [], set()
    for url, text in _anchors(html, base):
        if url in seen or not is_doc_link(url):
            continue
        seen.add(url)
        out.append((url, text))
    return out


def child_pages(html, base):
    """Same-site pages below `base` (directory-style sites)."""
    b = base if base.endswith("/") else base + "/"
    return sorted({u for u, _ in _anchors(html, base)
                   if u.startswith(b) and u != b and not is_doc_link(u) and u.endswith("/")})


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fetch_all(con, root, only=None, refresh=False, limit=None, log=print, session=None):
    init(con)
    s = session or requests.Session()
    s.headers["User-Agent"] = UA
    held = {r[0] for r in con.execute("SELECT DISTINCT url FROM retrievals WHERE sha256 IS NOT NULL").fetchall()}
    stats = {"pages": 0, "links": 0, "new": 0, "skipped": 0, "changed": 0, "errors": 0}
    for source, cfg in SOURCES.items():
        if only and source not in only:
            continue
        queue = [(p, 0) for p in cfg["pages"]]
        visited = set()
        while queue:
            page, depth = queue.pop(0)
            if page in visited:
                continue
            visited.add(page)
            try:
                r = s.get(page, timeout=30)
                r.raise_for_status()
            except requests.RequestException as e:
                log(f"  page failed {page}: {e}")
                stats["errors"] += 1
                continue
            stats["pages"] += 1
            if depth < cfg.get("follow_children", 0):
                queue += [(c, depth + 1) for c in child_pages(r.text, page) if c not in visited]
            found = links(r.text, page)
            stats["links"] += len(found)
            log(f"{source}: {len(found)} document links on {page}")
            for url, title in found:
                if limit is not None and stats["new"] + stats["changed"] >= limit:
                    return stats
                if url in held and not refresh:
                    stats["skipped"] += 1
                    continue
                time.sleep(DELAY)
                res = _download(con, s, root, source, cfg["body"], url, title, page)
                held.add(url)
                stats[res] += 1
    return stats


def _download(con, s, root, source, body, url, title, referrer):
    at = _now()
    try:
        r = s.get(url, timeout=120)
        status = r.status_code
        r.raise_for_status()
    except requests.RequestException as e:
        con.execute("INSERT INTO retrievals VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?)",
                    [url, referrer, title, at, getattr(getattr(e, "response", None), "status_code", None), str(e)[:500]])
        return "errors"
    data = r.content
    digest = hashlib.sha256(data).hexdigest()
    ctype = r.headers.get("Content-Type", "").split(";")[0].strip()
    ext = os.path.splitext(urlparse(url).path)[1].lower() or mimetypes.guess_extension(ctype) or ".bin"
    rel = os.path.join(source, digest[:2], digest + ext)
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    con.execute("INSERT INTO retrievals VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [url, referrer, title, at, status, r.headers.get("ETag"), r.headers.get("Last-Modified"), digest])
    prior = con.execute("SELECT count(*) FROM documents WHERE url = ?", [url]).fetchone()[0]
    if con.execute("SELECT 1 FROM documents WHERE sha256 = ?", [digest]).fetchone():
        return "skipped"
    con.execute("INSERT INTO documents (sha256, source, public_body, url, title, doc_class, doc_date, content_type, "
                "bytes, local_path, first_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [digest, source, body, url, title, classify(title, url), title_date(title), ctype, len(data), rel, at])
    return "changed" if prior else "new"


def extract_text(con, root, log=print):
    """PDF text per page into doc_text. Scanned PDFs yield little text; those
    are listed so they can go through the app's OCR pipeline."""
    import pymupdf
    init(con)
    todo = con.execute("SELECT sha256, local_path FROM documents WHERE NOT text_extracted "
                       "AND lower(local_path) LIKE '%.pdf'").fetchall()
    thin = []
    for digest, rel in todo:
        try:
            doc = pymupdf.open(os.path.join(root, rel))
            pages = [(digest, i + 1, p.get_text()) for i, p in enumerate(doc)]
        except Exception as e:  # corrupt/encrypted PDF: record and move on
            log(f"  text failed {rel}: {e}")
            continue
        con.execute("DELETE FROM doc_text WHERE sha256 = ?", [digest])
        from moneytrail.schema import bulk_insert
        bulk_insert(con, "doc_text", ["sha256", "page", "text"], pages)
        con.execute("UPDATE documents SET text_extracted = true WHERE sha256 = ?", [digest])
        if sum(len(t.strip()) for _, _, t in pages) < 200 * max(1, len(pages)) // 4:
            thin.append(rel)
    return {"extracted": len(todo), "needs_ocr": thin}


def ocr_pages(con, root, sha, pages, dpi=300):
    """OCR selected pages of a scanned PDF into doc_text (replacing empty
    text-layer rows). Used for the tail of scanned audit reports, where the
    comments and recommendations are."""
    import io

    import pymupdf
    import pytesseract
    from PIL import Image
    rel = con.execute("SELECT local_path FROM documents WHERE sha256 = ?", [sha]).fetchone()[0]
    doc = pymupdf.open(os.path.join(root, rel))
    done = 0
    for pno in pages:
        if not 1 <= pno <= len(doc):
            continue
        pix = doc[pno - 1].get_pixmap(dpi=dpi)
        txt = pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))))
        con.execute("DELETE FROM doc_text WHERE sha256 = ? AND page = ?", [sha, pno])
        con.execute("INSERT INTO doc_text VALUES (?, ?, ?)", [sha, pno, txt])
        done += 1
    return done
