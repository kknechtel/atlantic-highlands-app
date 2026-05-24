"""Dump the inner text of a CSS selector via Playwright. Used to figure
out the post-render DOM shape for JS-rendered venue calendars.

Usage:
    python -m scripts.debug_playwright_dump <url> <selector> [count]
"""
import sys

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python -m scripts.debug_playwright_dump <url> <selector> [count]")
        return 2
    url = sys.argv[1]
    selector = sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            c = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 1800})
            page = c.new_page()
            page.set_default_timeout(25000)
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(5000)
            html = page.content()
        finally:
            b.close()
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(["svg", "style", "script"]):
        s.decompose()
    items = soup.select(selector)
    print(f"=== {selector} on {url} === found {len(items)}")
    for i, el in enumerate(items[:n]):
        cls = " ".join(el.get("class") or [])
        text = el.get_text(" | ", strip=True)
        print(f"[{i}] .{cls[:60]}")
        print(f"  {text[:300]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
