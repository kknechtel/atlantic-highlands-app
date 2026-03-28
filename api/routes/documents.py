"""Document management routes - upload, list, search, view, delete."""
import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.document import Document, Project
from models.user import User
from auth import get_current_user
from services.s3_service import S3Service

logger = logging.getLogger(__name__)
router = APIRouter()
s3 = S3Service()


class DocumentResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    original_filename: str
    s3_key: str
    file_size: int
    content_type: str | None
    doc_type: str | None
    category: str | None
    department: str | None
    fiscal_year: str | None
    status: str
    notes: str | None
    created_at: str

    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    doc_type: str | None = None
    category: str | None = None
    department: str | None = None
    fiscal_year: str | None = None
    notes: str | None = None


@router.get("/", response_model=List[DocumentResponse])
def list_documents(
    project_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Document)
    if project_id:
        query = query.filter(Document.project_id == project_id)
    if category:
        query = query.filter(Document.category == category)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    docs = query.order_by(Document.created_at.desc()).all()
    return [
        DocumentResponse(
            id=str(d.id),
            project_id=str(d.project_id),
            filename=d.filename,
            original_filename=d.original_filename,
            s3_key=d.s3_key,
            file_size=d.file_size,
            content_type=d.content_type,
            doc_type=d.doc_type,
            category=d.category,
            department=d.department,
            fiscal_year=d.fiscal_year,
            status=d.status,
            notes=d.notes,
            created_at=d.created_at.isoformat(),
        )
        for d in docs
    ]


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    doc_type: str = Form(None),
    category: str = Form(None),
    fiscal_year: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Generate unique S3 key
    file_id = str(uuid.uuid4())
    s3_key = f"documents/{project_id}/{file_id}/{file.filename}"

    # Upload to S3
    s3.upload_file(content, s3_key, file.content_type)
    logger.info(f"Uploaded {file.filename} to S3: {s3_key} ({file_size} bytes)")

    # Create database record
    doc = Document(
        project_id=project_id,
        filename=file.filename,
        original_filename=file.filename,
        s3_key=s3_key,
        s3_bucket=s3.bucket,
        file_size=file_size,
        content_type=file.content_type,
        doc_type=doc_type,
        category=category,
        fiscal_year=fiscal_year,
        uploaded_by=user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return DocumentResponse(
        id=str(doc.id),
        project_id=str(doc.project_id),
        filename=doc.filename,
        original_filename=doc.original_filename,
        s3_key=doc.s3_key,
        file_size=doc.file_size,
        content_type=doc.content_type,
        doc_type=doc.doc_type,
        category=doc.category,
        department=doc.department,
        fiscal_year=doc.fiscal_year,
        status=doc.status,
        notes=doc.notes,
        created_at=doc.created_at.isoformat(),
    )


@router.post("/upload-multiple")
async def upload_multiple_documents(
    files: List[UploadFile] = File(...),
    project_id: str = Form(...),
    category: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    results = []
    for file in files:
        content = await file.read()
        file_id = str(uuid.uuid4())
        s3_key = f"documents/{project_id}/{file_id}/{file.filename}"

        s3.upload_file(content, s3_key, file.content_type)

        doc = Document(
            project_id=project_id,
            filename=file.filename,
            original_filename=file.filename,
            s3_key=s3_key,
            s3_bucket=s3.bucket,
            file_size=len(content),
            content_type=file.content_type,
            category=category,
            uploaded_by=user.id,
        )
        db.add(doc)
        results.append({"filename": file.filename, "status": "uploaded"})

    db.commit()
    return {"uploaded": len(results), "files": results}


@router.get("/{document_id}/view-url")
def get_view_url(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    url = s3.get_presigned_url(doc.s3_key)
    return {"url": url}


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: str,
    update: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(doc, field, value)
    db.commit()
    db.refresh(doc)

    return DocumentResponse(
        id=str(doc.id),
        project_id=str(doc.project_id),
        filename=doc.filename,
        original_filename=doc.original_filename,
        s3_key=doc.s3_key,
        file_size=doc.file_size,
        content_type=doc.content_type,
        doc_type=doc.doc_type,
        category=doc.category,
        department=doc.department,
        fiscal_year=doc.fiscal_year,
        status=doc.status,
        notes=doc.notes,
        created_at=doc.created_at.isoformat(),
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from S3
    s3.delete_file(doc.s3_key)

    db.delete(doc)
    db.commit()
    return {"detail": "Document deleted"}
