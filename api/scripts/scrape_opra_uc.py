"""
Scrape OPRAmachine using undetected-chromedriver to bypass Cloudflare.
Also scrape ecode360 documents while we have a Cloudflare-proof browser.
Run: python scripts/scrape_opra_uc.py
"""
import sys, re, json, time, uuid, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def get_driver():
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options, version_main=146)
    driver.set_page_load_timeout(30)
    return driver


def scrape_opramachine(driver):
    """Scrape OPRAmachine for Atlantic Highlands."""
    from bs4 import BeautifulSoup

    logger.info("=== OPRAmachine ===")
    results = []
    pdfs = []

    # Try the search page instead of direct body page
    urls_to_try = [
        "https://opramachine.com/body/atlantic_highlands",
        "https://opramachine.com/body/borough_of_atlantic_highlands",
        "https://opramachine.com/search/atlantic%20highlands",
    ]

    for url in urls_to_try:
        logger.info(f"  Trying: {url}")
        driver.get(url)
        time.sleep(8)

        title = driver.title
        logger.info(f"  Title: {title}")

        if "Attention Required" in title or "blocked" in driver.page_source.lower()[:500]:
            logger.info("  Still blocked, waiting 15s...")
            time.sleep(15)
            driver.get(url)
            time.sleep(10)
            title = driver.title
            logger.info(f"  Title after retry: {title}")

        if "Attention Required" in title:
            logger.info("  Cloudflare still blocking, trying next URL...")
            continue

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Find request links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "/request/" in href and text:
                full = href if href.startswith("http") else f"https://opramachine.com{href}"
                results.append({"title": text, "url": full})
            elif ".pdf" in href.lower():
                full = href if href.startswith("http") else f"https://opramachine.com{href}"
                pdfs.append({"title": text or "PDF", "url": full})

        if results:
            logger.info(f"  Found {len(results)} requests!")
            # Scrape first 20 request detail pages
            for req in results[:20]:
                try:
                    driver.get(req["url"])
                    time.sleep(4)
                    req_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # Get body text
                    body_div = req_soup.find("div", id="incoming-message-main") or req_soup.find("div", class_="correspondence")
                    if body_div:
                        req["body"] = body_div.get_text(strip=True)[:1000]

                    # Get status
                    status_el = req_soup.find("h1") or req_soup.find("div", class_="request-status")
                    if status_el:
                        req["status"] = status_el.get_text(strip=True)[:100]

                    # Get attached documents
                    for a in req_soup.find_all("a", href=True):
                        href = a["href"]
                        if ".pdf" in href.lower() or "/download/" in href or "attachment" in href:
                            full = href if href.startswith("http") else f"https://opramachine.com{href}"
                            pdfs.append({"title": a.get_text(strip=True) or "Attachment", "url": full, "request": req["title"]})

                    logger.info(f"    Got details for: {req['title'][:50]}")
                except Exception as e:
                    logger.warning(f"    Failed: {e}")

            break
        else:
            logger.info("  No requests found on this page")

    logger.info(f"OPRAmachine total: {len(results)} requests, {len(pdfs)} docs")
    return results, pdfs


def scrape_ecode360(driver):
    """Scrape ecode360 documents while we have a CF-proof browser."""
    from bs4 import BeautifulSoup

    logger.info("=== ecode360.com ===")
    categories = [
        "/AT0153/documents/Agendas",
        "/AT0153/documents/Minutes",
        "/AT0153/documents/Budgets",
        "/AT0153/documents/Resolutions",
        "/AT0153/documents/Legislation",
        "/AT0153/documents/Comprehensive_Plans",
        "/AT0153/documents/Misc._Documents",
    ]

    all_pdfs = []
    for cat_path in categories:
        url = f"https://ecode360.com{cat_path}"
        cat_name = cat_path.split("/")[-1].replace("_", " ")
        logger.info(f"  Crawling: {cat_name}")

        driver.get(url)
        time.sleep(8)

        title = driver.title
        if "moment" in title.lower() or "Attention" in title:
            logger.info("  Cloudflare challenge, waiting...")
            time.sleep(15)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        cat_pdfs = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                full = href if href.startswith("http") else f"https://ecode360.com{href}"
                text = a.get_text(strip=True)
                all_pdfs.append({"title": text, "url": full, "category": cat_name})
                cat_pdfs += 1

        # Check for subcategories/pagination
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ("category=" in href or "subCategory=" in href or "page=" in href) and "AT0153" in href:
                sub_url = href if href.startswith("http") else f"https://ecode360.com{href}"
                logger.info(f"    Following: {a.get_text(strip=True)[:30]}")
                driver.get(sub_url)
                time.sleep(5)
                sub_soup = BeautifulSoup(driver.page_source, "html.parser")
                for sub_a in sub_soup.find_all("a", href=True):
                    if ".pdf" in sub_a["href"].lower():
                        full = sub_a["href"] if sub_a["href"].startswith("http") else f"https://ecode360.com{sub_a['href']}"
                        all_pdfs.append({"title": sub_a.get_text(strip=True), "url": full, "category": cat_name})
                        cat_pdfs += 1

        logger.info(f"    {cat_name}: {cat_pdfs} PDFs")
        time.sleep(2)

    # Deduplicate
    seen = set()
    unique = []
    for p in all_pdfs:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)

    logger.info(f"ecode360 total: {len(unique)} unique PDFs")
    return unique


def save_and_download(opra_results, opra_pdfs, ecode_pdfs):
    """Save to JSON and download new PDFs to DB."""
    import requests
    from database import SessionLocal
    from models.document import Document, Project
    from models.user import User

    # Save JSON
    out_dir = Path(__file__).parent.parent / "storage" / "opra"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "opra_data.json", "w") as f:
        json.dump({"opra_requests": opra_results, "opra_docs": opra_pdfs, "ecode_pdfs": [p["url"] for p in ecode_pdfs]}, f, indent=2)

    db = SessionLocal()
    project = db.query(Project).filter(Project.name == "AH Scraped Documents").first()
    user = db.query(User).first()
    pid = str(project.id)
    existing = {fn.lower() for (fn,) in db.query(Document.filename).all()}
    H = {"User-Agent": "Mozilla/5.0"}

    # Download OPRA PDFs
    opra_dir = Path(__file__).parent.parent / "storage" / "scraped" / pid / "opra"
    opra_dir.mkdir(parents=True, exist_ok=True)
    opra_dl = 0
    for pdf in opra_pdfs:
        url = pdf.get("url", "")
        fn = re.sub(r'[^\w\-.]', '_', pdf.get("title", "")[:50]) + ".pdf"
        if fn.lower() in existing or len(fn) < 8:
            continue
        try:
            resp = requests.get(url, timeout=30, headers=H)
            if resp.status_code == 200 and len(resp.content) > 500:
                (opra_dir / fn).write_bytes(resp.content)
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
                opra_dl += 1
                existing.add(fn.lower())
        except:
            db.rollback()

    # Download ecode360 PDFs
    ecode_dir = Path(__file__).parent.parent / "storage" / "scraped" / pid / "ecode360"
    ecode_dir.mkdir(parents=True, exist_ok=True)
    ecode_dl = 0
    for pdf in ecode_pdfs:
        url = pdf.get("url", "")
        fn = requests.utils.unquote(url.split("/")[-1]).split("?")[0]
        if fn.lower() in existing or len(fn) < 5:
            continue
        try:
            resp = requests.get(url, timeout=30, headers=H)
            if resp.status_code == 200 and len(resp.content) > 500:
                (ecode_dir / fn).write_bytes(resp.content)
                # Guess doc type from category
                cat_map = {"Agendas": "agenda", "Minutes": "minutes", "Budgets": "budget",
                           "Resolutions": "resolution", "Legislation": "ordinance"}
                dtype = cat_map.get(pdf.get("category", ""), "general")
                doc = Document(
                    id=str(uuid.uuid4()), project_id=project.id,
                    filename=fn, original_filename=fn,
                    s3_key=f"scraped/{pid}/ecode360/{fn}",
                    s3_bucket="atlantic-highlands-documents",
                    file_size=len(resp.content), content_type="application/pdf",
                    doc_type=dtype, category="town", status="uploaded",
                    uploaded_by=user.id,
                )
                db.add(doc)
                db.commit()
                ecode_dl += 1
                existing.add(fn.lower())
        except:
            db.rollback()
        time.sleep(0.2)

    logger.info(f"Downloaded: {opra_dl} OPRA docs, {ecode_dl} ecode360 docs")
    total = db.query(Document).count()
    logger.info(f"Total docs in DB: {total}")
    db.close()
    return opra_dl, ecode_dl


if __name__ == "__main__":
    driver = None
    try:
        driver = get_driver()
        logger.info("undetected-chromedriver started")

        opra_results, opra_pdfs = scrape_opramachine(driver)
        ecode_pdfs = scrape_ecode360(driver)

        opra_dl, ecode_dl = save_and_download(opra_results, opra_pdfs, ecode_pdfs)

        print(f"\n=== Scrape Complete ===")
        print(f"OPRAmachine: {len(opra_results)} requests, {len(opra_pdfs)} docs ({opra_dl} downloaded)")
        print(f"ecode360: {len(ecode_pdfs)} PDFs ({ecode_dl} downloaded)")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
