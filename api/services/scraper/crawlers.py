"""
Site-specific crawlers adapted for S3 upload.
Each crawler finds documents and uploads them to S3 via the provided callback.
"""
import logging
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .scraper import BasicScraper, SeleniumScraper
from .utils import categorize_url
from .config import SOURCES, REQUEST_DELAY

logger = logging.getLogger("ah_scraper")


def _deduplicate_docs(docs: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for doc in docs:
        if doc["url"] not in seen:
            seen.add(doc["url"])
            unique.append(doc)
    return unique


def _get_stealth_driver():
    """Create a Selenium driver with anti-detection flags for Cloudflare sites."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--window-size=1920,1080')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        logger.error(f"Failed to create stealth driver: {e}")
        return None


class AHNJCrawler:
    """Crawler for ahnj.com (Borough of Atlantic Highlands)."""

    def __init__(self):
        self.source_name = "ahnj"
        self.config = SOURCES["ahnj"]
        self.basic = BasicScraper()
        self.selenium = None

    def _get_scraper(self):
        if self.selenium is None:
            try:
                self.selenium = SeleniumScraper()
                self.selenium._ensure_driver()
            except Exception:
                logger.warning("Selenium not available for ahnj.com — using basic scraper")
                self.selenium = False
        return self.selenium if self.selenium else self.basic

    def find_documents(self) -> list[dict]:
        all_docs = []
        scraper = self._get_scraper()
        visited = set()

        for page_path in self.config["pages_to_crawl"]:
            url = self.config["base_url"] + page_path
            if url in visited:
                continue
            visited.add(url)

            soup = scraper.fetch_page(url)
            if not soup:
                continue

            docs = self.basic.find_document_links(soup, url)
            all_docs.extend(docs)
            if docs:
                logger.info(f"  Found {len(docs)} documents on {page_path}")

            subpages = self.basic.find_subpage_links(soup, url, same_domain=True)
            for subpage in subpages[:20]:
                if subpage in visited:
                    continue
                visited.add(subpage)
                sub_soup = scraper.fetch_page(subpage)
                if sub_soup:
                    sub_docs = self.basic.find_document_links(sub_soup, subpage)
                    all_docs.extend(sub_docs)
                    if sub_docs:
                        logger.info(f"  Found {len(sub_docs)} documents on {subpage}")

        self._cleanup()
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        if self.selenium and self.selenium is not False:
            self.selenium.close()


class ECode360Crawler:
    """
    Crawler for ecode360.com (Atlantic Highlands document archive).
    Requires visible Chrome to bypass Cloudflare Turnstile.
    """

    def __init__(self):
        self.source_name = "ecode360"
        self.config = SOURCES["ecode360"]
        self.base_url = "https://ecode360.com"
        self.driver = None

    # Document categories on ecode360
    CATEGORIES = [
        "/AT0153/documents/Agendas",
        "/AT0153/documents/Budgets",
        "/AT0153/documents/Comprehensive_Plans",
        "/AT0153/documents/Legislation",
        "/AT0153/documents/Minutes",
        "/AT0153/documents/Misc._Documents",
        "/AT0153/documents/Resolutions",
    ]

    def find_documents(self) -> list[dict]:
        all_docs = []
        self.driver = _get_stealth_driver()
        if not self.driver:
            logger.error("Cannot crawl ecode360 without Chrome - Cloudflare protection")
            return []

        try:
            for cat_path in self.CATEGORIES:
                url = self.base_url + cat_path
                cat_name = cat_path.split("/")[-1].replace("_", " ")
                logger.info(f"  Crawling ecode360: {cat_name}")

                self.driver.get(url)
                time.sleep(8)

                title = self.driver.title
                if "moment" in title.lower():
                    logger.warning(f"  Cloudflare blocking {cat_name}, waiting...")
                    time.sleep(15)

                soup = BeautifulSoup(self.driver.page_source, "html.parser")
                links = soup.find_all("a", href=True)

                for link in links:
                    href = link["href"]
                    if ".pdf" in href.lower():
                        full_url = urljoin(self.base_url, href)
                        link_text = link.get_text(strip=True) or ""
                        all_docs.append({
                            "url": full_url,
                            "title": link_text,
                            "source_page": url,
                            "category": cat_name,
                        })

                found = len([l for l in links if ".pdf" in l["href"].lower()])
                if found:
                    logger.info(f"  Found {found} PDFs in {cat_name}")

                # Check for subcategory links
                for link in links:
                    href = link["href"]
                    if "category=" in href or "subCategory=" in href:
                        sub_url = urljoin(self.base_url, href)
                        sub_name = link.get_text(strip=True)
                        logger.info(f"  Following subcategory: {sub_name}")
                        self.driver.get(sub_url)
                        time.sleep(5)
                        sub_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                        for sub_link in sub_soup.find_all("a", href=True):
                            if ".pdf" in sub_link["href"].lower():
                                full_url = urljoin(self.base_url, sub_link["href"])
                                all_docs.append({
                                    "url": full_url,
                                    "title": sub_link.get_text(strip=True) or "",
                                    "source_page": sub_url,
                                    "category": cat_name,
                                })

        except Exception as e:
            logger.error(f"ECode360 crawl error: {e}", exc_info=True)
        finally:
            self._cleanup()

        result = _deduplicate_docs(all_docs)
        logger.info(f"  ECode360 total: {len(result)} unique documents")
        return result

    def _cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


class TriDistrictCrawler:
    """Crawler for tridistrict.org (School District)."""

    def __init__(self):
        self.source_name = "tridistrict"
        self.config = SOURCES["tridistrict"]
        self.basic = BasicScraper()
        self.selenium = None

    def _get_scraper(self):
        if self.selenium is None:
            try:
                self.selenium = SeleniumScraper()
                self.selenium._ensure_driver()
            except Exception:
                logger.warning("Selenium not available for tridistrict — using basic scraper")
                self.selenium = False
        return self.selenium if self.selenium else self.basic

    def _is_crawlable(self, url: str) -> bool:
        ok_patterns = ["/apps/pages/", "/apps/news/", "/apps/events/",
                       "/apps/documents/", "/legalnotices", "/apps/maps"]
        path = urlparse(url).path.lower()
        if path in ("", "/"):
            return True
        return any(p in path for p in ok_patterns)

    def find_documents(self) -> list[dict]:
        all_docs = []
        scraper = self._get_scraper()
        visited = set()

        seed_urls = [self.config["base_url"] + "/"]
        for school_url in self.config.get("school_sites", []):
            seed_urls.append(school_url)

        to_crawl = list(seed_urls)
        depth = 0
        max_depth = 2
        max_pages = 80

        while to_crawl and depth <= max_depth and len(visited) < max_pages:
            next_round = []
            for url in to_crawl:
                if url in visited:
                    continue
                visited.add(url)

                soup = scraper.fetch_page(url)
                if not soup:
                    continue

                docs = self.basic.find_document_links(soup, url)
                all_docs.extend(docs)
                if docs:
                    logger.info(f"  Found {len(docs)} documents on {url}")

                subpages = self.basic.find_subpage_links(soup, url, same_domain=False)
                for subpage in subpages:
                    if subpage not in visited and self._is_crawlable(subpage):
                        host = urlparse(subpage).netloc
                        if "tridistrict.org" in host:
                            next_round.append(subpage)

            to_crawl = next_round
            depth += 1
            logger.info(f"  Depth {depth}: discovered {len(next_round)} more pages to crawl")

        self._cleanup()
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        if self.selenium and self.selenium is not False:
            self.selenium.close()
