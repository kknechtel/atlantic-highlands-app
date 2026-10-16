"""
eCode360 (General Code) document library behind Cloudflare Turnstile.

A headless Chromium (Playwright) loads the library pages and clears the
challenge once; its cookies (cf_clearance) and User-Agent are copied onto a
requests session, so the PDFs themselves download over the ordinary fast path.
Works headless on a server — no visible Chrome needed (replaces the
Selenium/stealth-Chrome crawler that only ran from a desktop).

Chromium comes from PLAYWRIGHT_CHROMIUM (executable path) or Playwright's own
install (`playwright install --with-deps chromium`, already required by the
event scrapers).
"""
from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import REQUEST_DELAY
from .scraper import BasicScraper
from .utils import url_to_filename

logger = logging.getLogger(__name__)

BROWSER_UA = os.getenv(
    "BROWSER_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
)


class BrowserPages:
    """Context manager: rendered HTML for URLs, then cookies handed to a requests session."""

    def __init__(self, challenge_wait_s: int = 30):
        self.challenge_wait_s = challenge_wait_s
        self._pw = self._browser = self._ctx = self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = {"args": ["--disable-blink-features=AutomationControlled"]}
        if os.getenv("PLAYWRIGHT_CHROMIUM"):
            kw["executable_path"] = os.environ["PLAYWRIGHT_CHROMIUM"]
        self._browser = self._pw.chromium.launch(**kw)
        self._ctx = self._browser.new_context(user_agent=BROWSER_UA, locale="en-US", viewport={"width": 1300, "height": 900})
        self._page = self._ctx.new_page()
        return self

    def get(self, url: str) -> str | None:
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
            for _ in range(self.challenge_wait_s // 2):
                if "just a moment" not in (self._page.title() or "").lower():
                    break
                self._page.wait_for_timeout(2000)
            else:
                logger.warning("ecode360: challenge not cleared for %s", url)
                return None
            self._page.wait_for_timeout(1000)
            return self._page.content()
        except Exception as exc:
            logger.warning("ecode360: browser fetch failed for %s: %s", url, exc)
            return None

    def share_cookies(self, session: requests.Session) -> None:
        session.headers["User-Agent"] = BROWSER_UA
        for c in self._ctx.cookies():
            session.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))

    def __exit__(self, *exc):
        for obj, meth in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass


class ClearedDownloader(BasicScraper):
    """BasicScraper whose downloads reuse the browser's Cloudflare clearance and
    adapt to the host: 429 → honour Retry-After (else exponential backoff) and
    slow the pace for good; 403/503 → clearance expired, re-clear once and retry."""

    def __init__(self, warm_url: str, delay: float = REQUEST_DELAY):
        super().__init__()
        self.warm_url = warm_url
        self.delay = delay

    def download_file_to_bytes(self, url: str) -> tuple[bytes | None, str]:
        fname = url_to_filename(url)
        recleared = False
        for attempt in range(6):
            try:
                r = self.session.get(url, timeout=(10, 90))
            except requests.RequestException as exc:
                self.errors.append(f"download failed {url}: {exc}")
                return None, fname
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After") or 0) or min(300, 15 * 2 ** attempt)
                self.delay = min(10.0, self.delay * 1.5 + 0.5)
                logger.info("ecode360: 429 - waiting %.0fs, pace now %.1fs/request", wait, self.delay)
                time.sleep(wait)
                continue
            if r.status_code in (403, 503) and not recleared:
                logger.info("ecode360: clearance expired - re-clearing")
                with BrowserPages() as b:
                    if b.get(self.warm_url):
                        b.share_cookies(self.session)
                recleared = True
                continue
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                logger.warning("ecode360: HTTP %s for %s", r.status_code, url)
                return None, fname
            time.sleep(self.delay)
            return r.content, fname
        self.errors.append(f"ecode360: gave up on {url} after repeated 429s")
        return None, fname


class ECode360Crawler:
    """Atlantic Highlands' eCode360 library: every resolution, minutes, agendas,
    budgets, legislation. Titles carry the resolution number ("2026-068 …")."""

    CUSTOMER = "AT0153"
    # library folder → doc_type hint
    CATEGORIES = {"Resolutions": "resolution", "Minutes": "minutes", "Agendas": "agenda", "Budgets": "budget",
                  "Legislation": "ordinance", "Misc._Documents": None, "Comprehensive_Plans": "planning"}

    def __init__(self):
        self.source_name = "ecode360"
        self.base_url = "https://ecode360.com"
        self.historical = False
        self.progress_callback = None
        warm = f"{self.base_url}/{self.CUSTOMER}/documents/Resolutions"
        # The runner downloads with crawler.downloader when present.
        self.basic = self.downloader = ClearedDownloader(warm, delay=max(REQUEST_DELAY, 1.0))

    def find_documents(self) -> list[dict]:
        found: list[dict] = []
        seen: set[str] = set()
        min_year = None if self.historical else int(os.getenv("ECODE360_MIN_YEAR", "0")) or None
        try:
            with BrowserPages() as browser:
                for cat, doc_type in self.CATEGORIES.items():
                    url = f"{self.base_url}/{self.CUSTOMER}/documents/{cat}"
                    html = browser.get(url)
                    if not html:
                        self.basic.errors.append(f"ecode360: could not load {url}")
                        continue
                    n = 0
                    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                        href = a["href"]
                        if "/document/" not in href or ".pdf" not in href.lower():
                            continue
                        full = urljoin(self.base_url, href)
                        if full in seen:
                            continue
                        title = " ".join(a.get_text(" ", strip=True).split())
                        years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", title)]
                        if min_year and years and max(years) < min_year:
                            continue
                        seen.add(full)
                        item = {"url": full, "title": f"{cat.replace('_', ' ').rstrip('.')} — {title}",
                                "source_page": url, "category": cat.replace("_", " ")}
                        if doc_type:
                            item["doc_type"] = doc_type
                        found.append(item)
                        n += 1
                    logger.info("  ecode360 %s: %d documents", cat, n)
                    if self.progress_callback:
                        self.progress_callback(n)
                browser.share_cookies(self.downloader.session)
        except Exception as exc:
            logger.error("ecode360 crawl error: %s", exc, exc_info=True)
            self.basic.errors.append(f"ecode360: {exc}")
        logger.info("  ECode360 total: %d unique documents", len(found))
        return found
