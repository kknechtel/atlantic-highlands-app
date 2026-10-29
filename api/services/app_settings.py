"""Admin-set configuration, read live.

A value saved on the admin Settings screen wins over the environment (and
AWS Secrets Manager), so a deployment can be set up without shell access.
Values are Fernet-encrypted with a key derived from JWT_SECRET; changing
JWT_SECRET makes saved values unreadable, and they read as unset until an
admin enters them again.

Every process (API workers, the scraper) caches for CACHE_SECONDS, so a
saved key takes effect within that window everywhere.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import threading
import time

logger = logging.getLogger(__name__)

CACHE_SECONDS = 30

# What the Settings screen offers. secret=False values are shown in full.
SETTINGS = {
    "GEMINI_API_KEY": {
        "label": "Google Gemini API key",
        "help": "Document OCR, titles and summaries, search query expansion, reports. "
                "Get one at https://aistudio.google.com/apikey",
        "secret": True,
    },
    "ANTHROPIC_API_KEY": {
        "label": "Anthropic API key",
        "help": "Chat, presentations, meeting summaries, fact checks. "
                "Get one at https://console.anthropic.com/settings/keys",
        "secret": True,
    },
    "VOYAGE_API_KEY": {
        "label": "Voyage AI API key",
        "help": "Semantic search embeddings and reranking. Without it search falls back "
                "to keyword-only vectors. Get one at https://dash.voyageai.com",
        "secret": True,
    },
    "GOOGLE_OAUTH_CLIENT_ID": {
        "label": "Google Sign-In client ID",
        "help": "OAuth 2.0 Web client ID from Google Cloud Console. Blank disables "
                "Sign in with Google; password login still works.",
        "secret": False,
    },
    "CHAT_MODEL": {
        "label": "Chat model",
        "help": "Claude model for normal chat, e.g. claude-sonnet-4-6 (default), "
                "claude-sonnet-5-5 or claude-haiku-5-5 (cheapest).",
        "secret": False,
    },
    "CHAT_DEEP_MODEL": {
        "label": "Deep-thinking chat model",
        "help": "Model for the Deep toggle (only users allowed Deep mode). Default claude-opus-4-7.",
        "secret": False,
    },
    "CHAT_EFFORT": {
        "label": "Chat effort",
        "help": "Optional: low, medium or high. Lower is cheaper and faster. "
                "Blank uses the model's default.",
        "secret": False,
    },
    "CHAT_DEFAULT_BUDGET_USD": {
        "label": "Default monthly AI budget (USD)",
        "help": "Per-user cap for anyone without their own budget. Default 5. "
                "Admins are uncapped; per-user budgets are set on the Users tab.",
        "secret": False,
    },
    "CHAT_OPEN_SIGNUP_BUDGET_USD": {
        "label": "AI budget for open Google sign-ups (USD)",
        "help": "Monthly budget for people who sign in with Google without a signup link. "
                "Default 0 (no chat).",
        "secret": False,
    },
}

_lock = threading.Lock()
_cache: dict[str, str] = {}
_loaded_at = 0.0


def _fernet():
    from cryptography.fernet import Fernet

    from config import JWT_SECRET

    digest = hashlib.sha256(f"app-settings:{JWT_SECRET}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _load() -> dict[str, str]:
    from database import SessionLocal
    from models.app_setting import AppSetting

    out: dict[str, str] = {}
    f = _fernet()
    with SessionLocal() as db:
        for row in db.query(AppSetting).all():
            try:
                out[row.key] = f.decrypt(row.value_encrypted.encode()).decode()
            except Exception:
                logger.warning("app setting %s could not be decrypted (JWT_SECRET changed?)", row.key)
    return out


def saved() -> dict[str, str]:
    global _cache, _loaded_at
    with _lock:
        if time.monotonic() - _loaded_at > CACHE_SECONDS:
            try:
                _cache = _load()
            except Exception:
                # No table yet, or the DB is down: the environment still works.
                logger.debug("app settings unavailable", exc_info=True)
            _loaded_at = time.monotonic()
        return _cache


def invalidate() -> None:
    global _loaded_at
    with _lock:
        _loaded_at = 0.0


def save(db, key: str, value: str, user: str | None) -> None:
    from models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    enc = _fernet().encrypt(value.encode()).decode()
    if row is None:
        db.add(AppSetting(key=key, value_encrypted=enc, updated_by=user))
    else:
        row.value_encrypted, row.updated_by = enc, user
    db.commit()
    invalidate()


def clear(db, key: str) -> None:
    from models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    if row is not None:
        db.delete(row)
        db.commit()
    invalidate()
