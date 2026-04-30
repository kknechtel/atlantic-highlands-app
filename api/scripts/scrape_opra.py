"""
Scrape OPRA requests from GovPilot and OPRAmachine using Selenium.
Run: python scripts/scrape_opra.py
"""
import sys, os, re, json, time, uuid, logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def get_driver():
    """Create stealth Chrome driver."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    # Not headless — needed for Cloudflare
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })
    driver.set_page_load_timeout(30)
    return driver


def scrape_govpilot(driver):
    """Scrape GovPilot OPRA portal for Atlantic Highlands."""
    logger.info("=== Scraping GovPilot OPRA Portal ===")
    url = "https://main.govpilot.com/web/public/2b3162a4-a0f_OPRA-ahadmin?uid=6865&ust=NJ&pu=1&id=1"

    driver.get(url)
    time.sleep(8)

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")
    title = driver.title
    logger.info(f"  Page title: {title}")
    logger.info(f"  Page size: {len(driver.page_source)}")

    results = []

    # GovPilot may show a list of public OPRA requests or just a submission form
    # Look for any request listings, tables, or document links
    tables = soup.find_all("table")
    logger.info(f"  Found {len(tables)} tables")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:  # Skip header
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                text = " | ".join(c.get_text(strip=True) for c in cells)
                results.append({
                    "source": "govpilot",
                    "text": text,
                    "url": url,
                })

    # Also look for any PDF/document links
    pdfs = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower() or "download" in href.lower() or "document" in href.lower():
            pdfs.append({
                "title": a.get_text(strip=True),
                "url": href if href.startswith("http") else f"https://main.govpilot.com{href}",
            })

    # Look for React/JS rendered content
    divs = soup.find_all("div", class_=True)
    request_divs = [d for d in divs if any(
        c in " ".join(d.get("class", [])).lower()
        for c in ["request", "record", "list", "item", "card", "row"]
    )]
    logger.info(f"  Found {len(request_divs)} potential request divs")

    for div in request_divs[:20]:
        text = div.get_text(strip=True)[:200]
        if text and len(text) > 10:
            results.append({
                "source": "govpilot",
                "text": text,
                "url": url,
            })

    # Try scrolling to load more content
    from selenium.webdriver.common.by import By
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        # Check for "load more" or pagination buttons
        buttons = driver.find_elements(By.CSS_SELECTOR, "button, a.page-link, a.next, .pagination a")
        for btn in buttons:
            text = btn.text.lower()
            if "next" in text or "more" in text or "load" in text:
                logger.info(f"  Found pagination: {btn.text}")
                try:
                    btn.click()
                    time.sleep(3)
                except:
                    pass
    except:
        pass

    logger.info(f"  GovPilot: {len(results)} request entries, {len(pdfs)} documents")
    return results, pdfs


def scrape_opramachine(driver):
    """Scrape OPRAmachine for Atlantic Highlands OPRA requests."""
    logger.info("=== Scraping OPRAmachine ===")

    results = []
    pdfs = []

    # Try multiple possible slugs
    slugs = [
        "atlantic_highlands",
        "borough_of_atlantic_highlands",
        "atlantic-highlands",
        "borough-of-atlantic-highlands",
    ]

    from bs4 import BeautifulSoup

    for slug in slugs:
        url = f"https://opramachine.com/body/{slug}"
        logger.info(f"  Trying: {url}")

        driver.get(url)
        time.sleep(10)

        title = driver.title
        if "Attention Required" in title or "moment" in title.lower():
            logger.info("  Cloudflare challenge detected, waiting...")
            time.sleep(20)
            # Refresh after waiting
            driver.get(url)
            time.sleep(10)

        if "404" in driver.title or "Not Found" in driver.page_source:
            logger.info(f"  {slug}: not found, trying next...")
            continue

        soup = BeautifulSoup(driver.page_source, "html.parser")
        page_text = soup.get_text()[:500]
        logger.info(f"  Page title: {driver.title}")
        logger.info(f"  Preview: {page_text[:100]}")

        # Find OPRA request links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "/request/" in href:
                full_url = href if href.startswith("http") else f"https://opramachine.com{href}"
                results.append({
                    "source": "opramachine",
                    "title": text,
                    "url": full_url,
                    "slug": slug,
                })
            elif ".pdf" in href.lower():
                full_url = href if href.startswith("http") else f"https://opramachine.com{href}"
                pdfs.append({
                    "title": text,
                    "url": full_url,
                })

        if results:
            logger.info(f"  Found {len(results)} requests on {slug}")

            # Try to get details from each request page (first 10)
            for req in results[:10]:
                try:
                    driver.get(req["url"])
                    time.sleep(5)
                    req_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # Get request details
                    body = req_soup.find("div", class_="request_body") or req_soup.find("div", id="request_body")
                    if body:
                        req["body"] = body.get_text(strip=True)[:500]

                    # Get status
                    status = req_soup.find("span", class_="status") or req_soup.find("div", class_="status")
                    if status:
                        req["status"] = status.get_text(strip=True)

                    # Get any attached documents
                    for a in req_soup.find_all("a", href=True):
                        if ".pdf" in a["href"].lower() or "attachment" in a["href"].lower():
                            pdfs.append({
                                "title": a.get_text(strip=True),
                                "url": a["href"] if a["href"].startswith("http") else f"https://opramachine.com{a['href']}",
                                "request": req.get("title", ""),
                            })
                except Exception as e:
                    logger.warning(f"  Failed to get details for {req['url']}: {e}")

            break  # Found the right slug

    logger.info(f"  OPRAmachine: {len(results)} requests, {len(pdfs)} documents")
    return results, pdfs


def save_results(govpilot_results, govpilot_pdfs, opra_results, opra_pdfs):
    """Save results to DB and JSON."""
    out_dir = Path(__file__).parent.parent / "storage" / "opra"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    all_data = {
        "scraped_at": datetime.now().isoformat(),
        "govpilot": {
            "requests": govpilot_results,
            "documents": govpilot_pdfs,
        },
        "opramachine": {
            "requests": opra_results,
            "documents": opra_pdfs,
        },
    }

    with open(out_dir / "opra_data.json", "w") as f:
        json.dump(all_data, f, indent=2)
    logger.info(f"Saved to {out_dir / 'opra_data.json'}")

    # Save to DB as documents (download PDFs)
    import requests as req_lib
    from database import SessionLocal
    from models.document import Document, Project
    from models.user import User

    db = SessionLocal()
    project = db.query(Project).filter(Project.name == "AH Scraped Documents").first()
    user = db.query(User).first()
    pid = str(project.id)
    existing_fns = {fn.lower() for (fn,) in db.query(Document.filename).all()}

    downloaded = 0
    all_pdfs = govpilot_pdfs + opra_pdfs
    for pdf_info in all_pdfs:
        url = pdf_info.get("url", "")
        title = pdf_info.get("title", "")
        fn = url.split("/")[-1].split("?")[0]
        if not fn or fn.lower() in existing_fns or len(fn) < 5:
            fn = re.sub(r'[^\w\-.]', '_', title)[:60] + ".pdf" if title else None
            if not fn or fn.lower() in existing_fns:
                continue

        try:
            resp = req_lib.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and len(resp.content) > 500:
                (out_dir / fn).write_bytes(resp.content)
                doc = Document(
                    id=str(uuid.uuid4()), project_id=project.id,
                    filename=fn, original_filename=fn,
                    s3_key=f"scraped/{pid}/opra/{fn}",
                    s3_bucket="atlantic-highlands-documents",
                    file_size=len(resp.content), content_type="application/pdf",
                    doc_type="records_request", category="town", status="uploaded",
                    uploaded_by=user.id,
                )
                db.add(doc)
                db.commit()
                downloaded += 1
                existing_fns.add(fn.lower())
                logger.info(f"  Downloaded: {fn}")
        except Exception as e:
            db.rollback()
            logger.warning(f"  Failed to download {url}: {e}")

    logger.info(f"Downloaded {downloaded} OPRA documents to DB")
    db.close()


if __name__ == "__main__":
    driver = None
    try:
        driver = get_driver()
        logger.info("Chrome driver started")

        gp_results, gp_pdfs = scrape_govpilot(driver)
        opra_results, opra_pdfs = scrape_opramachine(driver)

        save_results(gp_results, gp_pdfs, opra_results, opra_pdfs)

        total_requests = len(gp_results) + len(opra_results)
        total_docs = len(gp_pdfs) + len(opra_pdfs)
        print(f"\n=== OPRA Scrape Complete ===")
        print(f"GovPilot: {len(gp_results)} requests, {len(gp_pdfs)} documents")
        print(f"OPRAmachine: {len(opra_results)} requests, {len(opra_pdfs)} documents")
        print(f"Total: {total_requests} requests, {total_docs} documents")

    except Exception as e:
        logger.error(f"Scrape failed: {e}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
