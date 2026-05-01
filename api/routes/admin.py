"""Admin routes - user management, invites, system stats."""
import secrets
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, InviteToken
from models.document import Document, Project
from models.financial import FinancialStatement
from auth import get_admin_user

router = APIRouter()


# ── Response Models ──────────────────────────────────────────────────────────

class AdminStatsResponse(BaseModel):
    total_users: int
    total_projects: int
    total_documents: int
    total_statements: int
    pending_users: int


class AdminUserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: str

    class Config:
        from_attributes = True


class InviteRequest(BaseModel):
    email: str | None = None  # Lock invite to a specific email, or None for open invite
    expires_hours: int = 72


class InviteResponse(BaseModel):
    token: str
    invite_url: str
    email: str | None
    expires_at: str


class InviteListResponse(BaseModel):
    id: str
    token: str
    email: str | None
    is_used: bool
    used_by: str | None
    expires_at: str
    created_at: str


# ── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=AdminStatsResponse)
def get_stats(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return AdminStatsResponse(
        total_users=db.query(User).count(),
        total_projects=db.query(Project).count(),
        total_documents=db.query(Document).count(),
        total_statements=db.query(FinancialStatement).count(),
        pending_users=db.query(User).filter(User.is_active == False).count(),
    )


# ── User Management ─────────────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserResponse])
def list_users(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        AdminUserResponse(
            id=str(u.id),
            email=u.email,
            username=u.username,
            full_name=u.full_name,
            is_active=u.is_active,
            is_admin=u.is_admin,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.patch("/users/{user_id}/approve")
def approve_user(user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """Approve a pending user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    return {"id": str(user.id), "is_active": True}


@router.patch("/users/{user_id}/toggle-active")
def toggle_user_active(user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"id": str(user.id), "is_active": user.is_active}


@router.patch("/users/{user_id}/toggle-admin")
def toggle_user_admin(user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id):
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")
    user.is_admin = not user.is_admin
    db.commit()
    return {"id": str(user.id), "is_admin": user.is_admin}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    db.delete(user)
    db.commit()
    return {"deleted": True}


# ── Invite Links ─────────────────────────────────────────────────────────────

@router.post("/invites", response_model=InviteResponse)
def create_invite(
    req: InviteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Generate an invite link. Optionally lock to a specific email."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=req.expires_hours)

    invite = InviteToken(
        token=token,
        email=req.email.lower() if req.email else None,
        created_by=admin.id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()

    # Build the invite URL — frontend will read the ?invite= param
    base_url = "https://ahnj.info"
    invite_url = f"{base_url}?invite={token}"

    return InviteResponse(
        token=token,
        invite_url=invite_url,
        email=req.email,
        expires_at=expires_at.isoformat(),
    )


@router.get("/invites", response_model=List[InviteListResponse])
def list_invites(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    invites = db.query(InviteToken).order_by(InviteToken.created_at.desc()).limit(50).all()
    return [
        InviteListResponse(
            id=str(i.id),
            token=i.token,
            email=i.email,
            is_used=i.is_used,
            used_by=str(i.used_by) if i.used_by else None,
            expires_at=i.expires_at.isoformat(),
            created_at=i.created_at.isoformat(),
        )
        for i in invites
    ]


@router.delete("/invites/{invite_id}")
def delete_invite(invite_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    invite = db.query(InviteToken).filter(InviteToken.id == invite_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    db.delete(invite)
    db.commit()
    return {"deleted": True}
