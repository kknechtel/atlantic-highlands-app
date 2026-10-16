"""Create or update an admin user. Run once to bootstrap authentication.

Usage:
    python create_admin.py admin@example.org               # random password, printed once
    python create_admin.py admin@example.org 'a-password'  # your own password

The user must change the password on first login.
"""
import secrets
import sys

from auth import hash_password
from config import PUBLIC_WEB_ORIGIN
from database import SessionLocal, init_db
from models.user import User

if len(sys.argv) < 2 or "@" not in sys.argv[1]:
    sys.exit(__doc__)

email = sys.argv[1].strip().lower()
password = sys.argv[2] if len(sys.argv) > 2 else secrets.token_urlsafe(12)

init_db()
db = SessionLocal()
existing = db.query(User).filter(User.email == email).first()
if existing:
    existing.hashed_password = hash_password(password)
    existing.is_admin = True
    existing.is_active = True
    existing.must_change_password = True
    db.commit()
    print(f"Updated existing user: {email} (admin, active, password reset)")
else:
    db.add(
        User(
            email=email,
            username=email.split("@")[0],
            hashed_password=hash_password(password),
            full_name=None,
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )
    )
    db.commit()
    print(f"Created admin user: {email}")
db.close()

print(f"\nLogin at: {PUBLIC_WEB_ORIGIN}")
print(f"  Email:    {email}")
if len(sys.argv) <= 2:
    print(f"  Password: {password}")
print("  You will be asked to change the password on first login.")
