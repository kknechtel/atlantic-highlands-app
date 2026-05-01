"""Create or update the admin user. Run once to bootstrap authentication.

Usage:
    python create_admin.py                           # creates karl@rkc.llc with default password
    python create_admin.py email@example.com pass123  # custom email/password
"""
import sys
from database import SessionLocal, init_db
from models.user import User
from auth import hash_password

init_db()
db = SessionLocal()

email = sys.argv[1] if len(sys.argv) > 1 else "karl@rkc.llc"
password = sys.argv[2] if len(sys.argv) > 2 else "283Home"

existing = db.query(User).filter(User.email == email).first()
if existing:
    existing.hashed_password = hash_password(password)
    existing.is_admin = True
    existing.is_active = True
    existing.must_change_password = True
    db.commit()
    print(f"Updated existing user: {email} (admin=True, active=True, password reset)")
else:
    user = User(
        email=email,
        username=email.split("@")[0],
        hashed_password=hash_password(password),
        full_name="Karl Knechtel",
        is_active=True,
        is_admin=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    print(f"Created admin user: {email}")

print(f"\nLogin at: https://ahnj.info")
print(f"  Email:    {email}")
print(f"  You will be prompted to change your password on first login.")
db.close()
