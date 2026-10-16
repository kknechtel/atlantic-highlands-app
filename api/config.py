"""
Atlantic Highlands - Configuration
Loads from AWS Secrets Manager in production, falls back to env vars / .env for local dev.
"""
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── AWS Secrets Manager ──────────────────────────────────────────────────────

def _load_aws_secrets() -> dict:
    """Load secrets from AWS Secrets Manager. Returns empty dict on failure."""
    secret_name = os.getenv("AWS_SECRETS_NAME", "")
    if not secret_name:
        return {}
    try:
        import boto3
        region = os.getenv("AWS_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secrets = json.loads(response["SecretString"])
        logger.info(f"Loaded {len(secrets)} secrets from AWS Secrets Manager ({secret_name})")
        return secrets
    except Exception as e:
        logger.warning(f"AWS Secrets Manager unavailable ({e}), using env vars")
        return {}


_secrets = _load_aws_secrets()


def _get(key: str, default: str = "") -> str:
    """Get config value: AWS Secrets Manager > env var > default."""
    return _secrets.get(key, os.getenv(key, default))


# ── Application ──────────────────────────────────────────────────────────────

APP_NAME = "Atlantic Highlands"
DEBUG = _get("DEBUG", "false").lower() == "true"
SECRET_KEY = _get("SECRET_KEY", "change-me-in-production")
ALLOWED_ORIGINS = _get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

# Database
DATABASE_URL = _get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/atlantic_highlands"
)

# AWS
AWS_REGION = _get("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = _get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = _get("AWS_SECRET_ACCESS_KEY")
S3_BUCKET = _get("S3_BUCKET", "atlantic-highlands-documents")

# AI / LLM keys and Google Sign-In are read with api_key() at call time, so a
# value an admin saves on the Settings screen takes effect without a restart.
# The environment (or AWS Secrets Manager) is the fallback.
def api_key(name: str) -> str:
    """Live value of an admin-settable key: Settings screen > env > ""."""
    from services.app_settings import saved

    return (saved().get(name) or _get(name) or "").strip()

# Auth
JWT_SECRET = _get("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(_get("JWT_EXPIRATION_HOURS", "24"))

# Refuse to start with a placeholder/weak JWT_SECRET. "change-me-in-production"
# is the literal default committed in this repo and in .env.example — running
# with it lets anyone forge a JWT for any user, including admins. If you hit
# this in local dev:
#   export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
if JWT_SECRET in ("", "change-me-in-production") or len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET is unset, too short, or using the placeholder default. "
        "Set JWT_SECRET to a value of at least 32 characters."
    )

# Email — digests, alerts. SES is the only sender; if FROM is blank, sends are
# silently dropped (useful for local dev where no SES identity is verified).
DIGEST_FROM_EMAIL = _get("DIGEST_FROM_EMAIL", "")
DIGEST_REPLY_TO = _get("DIGEST_REPLY_TO", "")
PUBLIC_WEB_ORIGIN = _get("PUBLIC_WEB_ORIGIN", "https://ahnj.info")

# Google Sign-In: api_key("GOOGLE_OAUTH_CLIENT_ID"). When blank,
# /api/auth/google returns 503 and password login still works.
