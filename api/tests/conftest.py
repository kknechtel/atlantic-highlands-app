"""Test setup: a throwaway JWT secret before any app module is imported. No network, no database."""
import os
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ah_test")

FIXTURES = Path(__file__).parent / "fixtures"
