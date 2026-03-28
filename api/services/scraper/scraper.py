"""
Core scraper module.
Level 1: requests + BeautifulSoup (works for most static pages)
Level 2: Selenium fallback for JavaScript-heavy pages
"""
import io
import time
import logging
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .config import (
    DOWNLOAD_EXTENSIONS,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    USER_AGENT,
)
from .utils import url_to_filename, categorize_url

logger = logging.getLogger("ah_scraper")


class BasicScraper:
    """Level 1 scraper using requests + BeautifulSoup."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def fetch_page(self, url: str) -> BeautifulSoup | None:
        """Fetch a page and return parsed HTML."""
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Fetching: {url}")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                time.sleep(REQUEST_DELAY)
                return BeautifulSoup(resp.text, "html.parser")
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (403, 404, 410):
                    logger.warning(f"HTTP {status} for {url} — skipping")
                    return None
                logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} failed for {url}: {e}")
                time.sleep(REQUEST_DELAY * 2)
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} failed for {url}: {e}")
                time.sleep(REQUEST_DELAY * 2)
        logger.error(f"Failed to fetch after {MAX_RETRIES} attempts: {url}")
        return None

    def find_document_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract all links to downloadable documents from a page."""
        documents = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            path_lower = parsed.path.lower()

            is_document = any(path_lower.endswith(ext) for ext in DOWNLOAD_EXTENSIONS)
            if not is_document:
                if "download" in href.lower() or "document" in href.lower():
                    is_document = True

            if is_document:
                link_text = link.get_text(strip=True) or url_to_filename(full_url)
                documents.append({
                    "url": full_url,
                    "title": link_text,
                    "source_page": base_url,
                })
        return documents

    def find_subpage_links(self, soup: BeautifulSoup, base_url: str, same_domain: bool = True) -> list[str]:
        """Find links to other pages on the same site to crawl deeper."""
        links = set()
        base_domain = urlparse(base_url).netloc
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            if parsed.scheme not in ("http", "https"):
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            if same_domain and parsed.netloc != base_domain:
                continue
            if any(parsed.path.lower().endswith(ext) for ext in DOWNLOAD_EXTENSIONS):
                continue
            links.add(full_url)
        return list(links)

    def download_file_to_bytes(self, url: str) -> tuple[bytes | None, str]:
        """Download a file and return (content_bytes, filename). Returns (None, '') on failure."""
        filename = url_to_filename(url)
        try:
            logger.info(f"  [DOWNLOAD] {filename}")
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
            resp.raise_for_status()

            buf = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=8192):
                buf.write(chunk)

            time.sleep(REQUEST_DELAY)
            return buf.getvalue(), filename
        except requests.RequestException as e:
            logger.error(f"  [FAIL] Download failed for {url}: {e}")
            return None, filename


class SeleniumScraper:
    """Level 2 scraper for JavaScript-heavy sites."""

    def __init__(self):
        self.driver = None

    def _ensure_driver(self):
        if self.driver is not None:
            return
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"--user-agent={USER_AGENT}")
            options.add_argument("--window-size=1920,1080")

            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            except ImportError:
                self.driver = webdriver.Chrome(options=options)

            self.driver.set_page_load_timeout(60)
            logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Selenium: {e}")
            raise

    def fetch_page(self, url: str) -> BeautifulSoup | None:
        self._ensure_driver()
        try:
            logger.info(f"[Selenium] Fetching: {url}")
            self.driver.get(url)
            time.sleep(3)
            html = self.driver.page_source
            time.sleep(REQUEST_DELAY)
            return BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.error(f"[Selenium] Failed to fetch {url}: {e}")
            return None

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
