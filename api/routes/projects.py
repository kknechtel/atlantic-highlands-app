"""Project management routes."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.document import Project
from models.user import User
from auth import get_current_user

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    entity_type: str | None = None  # "town", "school", "general"


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str | None
    document_count: int = 0
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=List[ProjectResponse], include_in_schema=False)
@router.get("/", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.query(Project).all()
    results = []
    for p in projects:
        results.append(ProjectResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            entity_type=p.entity_type,
            document_count=len(p.documents),
            created_at=p.created_at.isoformat(),
        ))
    return results


@router.post("", response_model=ProjectResponse, include_in_schema=False)
@router.post("/", response_model=ProjectResponse)
def create_project(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(
        name=req.name,
        description=req.description,
        entity_type=req.entity_type,
        created_by=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        entity_type=project.entity_type,
        document_count=0,
        created_at=project.created_at.isoformat(),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        entity_type=project.entity_type,
        document_count=len(project.documents),
        created_at=project.created_at.isoformat(),
    )


@router.delete("/{project_id}")
def delete_project(project_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"detail": "Project deleted"}
