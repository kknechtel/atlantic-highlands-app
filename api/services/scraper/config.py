"""
Scraper configuration. What to crawl comes from the deployment's municipality
profile (municipalities/<slug>/sources.json, see municipality.py); this file
holds the crawl mechanics that are the same for every town.
"""
from municipality import sources as _sources

# ─── Website sources ────────────────────────────────────────────────
# Each source: base_url, description, entity (the government that publishes
# it), and any of pages_to_crawl / historical_pages / direct_downloads /
# school_sites / school_pages / api_url / api_config.
SOURCES = _sources().get("documents", {})

# ─── File types to download ────────────────────────────────────────
DOWNLOAD_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv", ".txt", ".rtf",
}

# Skip these - too large or not useful as documents
SKIP_EXTENSIONS = {
    ".wav", ".wma", ".mp3", ".mp4", ".avi", ".mov", ".wmv",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico",
}

# Meeting recording audio/video — the *recordings* crawlers explicitly look for
# these (the general document crawlers still skip them via SKIP_EXTENSIONS).
RECORDING_EXTENSIONS = {
    ".wma", ".wav", ".m4a", ".mp3", ".mp4", ".mov", ".dcr",
}

# ─── Meeting-recording sources ─────────────────────────────────────
# Last-12-months filter is applied by the crawler at scrape time so we don't
# pull every back-year on every run. Set RECORDINGS_BACKFILL=full to disable.
RECORDING_SOURCES = _sources().get("recordings", {})

# ─── Scraper settings ──────────────────────────────────────────────
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
