"""
Crawlers, one per kind of site. A source in the municipality's sources.json
picks its crawler with the `crawler` key (see CRAWLERS at the bottom); every
crawler takes the source name and reads its settings from that source.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup

from .scraper import BasicScraper, SeleniumScraper
from .utils import categorize_url
from .config import SOURCES, RECORDING_SOURCES, REQUEST_DELAY
from municipality import TOWN, entity, entity_for_source
from services.meeting_dates import correct_future_date, year_from_url as _year_from_url

logger = logging.getLogger("ah_scraper")


def _deduplicate_docs(docs: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for doc in docs:
        if doc["url"] not in seen:
            seen.add(doc["url"])
            unique.append(doc)
    return unique


def _source_config(source_name: str) -> dict:
    return SOURCES.get(source_name) or RECORDING_SOURCES.get(source_name) or {}


def _source_category(source_name: str) -> str:
    """School or town, from the kind of government that publishes the source."""
    ent = entity(entity_for_source(source_name)) or {}
    return "school" if ent.get("kind") == "school" else "town"


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


class SiteCrawler:
    """Two-level crawl of a site's seed pages (pages_to_crawl, plus
    historical_pages when historical). Uses Selenium when available."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.basic = BasicScraper()
        self.selenium = None
        # When False, skip historical_pages (2005-2013 archive years).
        # Runner toggles this from the recent_only request flag.
        self.historical = True

    def _get_scraper(self):
        if self.selenium is None:
            try:
                self.selenium = SeleniumScraper()
                self.selenium._ensure_driver()
            except Exception:
                logger.warning(f"Selenium not available for {self.source_name} — using basic scraper")
                self.selenium = False
        return self.selenium if self.selenium else self.basic

    def find_documents(self) -> list[dict]:
        all_docs = []
        scraper = self._get_scraper()
        visited = set()
        # Two-level deep crawl from each seed: municipal archive trees often nest
        # /Archive/<Year>/<Month-Day>/<file>.pdf, so depth=1 misses most PDFs.
        max_pages = 250
        cb = getattr(self, "progress_callback", None)

        def _crawl(url: str, depth: int):
            if url in visited or len(visited) >= max_pages:
                return
            visited.add(url)
            soup = scraper.fetch_page(url)
            if not soup:
                return
            docs = self.basic.find_document_links(soup, url)
            if docs:
                all_docs.extend(docs)
                logger.info(f"  Found {len(docs)} documents on {url}")
                if cb:
                    cb(len(docs))
            if depth <= 0:
                return
            subpages = self.basic.find_subpage_links(soup, url, same_domain=True)
            # Cap fanout per page so we don't explode on side-nav menus
            for subpage in subpages[:30]:
                if len(visited) >= max_pages:
                    break
                _crawl(subpage, depth - 1)

        seed_paths = list(self.config["pages_to_crawl"])
        if self.historical:
            seed_paths += list(self.config.get("historical_pages", []))
        for page_path in seed_paths:
            url = self.config["base_url"] + page_path
            _crawl(url, depth=2)

        self._cleanup()
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        if self.selenium and self.selenium is not False:
            self.selenium.close()


class ECode360Crawler:
    """
    Crawler for a town's ecode360.com document archive.
    Requires visible Chrome to bypass Cloudflare Turnstile.
    """

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.base_url = self.config.get("base_url", "https://ecode360.com")
        self.driver = None
        # Document categories: the /<code>/documents/<Category> pages.
        self.CATEGORIES = [p for p in self.config.get("pages_to_crawl", []) if "/documents/" in p]

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


class OPRACrawler:
    """Crawler for OPRAmachine.com - crowdsourced OPRA requests for the town's
    public body (profile `opra_body`). Requires Selenium due to Cloudflare protection."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.driver = None

    def _slugs(self) -> list[str]:
        body = getattr(TOWN, "opra_body", None)
        if not body:
            return []
        kind = getattr(TOWN, "kind", None)
        return [body] + ([f"{kind}_of_{body}"] if kind else [])

    def find_documents(self) -> list[dict]:
        all_docs = []
        self.driver = _get_stealth_driver()
        if not self.driver:
            logger.warning("Cannot crawl OPRAmachine without Chrome — Cloudflare protection")
            return []

        try:
            # Try multiple possible slugs
            for slug in self._slugs():
                url = f"https://opramachine.com/body/{slug}"
                logger.info(f"  Trying OPRAmachine: {url}")
                self.driver.get(url)
                time.sleep(8)

                title = self.driver.title
                if "Attention Required" in title or "moment" in title.lower():
                    logger.warning(f"  Cloudflare blocking, waiting longer...")
                    time.sleep(15)

                if "Not Found" in self.driver.page_source or "404" in self.driver.title:
                    continue

                soup = BeautifulSoup(self.driver.page_source, "html.parser")

                # Find OPRA request links
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if "/request/" in href:
                        full_url = urljoin("https://opramachine.com", href)
                        link_text = link.get_text(strip=True) or "OPRA Request"
                        all_docs.append({
                            "url": full_url,
                            "title": f"OPRA: {link_text}",
                            "source_page": url,
                            "category": "opra",
                        })

                # Also grab any PDF attachments
                for link in soup.find_all("a", href=True):
                    if ".pdf" in link["href"].lower():
                        full_url = urljoin("https://opramachine.com", link["href"])
                        all_docs.append({
                            "url": full_url,
                            "title": link.get_text(strip=True) or "OPRA Attachment",
                            "source_page": url,
                            "category": "opra",
                        })

                if all_docs:
                    logger.info(f"  OPRAmachine: found {len(all_docs)} items from {slug}")
                    break

        except Exception as e:
            logger.error(f"OPRAmachine crawl error: {e}", exc_info=True)
        finally:
            self._cleanup()

        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


class PagesCrawler:
    """Queues a source's direct_downloads and collects document links from each
    of its pages_to_crawl (full URLs or paths under base_url). With
    `follow_subpages: N`, also scans the first N same-site links of each page."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.basic = BasicScraper()

    def find_documents(self) -> list[dict]:
        all_docs = []
        for url in self.config.get("direct_downloads", []):
            filename = url.split("/")[-1]
            if not filename or "." not in filename:
                filename = url.split("/")[-2] + ".pdf"
            all_docs.append({
                "url": url,
                "title": filename,
                "source_page": url,
                "category": self.source_name,
            })
            logger.info(f"  Queued direct download: {filename}")
        follow = int(self.config.get("follow_subpages", 0))
        for path in self.config.get("pages_to_crawl", []):
            url = self.config["base_url"] + path if path.startswith("/") else path
            try:
                soup = self.basic.fetch_page(url)
                if soup:
                    docs = self.basic.find_document_links(soup, url)
                    all_docs.extend(docs)
                    if follow:
                        subpages = self.basic.find_subpage_links(soup, url, same_domain=True)
                        for sub in subpages[:follow]:
                            sub_soup = self.basic.fetch_page(sub)
                            if sub_soup:
                                all_docs.extend(self.basic.find_document_links(sub_soup, sub))
                    if docs:
                        logger.info(f"  {self.source_name}: found {len(docs)} documents on {url}")
            except Exception as e:
                logger.warning(f"{self.source_name} scrape failed for {url}: {e}")
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        pass


class MunicodeMeetingsCrawler:
    """Crawler for a <town>.municodemeetings.com portal (council meeting
    agendas + packets, hosted on Microsoft Azure blob storage).

    The portal is a Drupal site with an infinite-scroll meetings table.
    Hitting `/` returns only the first ~15-20 meetings (~50 PDFs); the next
    pages live at `/?page=1`, `/?page=2`, … up to ~17. We paginate until a
    page yields no new PDFs."""

    MAX_PAGES = 30  # cap; real depth is ~18

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.basic = BasicScraper()
        self.progress_callback = None

    def find_documents(self) -> list[dict]:
        all_docs = []
        base = self.config["base_url"].rstrip("/")
        for page in range(self.MAX_PAGES):
            url = f"{base}/?page={page}" if page else f"{base}/"
            try:
                soup = self.basic.fetch_page(url)
                if not soup:
                    break
                docs = self.basic.find_document_links(soup, url)
                # Filter out ecode360-hosted PDFs: they're Cloudflare-Turnstile
                # protected and 403 on every retry from our IP. Each download
                # attempt costs ~5s (3 retries × delay), and a typical run
                # finds ~170 of them — that's ~15 min of guaranteed-wasted
                # time per run. ecode360 content is crawled separately by the
                # local scrape_ecode_local.py script.
                docs = [d for d in docs if "ecode360.com" not in urlparse(d["url"]).netloc.lower()]
                if not docs:
                    # Empty page = past the end of the infinite-scroll list.
                    logger.info(f"  {self.source_name} portal: no docs at page={page}, stopping")
                    break
                all_docs.extend(docs)
                logger.info(f"  {self.source_name} portal: page={page} → {len(docs)} documents")
                if self.progress_callback:
                    self.progress_callback(len(docs))
            except Exception as e:
                logger.warning(f"{self.source_name} scrape failed for {url}: {e}")
                break
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        pass


# ─── Meeting-recording crawlers ────────────────────────────────────
# Output records look like normal docs but always include `recording`
# metadata that runner.py reads to populate Document.metadata_:
#   { "url", "title", "source_page", "doc_type",
#     "recording": {
#       "platform":     "audio" | "youtube",
#       "meeting_body": "Borough Council" | "Planning Board" | ...,
#       "meeting_date": "YYYY-MM-DD",    # parsed from filename or page label
#       "youtube_id":   "..."            # YouTube only
#     }
#   }

# Year regex used by recording-folder discovery. Year-only links live next
# to month/day named subfolders we don't want to recurse into.
_YEAR_FOLDER_RE = re.compile(r"/(20\d{2})(?:%20Recordings)?/?$", re.I)


# Parse common recording filename date formats:
#   2024.03.05, 2024-03-05  → ymd
#   3.5.2024, 03-05-2024    → mdy
#   "March 5, 2024"         → month_name
#   Council_20240208_130626 → compact (YYYYMMDD with non-digit boundaries)
_DATE_PATTERNS = [
    (re.compile(r"(20\d{2})[.\-_](\d{1,2})[.\-_](\d{1,2})"), "ymd"),
    (re.compile(r"(\d{1,2})[.\-_](\d{1,2})[.\-_](20\d{2}|\d{2})"), "mdy"),
    (re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})",
        re.I,
    ), "month_name"),
    (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"), "compact"),
]
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _parse_meeting_date(text: str) -> str | None:
    """Return YYYY-MM-DD or None. Try several formats found across municipal portals."""
    text = unquote(text)
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "mdy":
                mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
            elif kind == "compact":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:  # month_name
                mo = _MONTHS.get(m.group(1)[:3].lower())
                d, y = int(m.group(2)), int(m.group(3))
                if not mo:
                    continue
            datetime(y, mo, d)  # validate
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except (ValueError, TypeError):
            continue
    return None


class FolderRecordingsCrawler:
    """Crawler for meeting recordings published as audio files in folder
    listings on the town site.

    One pass per entry in the source's `bodies`, flat or with year subfolders
    (`year_subfolders`). Filters to last 12 months by parsed filename
    date when present, else keeps the file if its source page is the
    current-year folder."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.category = _source_category(source_name)
        self.basic = BasicScraper()
        self.progress_callback = None
        # 12 months back from today. We compare to the parsed file date.
        self.cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).date()

    def find_documents(self) -> list[dict]:
        all_docs: list[dict] = []
        for body in self.config["bodies"]:
            base = self.config["base_url"] + body["path"]
            try:
                soup = self.basic.fetch_page(base)
            except Exception as e:
                logger.warning(f"{self.source_name} ({body['name']}) parent fetch failed: {e}")
                continue
            if not soup:
                continue

            pages_to_scan = [base]
            if body.get("year_subfolders"):
                # Two patterns in the wild:
                #   Harbor:  /Harbor Meeting Recordings/<YEAR> Recordings/<file>.wma
                #   Planning: /_Agendas and Minutes/<YEAR>/Recordings/<file>.wma
                # Walk year folders, then if the year folder has no media itself
                # look for a "Recordings" subfolder inside it.
                subs = self.basic.find_subpage_links(soup, base, same_domain=True)
                for s in subs:
                    m = _YEAR_FOLDER_RE.search(s)
                    if not m:
                        continue
                    year = int(m.group(1))
                    if year < self.cutoff.year - 1:
                        continue
                    pages_to_scan.append(s)
                    # Speculatively also add the per-year Recordings subfolder.
                    if not s.rstrip("/").lower().endswith("recordings"):
                        pages_to_scan.append(s.rstrip("/") + "/Recordings/")

            body_docs: list[dict] = []
            for page_url in pages_to_scan:
                try:
                    page_soup = self.basic.fetch_page(page_url) if page_url != base else soup
                    if not page_soup:
                        continue
                    media = self.basic.find_media_links(page_soup, page_url)
                except Exception as e:
                    logger.warning(f"{self.source_name} page failed {page_url}: {e}")
                    continue

                for item in media:
                    title_with_url = item["title"] + " " + item["url"]
                    meeting_date = _parse_meeting_date(title_with_url)
                    meeting_date_raw = None
                    if meeting_date:
                        fixed = correct_future_date(meeting_date, url_year=_year_from_url(item["url"]))
                        if fixed:
                            logger.warning(f"{self.source_name}: future date {meeting_date} in {item['url']} → {fixed}")
                            meeting_date_raw, meeting_date = meeting_date, fixed
                    if meeting_date:
                        d = datetime.strptime(meeting_date, "%Y-%m-%d").date()
                        if d < self.cutoff:
                            continue
                    else:
                        # Filename has no year (Harbor's "M.D" naming inside a
                        # /YYYY Recordings/ folder). Fall back to the URL path.
                        url_year = _year_from_url(item["url"])
                        if url_year is not None and url_year < self.cutoff.year - 1:
                            continue
                        if url_year is None:
                            # No year anywhere — refuse to ingest rather than
                            # silently keep undated audio.
                            continue
                    body_docs.append({
                        **item,
                        "doc_type": body["doc_type"],
                        "category": self.category,
                        "recording": {
                            "platform": "audio",
                            "meeting_body": body["name"],
                            "meeting_date": meeting_date,
                            **({"meeting_date_raw": meeting_date_raw} if meeting_date_raw else {}),
                        },
                    })

            if body_docs:
                logger.info(f"  {self.source_name} — {body['name']}: {len(body_docs)} files")
                if self.progress_callback:
                    self.progress_callback(len(body_docs))
                all_docs.extend(body_docs)

        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        pass


_YOUTUBE_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/watch\?v=|youtube\.com/embed/)([A-Za-z0-9_-]{11})"
)


class YouTubeLinksCrawler:
    """Crawler for a Board Meeting Recordings page that links to YouTube.

    The page is a flat list of <a href="https://youtu.be/<id>">Month Day, Year
    Board of Education Meeting</a> entries. We extract the YouTube video ID
    and the meeting date from the anchor text; no download is performed —
    transcripts come from YouTube's auto-captions and the player is embedded
    in the UI."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        self.category = _source_category(source_name)
        self.meeting_body = self.config.get("meeting_body") or "Board of Education"
        self.name_prefix = self.config.get("name_prefix") or self.meeting_body
        self.basic = BasicScraper()
        self.progress_callback = None
        self.cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).date()

    def find_documents(self) -> list[dict]:
        all_docs: list[dict] = []
        seen_ids: set[str] = set()
        for path in self.config["pages_to_crawl"]:
            url = self.config["base_url"] + path
            try:
                soup = self.basic.fetch_page(url)
            except Exception as e:
                logger.warning(f"{self.source_name} page failed: {e}")
                continue
            if not soup:
                continue

            for link in soup.find_all("a", href=True):
                m = _YOUTUBE_ID_RE.search(link["href"])
                if not m:
                    continue
                yt_id = m.group(1)
                if yt_id in seen_ids:
                    continue
                seen_ids.add(yt_id)

                anchor_text = link.get_text(strip=True) or f"{self.name_prefix} Meeting {yt_id}"
                meeting_date = _parse_meeting_date(anchor_text)
                meeting_date_raw = None
                if meeting_date:
                    fixed = correct_future_date(meeting_date)
                    if fixed:
                        logger.warning(f"{self.source_name}: future date {meeting_date} in '{anchor_text}' → {fixed}")
                        meeting_date_raw, meeting_date = meeting_date, fixed
                if meeting_date:
                    d = datetime.strptime(meeting_date, "%Y-%m-%d").date()
                    if d < self.cutoff:
                        continue

                # Use a stable synthetic URL so dedup against existing rows works.
                synthetic_url = f"https://www.youtube.com/watch?v={yt_id}"
                all_docs.append({
                    "url": synthetic_url,
                    "title": anchor_text,
                    "source_page": url,
                    "doc_type": self.config["doc_type"],
                    "category": self.category,
                    "name_prefix": self.name_prefix,
                    "recording": {
                        "platform": "youtube",
                        "meeting_body": self.meeting_body,
                        "meeting_date": meeting_date,
                        **({"meeting_date_raw": meeting_date_raw} if meeting_date_raw else {}),
                        "youtube_id": yt_id,
                    },
                })

        if all_docs:
            logger.info(f"  {self.source_name}: {len(all_docs)} YouTube videos")
            if self.progress_callback:
                self.progress_callback(len(all_docs))
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        pass


class CensusCrawler:
    """Fetches Census ACS data via API and saves as a JSON document."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)

    def find_documents(self) -> list[dict]:
        api_config = self.config.get("api_config", {})
        if not api_config:
            return []

        census = getattr(TOWN, "census", None) or {}
        variables = api_config.get("variables", [])
        state = api_config.get("state_fips") or census.get("state_fips")
        place = api_config.get("place_fips") or census.get("place_fips")
        if not (state and place):
            logger.warning("Census: no state_fips/place_fips in the source or the profile")
            return []

        try:
            import requests, json
            var_str = ",".join(["NAME"] + variables)
            url = f"https://api.census.gov/data/2022/acs/acs5?get={var_str}&for=place:{place}&in=state:{state}"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                # Save as a synthetic document
                from pathlib import Path
                out_dir = Path(__file__).parent.parent.parent / "storage" / "census"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{entity_for_source(self.source_name)}_acs_2022.json"
                with open(out_file, "w") as f:
                    json.dump({"source": "Census ACS 5-Year 2022", "raw": data, "variables": variables}, f, indent=2)
                logger.info(f"  Census: saved ACS data to {out_file}")
                return [{
                    "url": str(out_file),
                    "title": f"{TOWN.name} Census ACS 2022 Demographics",
                    "source_page": url,
                    "category": "census",
                }]
        except Exception as e:
            logger.warning(f"Census API failed: {e}")
        return []

    def _cleanup(self):
        pass


class EdlioCrawler:
    """Crawler for an Edlio-hosted school district site (/apps/pages/...),
    plus its member schools' subdomains (school_sites, school_pages)."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.config = _source_config(source_name)
        # Stay on the district's domain and its school subdomains.
        host = urlparse(self.config["base_url"]).netloc.lower()
        self.domain = host[4:] if host.startswith("www.") else host
        self.basic = BasicScraper()
        self.selenium = None

    def _get_scraper(self):
        if self.selenium is None:
            try:
                self.selenium = SeleniumScraper()
                self.selenium._ensure_driver()
            except Exception:
                logger.warning(f"Selenium not available for {self.source_name} — using basic scraper")
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
        cb = getattr(self, "progress_callback", None)

        # Seed with: main domain root + explicit pages_to_crawl + school_sites + school_pages
        # The explicit pages_to_crawl entries (BOE 25-26, 24-25, archive, budget, etc.) are
        # high-PDF-yield landing pages that must be hit even if depth-bounded discovery misses them.
        seed_urls: list[str] = []
        seed_urls.append(self.config["base_url"] + "/")
        for path in self.config.get("pages_to_crawl", []):
            if path.startswith("http"):
                seed_urls.append(path)
            elif path == "/":
                continue
            else:
                seed_urls.append(self.config["base_url"] + path)
        for school_url in self.config.get("school_sites", []):
            seed_urls.append(school_url)
        for sp in self.config.get("school_pages", []):
            seed_urls.append(sp)

        # Direct fetch of every seed first (single-level), then expand discovered subpages.
        to_crawl = list(dict.fromkeys(seed_urls))
        depth = 0
        max_depth = 2
        max_pages = 200

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
                    if cb:
                        cb(len(docs))

                subpages = self.basic.find_subpage_links(soup, url, same_domain=False)
                for subpage in subpages:
                    if subpage not in visited and self._is_crawlable(subpage):
                        host = urlparse(subpage).netloc
                        if self.domain in host:
                            next_round.append(subpage)

            to_crawl = next_round
            depth += 1
            logger.info(f"  Depth {depth}: discovered {len(next_round)} more pages to crawl")

        self._cleanup()
        return _deduplicate_docs(all_docs)

    def _cleanup(self):
        if self.selenium and self.selenium is not False:
            self.selenium.close()


# `crawler` values a source in sources.json can name. Sources without one get
# the generic two-level site crawl.
CRAWLERS = {
    "site": SiteCrawler,
    "pages": PagesCrawler,
    "ecode360": ECode360Crawler,
    "edlio": EdlioCrawler,
    "municode_meetings": MunicodeMeetingsCrawler,
    "opramachine": OPRACrawler,
    "census": CensusCrawler,
    "folder_recordings": FolderRecordingsCrawler,
    "youtube_links": YouTubeLinksCrawler,
}
DEFAULT_CRAWLER = "site"
