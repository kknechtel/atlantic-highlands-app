"""
Configuration for Atlantic Highlands Town Repository Scraper.
Adapted for S3 storage (no Box dependency).
"""

# ─── Website sources ────────────────────────────────────────────────
SOURCES = {
    "ahnj": {
        "base_url": "https://www.ahnj.com",
        "description": "Borough of Atlantic Highlands Official Site",
        "pages_to_crawl": [
            "/ahnj/Government",
            "/ahnj/Departments",
            "/ahnj/Community",
            "/ahnj/Court",
            "/ahnj/Emergency",
            "/ahnj/Meetings%20and%20Agendas/",
            "/ahnj/Events/",
            "/ahnj/Recreation/",
            "/ahnj/Departments/Building%20Department/",
            "/ahnj/Departments/Affordable%20Housing/",
        ],
    },
    "ecode360": {
        "base_url": "https://ecode360.com",
        "description": "Atlantic Highlands Document Repository (Agendas, Minutes, Codes)",
        "pages_to_crawl": [
            "/AT0153/documents/Agendas",
            "/AT0153/documents/Minutes",
            "/AT0153",
        ],
    },
    "tridistrict": {
        "base_url": "https://www.tridistrict.org",
        "description": "Henry Hudson Regional School District (Tri-District)",
        "pages_to_crawl": [
            "/",
        ],
        "school_sites": [
            "https://ahes.tridistrict.org",
            "https://hes.tridistrict.org",
            "https://hhrs.tridistrict.org",
        ],
    },
}

# ─── File types to download ────────────────────────────────────────
DOWNLOAD_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv", ".txt", ".rtf",
    ".zip", ".png", ".jpg", ".jpeg",
}

# ─── Scraper settings ──────────────────────────────────────────────
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
