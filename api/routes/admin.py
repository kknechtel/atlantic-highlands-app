"""Admin routes - user management, system stats."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.document import Document, Project
from models.financial import FinancialStatement
from auth import get_admin_user

router = APIRouter()


class AdminStatsResponse(BaseModel):
    total_users: int
    total_projects: int
    total_documents: int
    total_statements: int


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


@router.get("/stats", response_model=AdminStatsResponse)
def get_stats(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return AdminStatsResponse(
        total_users=db.query(User).count(),
        total_projects=db.query(Project).count(),
        total_documents=db.query(Document).count(),
        total_statements=db.query(FinancialStatement).count(),
    )


@router.get("/users", response_model=List[AdminUserResponse])
def list_users(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    users = db.query(User).all()
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


@router.patch("/users/{user_id}/toggle-active")
def toggle_user_active(user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"id": str(user.id), "is_active": user.is_active}
