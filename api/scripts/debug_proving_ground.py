"""Dump diagnostics about what we actually see when we GET
theprovingground.com/events. Helps distinguish a parser bug
from JS-rendered content that's invisible to requests.get()."""
import re
import sys

import requests
from bs4 import BeautifulSoup

URL = "https://www.theprovingground.com/events"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ah-events-scraper/1.0; +https://ahnj.info)",
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9",
}


def main() -> int:
    r = requests.get(URL, headers=HEADERS, timeout=20)
    body = r.text
    print(f"HTTP {r.status_code} · {len(body)} bytes · ", end="")
    print(f"Content-Type: {r.headers.get('content-type')}")
    soup = BeautifulSoup(body, "html.parser")
    print(f"<h3> count: {len(soup.find_all('h3'))}")
    print(f"<h2> count: {len(soup.find_all('h2'))}")
    print(f"<h1> count: {len(soup.find_all('h1'))}")
    print(f"<p>  count: {len(soup.find_all('p'))}")
    print(f"<script type='application/ld+json'> count: "
          f"{len(soup.find_all('script', type='application/ld+json'))}")
    print(f"<noscript> count: {len(soup.find_all('noscript'))}")
    # Find any element mentioning a current/upcoming month name (May/June/etc.)
    month_re = re.compile(r"\b(?:May|June|July|August)\s+\d{1,2}", re.I)
    matches = month_re.findall(body)
    print(f"month/day matches in raw body: {len(matches)} -- first 5: {matches[:5]}")
    # Show title + first 600 chars of body text
    title = soup.find("title")
    print(f"\n<title>: {title.get_text() if title else '(none)'}")
    print(f"\n--- first 400 chars of body text ---")
    print(soup.get_text(" ", strip=True)[:400])
    print(f"\n--- last 400 chars of body text ---")
    print(soup.get_text(" ", strip=True)[-400:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
