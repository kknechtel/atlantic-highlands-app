"""
Site-specific crawlers adapted for S3 upload.
Each crawler finds documents and uploads them to S3 via the provided callback.
"""
import logging
import time
from urllib.parse import urljoin, urlparse

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
        """Crawl and return list of found documents (no downloading)."""
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
    """Crawler for ecode360.com (Atlantic Highlands document archive)."""

    def __init__(self):
        self.source_name = "ecode360"
        self.config = SOURCES["ecode360"]
        self.basic = BasicScraper()
        self.selenium = None

    def _get_scraper(self):
        if self.selenium is None:
            try:
                self.selenium = SeleniumScraper()
                self.selenium._ensure_driver()
            except Exception:
                logger.warning("Selenium not available for ecode360 — using basic scraper")
                self.selenium = False
        return self.selenium if self.selenium else self.basic

    def find_documents(self) -> list[dict]:
        all_docs = []
        scraper = self._get_scraper()

        for page_path in self.config["pages_to_crawl"]:
            url = self.config["base_url"] + page_path
            soup = scraper.fetch_page(url)
            if not soup:
                continue

            docs = self.basic.find_document_links(soup, url)
            all_docs.extend(docs)
            logger.info(f"  Found {len(docs)} documents on {page_path}")

            page_links = soup.find_all("a", href=True)
            for link in page_links:
                href = link["href"]
                text = link.get_text(strip=True).lower()
                if any(kw in text for kw in ["next", "more", "page 2", "page 3"]):
                    next_url = urljoin(url, href)
                    next_soup = scraper.fetch_page(next_url)
                    if next_soup:
                        more_docs = self.basic.find_document_links(next_soup, next_url)
                        all_docs.extend(more_docs)

        self._cleanup()
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        if self.selenium and self.selenium is not False:
            self.selenium.close()


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
