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

# AI / LLM
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
GEMINI_API_KEY = _get("GEMINI_API_KEY")

# Auth
JWT_SECRET = _get("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(_get("JWT_EXPIRATION_HOURS", "24"))
