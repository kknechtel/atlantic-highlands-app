"""Probe a venue page using Playwright, dump heading inventory + top
selectors AFTER the JS render. Use to figure out what classes events
actually have once the client-side widgets hydrate.

Usage:
    python -m scripts.debug_playwright <url>
"""
import re
import sys
from collections import Counter

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.debug_playwright <url>")
        return 2
    url = sys.argv[1]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1800})
            page = ctx.new_page()
            page.set_default_timeout(25_000)
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(5_000)
            html = page.content()
        finally:
            browser.close()

    print(f"rendered size: {len(html)} bytes")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    print(f"<title>: {title.get_text() if title else '(none)'}")
    for tag in ("h1", "h2", "h3", "h4"):
        print(f"<{tag}>: {len(soup.find_all(tag))}")

    classes = Counter()
    for d in soup.find_all("div", class_=True):
        for c in d.get("class") or []:
            classes[c] += 1
    print("\n--- top 25 div classes ---")
    for c, n in classes.most_common(25):
        if n >= 2:
            print(f"  {n:4d}  .{c}")

    print("\n--- first 15 <h2> with parent class ---")
    for i, h2 in enumerate(soup.find_all("h2")[:15]):
        parent = h2.parent
        pc = " ".join(parent.get("class") or []) if parent else "?"
        print(f"  [{i}] parent={pc[:50]!r:50s} :: {h2.get_text(' ', strip=True)[:80]}")

    months = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    matches = re.findall(rf"\b(?:{months})[a-z]*\.?\s+\d{{1,2}}(?:st|nd|rd|th)?", html, re.I)
    print(f"\ndate-shaped: {len(matches)} -- first 10: {matches[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
