"""
Utility functions for the scraper.
Handles dedup tracking, URL categorization, naming, and filename generation.
"""
import os
import re
import hashlib
import logging
from urllib.parse import urlparse, unquote

logger = logging.getLogger("ah_scraper")


def url_to_filename(url: str) -> str:
    """Convert a URL to a safe filename, preserving the original file extension."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = os.path.basename(path)

    if not filename:
        segments = [s for s in path.split("/") if s]
        filename = segments[-1] if segments else hashlib.md5(url.encode()).hexdigest()

    # Clean up the filename
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_()")
    cleaned = ""
    for ch in filename:
        cleaned += ch if ch in safe_chars else "_"

    return cleaned[:200]


def url_to_descriptive_name(url: str, source_page: str = "", title: str = "") -> str:
    """
    Generate a descriptive filename from the URL path tree.
    e.g. https://www.ahnj.com/ahnj/Government/Employees/2024%20Holiday%20Closures.pdf
    -> Government - Employees - 2024 Holiday Closures.pdf
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)
    segments = [s for s in path.split("/") if s]

    if not segments:
        return url_to_filename(url)

    # Get the actual filename (last segment)
    filename = segments[-1]
    ext = ""
    for e in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".txt", ".zip", ".png", ".jpg", ".jpeg"]:
        if filename.lower().endswith(e):
            ext = e
            filename = filename[: -len(e)]
            break

    # Build descriptive prefix from path segments (skip domain-specific prefixes)
    skip_segments = {"ahnj", "at0153", "documents", "apps", "pages", "index.jsp", "www.ahnj.com", "ecode360.com"}
    path_parts = []
    for seg in segments[:-1]:  # exclude filename
        clean = seg.strip()
        if clean.lower() in skip_segments:
            continue
        # Clean up URL encoding artifacts
        clean = clean.replace("%20", " ").replace("+", " ").replace("_", " ")
        if clean and len(clean) > 1:
            path_parts.append(clean)

    # Clean up filename
    clean_name = filename.replace("%20", " ").replace("_", " ").replace("+", " ").strip()

    # If we have path context, prefix it
    if path_parts:
        prefix = " - ".join(path_parts[:3])  # max 3 levels
        result = f"{prefix} - {clean_name}{ext}"
    else:
        result = f"{clean_name}{ext}"

    # If the title provides better info and filename is generic
    if title and len(title) > 5 and title.lower() not in ["download", "click here", "link"]:
        # Use title if filename is just a hash or ID
        if re.match(r'^[a-f0-9]{8,}$', clean_name.replace(" ", "").replace("-", "")):
            result = f"{_safe_filename(title)}{ext}"

    return _safe_filename(result)[:250]


def _safe_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    # Remove characters that aren't safe in filenames
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Collapse multiple spaces/underscores
    safe = re.sub(r'[_\s]+', ' ', safe).strip()
    return safe


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


def detect_doc_type_from_name(filename: str) -> str:
    """Detect document type from a descriptive filename."""
    lower = filename.lower()
    if "agenda" in lower:
        return "agenda"
    if "minute" in lower:
        return "minutes"
    if "budget" in lower:
        return "budget"
    if "audit" in lower or "amr" in lower:
        return "audit"
    if any(kw in lower for kw in ["financial statement", "comprehensive financial", " fs", "cafr"]):
        return "financial_statement"
    if "resolution" in lower:
        return "resolution"
    if "ordinance" in lower or "code" in lower:
        return "ordinance"
    if "performance report" in lower:
        return "performance_report"
    if any(kw in lower for kw in ["civil case", "olszewski", "reply brief", "motion", "order"]):
        return "legal"
    if "opra" in lower or "ferpa" in lower:
        return "records_request"
    if "presentation" in lower or lower.endswith(".pptx"):
        return "presentation"
    if any(kw in lower for kw in ["election", "ballot", "vote"]):
        return "election"
    if "plan" in lower or "strategic" in lower:
        return "planning"
    return "general"


def detect_fiscal_year(filename: str) -> str | None:
    """Extract a fiscal year from a filename."""
    # Match patterns like 2024-2025, 2024-25, 2024
    m = re.search(r'(20\d{2})[-/](20\d{2}|\d{2})', filename)
    if m:
        return m.group(0)
    m = re.search(r'(20\d{2})', filename)
    if m:
        return m.group(1)
    return None
