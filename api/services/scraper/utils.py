"""
Utility functions for the scraper.
Handles dedup tracking, URL categorization, and filename generation.
"""
import os
import hashlib
import logging
from urllib.parse import urlparse, unquote

logger = logging.getLogger("ah_scraper")


def url_to_filename(url: str) -> str:
    """Convert a URL to a safe filename."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = os.path.basename(path)

    if not filename:
        segments = [s for s in path.split("/") if s]
        filename = segments[-1] if segments else hashlib.md5(url.encode()).hexdigest()

    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_()")
    cleaned = ""
    for ch in filename:
        cleaned += ch if ch in safe_chars else "_"

    return cleaned[:200]


def categorize_url(url: str) -> str:
    """Categorize a document URL into a subfolder/doc_type name."""
    url_lower = url.lower()

    categories = {
        "agendas": ["agenda"],
        "minutes": ["minute"],
        "budgets": ["budget", "financial", "audit", "cafr"],
        "ordinances": ["ordinance", "code"],
        "resolutions": ["resolution"],
        "policies": ["polic"],
        "strategic_planning": ["strategic", "plan"],
        "board_docs": ["board"],
        "general": [],
    }

    for category, keywords in categories.items():
        if any(kw in url_lower for kw in keywords):
            return category

    return "general"


def source_to_entity_type(source_name: str) -> str:
    """Map scraper source name to entity type."""
    if source_name == "tridistrict":
        return "school"
    return "town"
