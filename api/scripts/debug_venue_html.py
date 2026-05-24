"""Reusable HTML diagnostic for venue event pages.

Usage:
    python -m scripts.debug_venue_html <url>

Shows: response size, heading counts, top headings + their parent class,
script types, structured-data hits, and a sample of date-shaped strings
in the raw body — enough to figure out the right BS4 selectors without
guessing.
"""
import re
import sys
from collections import Counter

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ah-events-scraper/1.0; +https://ahnj.info)",
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9",
}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.debug_venue_html <url>")
        return 2
    url = sys.argv[1]

    r = requests.get(url, headers=HEADERS, timeout=20)
    body = r.text
    print(f"HTTP {r.status_code} | {len(body)} bytes | CT={r.headers.get('content-type')}")
    soup = BeautifulSoup(body, "html.parser")
    title = soup.find("title")
    print(f"<title>: {title.get_text() if title else '(none)'}")

    # Heading inventory
    for tag in ("h1", "h2", "h3", "h4"):
        n = len(soup.find_all(tag))
        print(f"<{tag}> count: {n}")
    print(f"<script type='application/ld+json'>: {len(soup.find_all('script', type='application/ld+json'))}")
    print(f"<noscript>: {len(soup.find_all('noscript'))}")

    # Top h2/h3 samples with parent class context (this is what found the
    # Proving Ground selector last time).
    for tag in ("h2", "h3"):
        items = soup.find_all(tag)[:25]
        if not items:
            continue
        print(f"\n--- first {len(items)} <{tag}> with parent.class ---")
        for i, el in enumerate(items):
            parent = el.parent
            pc = " ".join(parent.get("class") or []) if parent else ""
            print(f"  [{i}] parent='{pc[:55]}' :: {el.get_text(' ', strip=True)[:90]}")

    # Most common classes on divs (helps spot event containers)
    classes = Counter()
    for d in soup.find_all("div", class_=True):
        for c in d.get("class") or []:
            classes[c] += 1
    print("\n--- top 15 div classes ---")
    for c, n in classes.most_common(15):
        if n >= 2:
            print(f"  {n:4d}  .{c}")

    # JSON-LD blobs (truncated)
    for i, s in enumerate(soup.find_all("script", type="application/ld+json")[:3]):
        snippet = (s.string or "").strip()[:300]
        print(f"\n--- ld+json [{i}] ---\n{snippet}")

    # Date-shaped strings in raw body (first 8)
    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    matches = re.findall(rf"\b(?:{months})[a-z]*\.?\s+\d{{1,2}}(?:st|nd|rd|th)?", body, re.I)
    print(f"\ndate-shaped matches: {len(matches)} -- first 8: {matches[:8]}")

    # CLI flag: --dump <selector> prints inner text of first 3 elements
    if "--dump" in sys.argv:
        sel = sys.argv[sys.argv.index("--dump") + 1]
        print(f"\n--- inner text of first 3 `{sel}` ---")
        for i, el in enumerate(soup.select(sel)[:3]):
            print(f"\n[{i}]\n{el.prettify()[:1200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
