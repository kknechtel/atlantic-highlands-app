"""Authentication utilities - JWT-based auth."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from database import get_db
from models.user import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _get_or_create_default_user(db: Session) -> User:
    """Get or create a default admin user (auth disabled)."""
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        user = User(
            email="admin@atlantichighlands.local",
            username="admin",
            hashed_password="$2b$12$disabled",  # placeholder, auth is off
            full_name="Admin",
            is_active=True,
            is_admin=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    db: Session = Depends(get_db),
) -> User:
    """Auth disabled - returns default admin user."""
    return _get_or_create_default_user(db)


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
