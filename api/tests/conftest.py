"""Test setup: a throwaway JWT secret before any app module is imported."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ah_test")
