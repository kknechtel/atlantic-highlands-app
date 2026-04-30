"""Deep scrape all remaining document sources for Atlantic Highlands."""
import sys, os, requests, re, time, uuid
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import SessionLocal
from models.document import Document, Project
from models.user import User

BASE = "https://www.ahnj.com"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SKIP_EXT = {".wav", ".wma", ".mp3", ".mp4", ".mov", ".avi", ".wmv", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".rar"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"}

db = SessionLocal()
project = db.query(Project).filter(Project.name == "AH Scraped Documents").first()
user = db.query(User).first()
pid = str(project.id)
existing_fns = {fn.lower() for (fn,) in db.query(Document.filename).all()}
storage_base = Path("storage/scraped") / pid
print(f"Existing docs: {len(existing_fns)}", flush=True)


def crawl_and_download(label, pages, doc_type="general", category="town", subfolder="misc"):
    all_urls = set()
    visited = set()

    def crawl(url, depth=0):
        if url in visited or depth > 2:
            return
        visited.add(url)
        try:
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code != 200:
                return
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                lower = href.lower()
                if any(lower.endswith(ext) for ext in SKIP_EXT):
                    continue
                if any(lower.endswith(ext) for ext in DOC_EXT):
                    full = (href if href.startswith("http") else BASE + href).split("?")[0]
                    all_urls.add(full)
                elif depth < 2 and "/ahnj/" in href and "javascript" not in lower:
                    sub = href if href.startswith("http") else BASE + href
                    if sub not in visited and "ahnj.com" in sub:
                        time.sleep(0.3)
                        crawl(sub, depth + 1)
        except Exception:
            pass

    for page in pages:
        url = page if page.startswith("http") else BASE + page
        crawl(url)

    out_dir = storage_base / subfolder
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    for url in sorted(all_urls):
        fn = requests.utils.unquote(url.split("/")[-1])
        if fn.lower() in existing_fns or len(fn) < 5:
            continue
        try:
            resp = requests.get(url, headers=H, timeout=30)
            if resp.status_code != 200 or len(resp.content) < 500:
                continue
            (out_dir / fn).write_bytes(resp.content)
            doc = Document(
                id=str(uuid.uuid4()), project_id=project.id,
                filename=fn, original_filename=fn,
                s3_key=f"scraped/{pid}/{subfolder}/{fn}",
                s3_bucket="atlantic-highlands-documents",
                file_size=len(resp.content), content_type="application/pdf",
                doc_type=doc_type, category=category, status="uploaded",
                uploaded_by=user.id,
            )
            db.add(doc)
            db.commit()
            downloaded += 1
            existing_fns.add(fn.lower())
        except Exception:
            db.rollback()
        time.sleep(0.2)

    print(f"  {label}: found {len(all_urls)}, downloaded {downloaded} new", flush=True)
    return downloaded


total = 0

# 1. Council Agendas Archives
print("=== Council Agendas 2015-2025 ===", flush=True)
pages = [f"/ahnj/Agendas/Archives/{y}/" for y in range(2015, 2026)]
pages += ["/ahnj/Agendas/", "/ahnj/Meetings%20and%20Agendas/"]
total += crawl_and_download("Council Agendas", pages, "agenda", "town", "council_agendas")

# 2. Budget & Finance
print("=== Budget & Finance ===", flush=True)
total += crawl_and_download("Budget/Finance", [
    "/ahnj/Government/Budget%20Information/",
    "/ahnj/Departments/Finance%20Department/",
    "/ahnj/Departments/Tax%20Assessor/",
    "/ahnj/Departments/Tax%20Collector/",
], "budget", "town", "finance")

# 3. Ordinances
print("=== Ordinances ===", flush=True)
total += crawl_and_download("Ordinances", [
    "/ahnj/Government/Borough%20Ordinances/",
    "/ahnj/Government/Government%20Records/",
    "/ahnj/Government/Government%20Records/Most%20Referenced%20Ordinances/",
], "ordinance", "town", "ordinances")

# 4. Departments
print("=== Departments ===", flush=True)
total += crawl_and_download("Departments", [
    "/ahnj/Departments/Building%20Department/",
    "/ahnj/Departments/Affordable%20Housing/",
    "/ahnj/Departments/Zoning%20Office/",
    "/ahnj/Departments/Police%20Department/",
    "/ahnj/Departments/Fire%20Department/",
    "/ahnj/Departments/Public%20Works/",
    "/ahnj/Departments/Code%20Enforcement/",
    "/ahnj/Departments/Stormwater%20Management/",
    "/ahnj/Departments/Environmental%20Commission/",
    "/ahnj/Departments/Municipal%20Clerk/",
    "/ahnj/Departments/Business%20Administrator/",
    "/ahnj/Community/",
    "/ahnj/Court/",
    "/ahnj/Emergency/",
    "/ahnj/Forms/",
    "/ahnj/Other%20Links/BIDS%20and%20RFPs/",
    "/ahnj/Announcements/",
    "/ahnj/Recreation/",
], "general", "town", "departments")

# 5. NJ State direct downloads
print("=== NJ State Downloads ===", flush=True)
nj_urls = {
    "NJ_ACFR_AH_School_2015.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/15/0130.pdf",
    "NJ_ACFR_AH_School_2016.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/16/0130.pdf",
    "NJ_ACFR_AH_School_2017.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/17/0130.pdf",
    "NJ_ACFR_AH_School_2018.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/18/0130.pdf",
    "NJ_ACFR_AH_School_2019.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/19/0130.pdf",
    "NJ_ACFR_AH_School_2020.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/20/0130.pdf",
    "NJ_ACFR_AH_School_2021.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/21/0130.pdf",
    "NJ_ACFR_AH_School_2022.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/22/0130.pdf",
    "NJ_ACFR_AH_School_2023.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/23/0130.pdf",
    "NJ_ACFR_AH_School_2024.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/24/0130.pdf",
    "NJ_ACFR_HH_Regional_2015.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/15/2120.pdf",
    "NJ_ACFR_HH_Regional_2016.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/16/2120.pdf",
    "NJ_ACFR_HH_Regional_2017.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/17/2120.pdf",
    "NJ_ACFR_HH_Regional_2018.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/18/2120.pdf",
    "NJ_ACFR_HH_Regional_2019.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/19/2120.pdf",
    "NJ_ACFR_HH_Regional_2020.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/20/2120.pdf",
    "NJ_ACFR_HH_Regional_2021.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/21/2120.pdf",
    "NJ_ACFR_HH_Regional_2022.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/22/2120.pdf",
    "NJ_ACFR_HH_Regional_2023.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/23/2120.pdf",
    "NJ_ACFR_HH_Regional_2024.pdf": "https://www.nj.gov/education/finance/fp/acfr/search/24/2120.pdf",
    "Sea_Bright_Appellate_Division_Opinion.pdf": "https://www.njcourts.gov/system/files/court-opinions/2024/a0716-23.pdf",
    "Sea_Bright_Supreme_Court_Opinion.pdf": "https://www.njcourts.gov/system/files/court-opinions/2025/a_68_24.pdf",
    "AH_Community_Letter_SeaBright.pdf": "https://www.ahnj.com/ahnj/Announcements/LettertoCommnity-SeaBrightDecision.pdf",
    "Highlands_Letter_Regionalization.pdf": "https://highlandsnj.gov/wp-content/uploads/2024/12/Public-Letter-on-Regionalization.pdf",
    "Sea_Bright_Amended_Petition_Decision.pdf": "https://highlandsnj.gov/wp-content/uploads/2025/06/Decision-on-Sea-Bright-Amended-Petition-June-2025-2.pdf",
}

out_dir = storage_base / "nj_state"
out_dir.mkdir(parents=True, exist_ok=True)
nj_dl = 0
for fn, url in nj_urls.items():
    if fn.lower() in existing_fns:
        continue
    try:
        resp = requests.get(url, headers=H, timeout=30, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            (out_dir / fn).write_bytes(resp.content)
            dtype = "financial_statement" if "ACFR" in fn else "legal"
            cat = "school" if "School" in fn or "Regional" in fn else "town"
            doc = Document(
                id=str(uuid.uuid4()), project_id=project.id,
                filename=fn, original_filename=fn,
                s3_key=f"scraped/{pid}/nj_state/{fn}",
                s3_bucket="atlantic-highlands-documents",
                file_size=len(resp.content), content_type="application/pdf",
                doc_type=dtype, category=cat, status="uploaded",
                uploaded_by=user.id,
            )
            db.add(doc)
            db.commit()
            nj_dl += 1
            existing_fns.add(fn.lower())
    except Exception:
        db.rollback()
    time.sleep(0.5)

print(f"  NJ State: downloaded {nj_dl} new", flush=True)
total += nj_dl

# 6. Tridistrict BOE
print("=== Tridistrict BOE ===", flush=True)
tri_pages = [
    "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2593279",
    "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2593280",
]
tri_dl = 0
for page in tri_pages:
    try:
        r = requests.get(page, headers=H, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                full = href if href.startswith("http") else "https://www.tridistrict.org" + href
                fn = requests.utils.unquote(full.split("/")[-1]).split("?")[0]
                if fn.lower() in existing_fns or len(fn) < 5:
                    continue
                try:
                    resp = requests.get(full, headers=H, timeout=30)
                    if resp.status_code == 200 and len(resp.content) > 500:
                        tri_dir = storage_base / "tridistrict"
                        tri_dir.mkdir(parents=True, exist_ok=True)
                        (tri_dir / fn).write_bytes(resp.content)
                        doc = Document(
                            id=str(uuid.uuid4()), project_id=project.id,
                            filename=fn, original_filename=fn,
                            s3_key=f"scraped/{pid}/tridistrict/{fn}",
                            s3_bucket="atlantic-highlands-documents",
                            file_size=len(resp.content), content_type="application/pdf",
                            doc_type="minutes", category="school", status="uploaded",
                            uploaded_by=user.id,
                        )
                        db.add(doc)
                        db.commit()
                        tri_dl += 1
                        existing_fns.add(fn.lower())
                except Exception:
                    db.rollback()
                time.sleep(0.3)
    except Exception:
        pass

print(f"  Tridistrict: downloaded {tri_dl} new", flush=True)
total += tri_dl

print(f"\n=== TOTAL: {total} new documents downloaded ===", flush=True)
final_count = db.query(Document).count()
print(f"Total docs in DB: {final_count}", flush=True)
db.close()
