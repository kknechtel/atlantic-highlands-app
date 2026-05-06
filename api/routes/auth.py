"""Authentication routes - login, register, magic link invites."""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, InviteToken
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_allow_pending,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Models ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class SetPasswordRequest(BaseModel):
    invite_token: str
    email: str
    password: str
    full_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    pending_approval: bool = False


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str | None
    is_admin: bool
    is_active: bool
    must_change_password: bool = False

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    new_password: str


class InviteCheckResponse(BaseModel):
    valid: bool
    email: str | None
    already_registered: bool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_invite(db: Session, token_str: str) -> InviteToken:
    """Validate an invite token. Raises HTTPException if invalid."""
    invite = db.query(InviteToken).filter(
        InviteToken.token == token_str,
        InviteToken.is_used == False,
    ).first()

    if not invite:
        raise HTTPException(status_code=400, detail="Invalid invite link")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invite link has expired")
    return invite


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Standard email/password login."""
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        token = create_access_token({"sub": str(user.id)})
        return TokenResponse(access_token=token, pending_approval=True)

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/invite/{token}", response_model=InviteCheckResponse)
def check_invite(token: str, db: Session = Depends(get_db)):
    """Check if an invite token is valid. Frontend calls this on page load."""
    invite = db.query(InviteToken).filter(
        InviteToken.token == token,
        InviteToken.is_used == False,
    ).first()

    if not invite or invite.expires_at < datetime.utcnow():
        return InviteCheckResponse(valid=False, email=None, already_registered=False)

    already_registered = False
    if invite.email:
        existing = db.query(User).filter(User.email == invite.email).first()
        already_registered = existing is not None

    return InviteCheckResponse(
        valid=True,
        email=invite.email,
        already_registered=already_registered,
    )


@router.post("/magic-link", response_model=TokenResponse)
def magic_link_login(req: SetPasswordRequest, db: Session = Depends(get_db)):
    """
    Accept an invite, set a password, and log in.
    - If user exists (email-locked invite): activate + update password
    - If user doesn't exist: create account, activate, set password
    """
    invite = _validate_invite(db, req.invite_token)

    # If invite is email-locked, enforce it
    if invite.email and invite.email.lower() != req.email.lower():
        raise HTTPException(status_code=400, detail="This invite is for a different email address")

    user = db.query(User).filter(User.email == req.email).first()

    if user:
        # Existing user — activate and update password
        user.hashed_password = hash_password(req.password)
        user.is_active = True
        if req.full_name:
            user.full_name = req.full_name
    else:
        # New user — create account
        username = req.email.split("@")[0]
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            email=req.email,
            username=username,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
            is_active=True,
        )
        db.add(user)
        db.flush()

    # Consume the invite
    invite.is_used = True
    invite.used_by = user.id
    db.commit()
    db.refresh(user)

    logger.info(f"Magic link login: {req.email} (invite consumed)")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user_allow_pending)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        is_admin=current_user.is_admin,
        is_active=current_user.is_active,
        must_change_password=current_user.must_change_password,
    )


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user_allow_pending),
    db: Session = Depends(get_db),
):
    """Change password. Clears the must_change_password flag."""
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    current_user.hashed_password = hash_password(req.new_password)
    current_user.must_change_password = False
    db.commit()
    return {"detail": "Password changed"}


class DirectoryEntry(BaseModel):
    id: str
    email: str
    full_name: str | None


@router.get("/directory", response_model=list[DirectoryEntry])
def user_directory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Minimal directory of approved users — used by share dialogs to pick
    a target user. Excludes pending/disabled accounts and the requester
    themselves."""
    users = (
        db.query(User)
        .filter(User.is_active == True, User.id != current_user.id)
        .order_by(User.email)
        .all()
    )
    return [
        DirectoryEntry(id=str(u.id), email=u.email, full_name=u.full_name)
        for u in users
    ]
