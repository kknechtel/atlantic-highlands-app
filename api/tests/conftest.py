import os

# config.py refuses to import without a real-looking JWT secret.
os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "x" * 32)
