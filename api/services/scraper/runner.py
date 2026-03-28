"""
Scraper runner - orchestrates crawling, downloading, and uploading to S3.
Creates Document records in the database for each file found.
"""
import logging
import uuid
import mimetypes
from datetime import datetime
from typing import Optional

from .crawlers import AHNJCrawler, ECode360Crawler, TriDistrictCrawler
from .scraper import BasicScraper
from .utils import categorize_url, url_to_filename, source_to_entity_type

logger = logging.getLogger("ah_scraper")

# Global state for tracking scraper progress
_scraper_status = {
    "running": False,
    "current_site": None,
    "documents_found": 0,
    "documents_uploaded": 0,
    "documents_skipped": 0,
    "errors": [],
    "started_at": None,
    "completed_at": None,
}


def get_scraper_status() -> dict:
    return dict(_scraper_status)


async def run_scraper(
    sites: list[str] | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
    dry_run: bool = False,
):
    """
    Main scraper entry point. Crawls sites, downloads files, uploads to S3,
    and creates Document records in the database.
    """
    from database import SessionLocal
    from models.document import Document, Project
    from services.s3_service import S3Service

    global _scraper_status
    _scraper_status = {
        "running": True,
        "current_site": None,
        "documents_found": 0,
        "documents_uploaded": 0,
        "documents_skipped": 0,
        "errors": [],
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    }

    db = SessionLocal()
    s3 = S3Service()
    downloader = BasicScraper()

    try:
        # Get or create project
        if project_id:
            project = db.query(Project).filter(Project.id == project_id).first()
        else:
            # Create a default scraper project
            project = db.query(Project).filter(Project.name == "AH Scraped Documents").first()
            if not project:
                project = Project(
                    name="AH Scraped Documents",
                    description="Documents automatically scraped from town and school websites",
                    entity_type="town",
                    created_by=user_id or str(uuid.uuid4()),
                )
                db.add(project)
                db.commit()
                db.refresh(project)

        # Get existing S3 keys to avoid re-uploading
        existing_keys = set()
        existing_docs = db.query(Document.s3_key).filter(Document.project_id == project.id).all()
        for (key,) in existing_docs:
            existing_keys.add(key)

        # Also track existing filenames for dedup
        existing_filenames = set()
        existing_fn_docs = db.query(Document.filename).filter(Document.project_id == project.id).all()
        for (fn,) in existing_fn_docs:
            existing_filenames.add(fn.lower())

        all_sites = sites or ["ahnj", "ecode", "tri"]
        all_uploaded = []

        # ── Crawl each site ───────────────────────────────────────
        crawlers = {
            "ahnj": ("ahnj.com", AHNJCrawler),
            "ecode": ("ecode360.com", ECode360Crawler),
            "tri": ("tridistrict.org", TriDistrictCrawler),
        }

        for site_key in all_sites:
            if site_key not in crawlers:
                continue

            site_name, CrawlerClass = crawlers[site_key]
            _scraper_status["current_site"] = site_name
            logger.info(f"\n--- Crawling: {site_name} ---")

            try:
                crawler = CrawlerClass()
                docs = crawler.find_documents()
                _scraper_status["documents_found"] += len(docs)
                logger.info(f"  Found {len(docs)} documents on {site_name}")

                if dry_run:
                    logger.info(f"  [DRY RUN] Would download {len(docs)} files")
                    continue

                # Download and upload each document
                for doc_info in docs:
                    try:
                        filename = url_to_filename(doc_info["url"])

                        # Skip if already in DB
                        if filename.lower() in existing_filenames:
                            _scraper_status["documents_skipped"] += 1
                            continue

                        # Download file content
                        content, fname = downloader.download_file_to_bytes(doc_info["url"])
                        if not content:
                            continue

                        # Determine S3 key
                        category = categorize_url(doc_info["url"])
                        entity_type = source_to_entity_type(crawler.source_name)
                        s3_key = f"scraped/{crawler.source_name}/{category}/{filename}"

                        if s3_key in existing_keys:
                            _scraper_status["documents_skipped"] += 1
                            continue

                        # Upload to S3
                        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                        s3.upload_file(content, s3_key, content_type)

                        # Create database record
                        doc_record = Document(
                            project_id=project.id,
                            filename=filename,
                            original_filename=filename,
                            s3_key=s3_key,
                            s3_bucket=s3.bucket,
                            file_size=len(content),
                            content_type=content_type,
                            doc_type=category,
                            category=entity_type,
                            uploaded_by=user_id or project.created_by,
                            metadata_={
                                "source_url": doc_info["url"],
                                "source_page": doc_info.get("source_page"),
                                "source_site": crawler.source_name,
                                "title": doc_info.get("title"),
                                "scraped_at": datetime.utcnow().isoformat(),
                            },
                        )
                        db.add(doc_record)
                        existing_filenames.add(filename.lower())
                        existing_keys.add(s3_key)
                        _scraper_status["documents_uploaded"] += 1
                        all_uploaded.append({
                            "filename": filename,
                            "source": crawler.source_name,
                            "category": category,
                            "url": doc_info["url"],
                        })

                    except Exception as e:
                        err = f"Error processing {doc_info.get('url', '?')}: {e}"
                        logger.error(err)
                        _scraper_status["errors"].append(err)

                # Commit after each site
                db.commit()

            except Exception as e:
                err = f"Error crawling {site_name}: {e}"
                logger.error(err, exc_info=True)
                _scraper_status["errors"].append(err)

        _scraper_status["current_site"] = None
        _scraper_status["running"] = False
        _scraper_status["completed_at"] = datetime.utcnow().isoformat()

        logger.info(f"\nScraper complete: {_scraper_status['documents_uploaded']} uploaded, "
                     f"{_scraper_status['documents_skipped']} skipped, "
                     f"{len(_scraper_status['errors'])} errors")

        return all_uploaded

    except Exception as e:
        logger.error(f"Scraper failed: {e}", exc_info=True)
        _scraper_status["running"] = False
        _scraper_status["errors"].append(str(e))
        raise
    finally:
        db.close()
