"""Document management routes - upload, list, search, view, delete."""
import logging
import os
import uuid
import mimetypes
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.document import Document, Project
from models.user import User
from auth import get_current_user
from services.s3_service import S3Service, LOCAL_STORAGE_DIR

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


class DocumentListItem(BaseModel):
    """Slim version for list endpoints — only fields needed for the list UI."""
    id: str
    project_id: str
    filename: str
    file_size: int
    doc_type: str | None
    category: str | None
    department: str | None
    fiscal_year: str | None
    status: str

    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    doc_type: str | None = None
    category: str | None = None
    department: str | None = None
    fiscal_year: str | None = None
    notes: str | None = None


@router.get("/", response_model=List[DocumentListItem])
def list_documents(
    project_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List documents (slim — no notes). Use GET /{id} for full details with notes."""
    query = db.query(Document)
    if project_id:
        query = query.filter(Document.project_id == project_id)
    if category:
        query = query.filter(Document.category == category)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    docs = query.order_by(Document.created_at.desc()).all()
    return [
        DocumentListItem(
            id=str(d.id),
            project_id=str(d.project_id),
            filename=d.filename,
            file_size=d.file_size,
            doc_type=d.doc_type,
            category=d.category,
            department=d.department,
            fiscal_year=d.fiscal_year,
            status=d.status,
        )
        for d in docs
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full document details including notes/AI summary."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
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

    # Duplicate detection — check filename + size across all projects
    import hashlib
    file_hash = hashlib.md5(content).hexdigest()
    existing = db.query(Document).filter(
        Document.filename == file.filename,
        Document.file_size == file_size,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate document: '{file.filename}' ({file_size} bytes) already exists"
        )

    # Also check by content hash
    existing_hash = db.query(Document).filter(
        Document.file_size == file_size,
    ).all()
    for ex in existing_hash:
        try:
            ex_content = s3.download_file(ex.s3_key)
            if hashlib.md5(ex_content).hexdigest() == file_hash:
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate content: same file already exists as '{ex.filename}'"
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Can't download existing file — skip hash check

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


@router.get("/serve/{key:path}")
def serve_local_file(key: str):
    """Serve a locally stored file (used when S3 is not configured)."""
    ref_path = os.path.join(LOCAL_STORAGE_DIR, key + ".ref")
    if os.path.exists(ref_path):
        with open(ref_path, "r") as f:
            real_path = f.read().strip()
        if os.path.exists(real_path):
            return FileResponse(real_path)

    filepath = os.path.join(LOCAL_STORAGE_DIR, key)
    if os.path.exists(filepath):
        return FileResponse(filepath)

    raise HTTPException(status_code=404, detail="File not found")


class BulkImportRequest(BaseModel):
    directory: str
    project_id: str | None = None


@router.post("/bulk-import")
def bulk_import(
    req: BulkImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import all files from a local directory into the document library."""
    directory = req.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")

    s3_svc = S3Service()

    if req.project_id:
        project = db.query(Project).filter(Project.id == req.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        project = db.query(Project).filter(Project.name == "Knechtel Documents").first()
        if not project:
            project = Project(
                name="Knechtel Documents",
                description="Bulk imported from local Box folder",
                entity_type="general",
                created_by=user.id,
            )
            db.add(project)
            db.commit()
            db.refresh(project)

    existing = set()
    for (fn,) in db.query(Document.filename).filter(Document.project_id == project.id).all():
        existing.add(fn.lower())

    imported = []
    skipped = []

    for root, dirs, files in os.walk(directory):
        for fname in files:
            if fname.startswith(".") or fname.startswith("_"):
                continue
            if fname.lower() in existing:
                skipped.append(fname)
                continue

            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, directory).replace("\\", "/")
            file_size = os.path.getsize(full_path)
            content_type = mimetypes.guess_type(fname)[0] or "application/octet-stream"

            category = _categorize_file(fname, rel_path)
            doc_type = _detect_doc_type(fname, rel_path)
            fiscal_year = _detect_fiscal_year(fname)

            s3_key = f"imported/{str(project.id)}/{rel_path}"
            s3_svc.register_local_file(full_path, s3_key)

            doc = Document(
                project_id=project.id,
                filename=fname,
                original_filename=fname,
                s3_key=s3_key,
                s3_bucket="local",
                file_size=file_size,
                content_type=content_type,
                doc_type=doc_type,
                category=category,
                fiscal_year=fiscal_year,
                uploaded_by=user.id,
                status="uploaded",
            )
            db.add(doc)
            existing.add(fname.lower())
            imported.append(fname)

    db.commit()
    logger.info(f"Bulk import: {len(imported)} imported, {len(skipped)} skipped from {directory}")

    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "imported": len(imported),
        "skipped": len(skipped),
        "total_files": len(imported) + len(skipped),
    }


def _categorize_file(filename: str, rel_path: str) -> str:
    lower = (filename + " " + rel_path).lower()
    school_keywords = ["ahes", "hhrs", "hhrpk", "boe", "tridistrict", "tri-district",
                       "school", "board of education", "budget presentation"]
    if any(kw in lower for kw in school_keywords):
        return "school"
    town_keywords = ["atlantic highlands", "borough", "adopted budget", "audit report", "ads"]
    if any(kw in lower for kw in town_keywords):
        return "town"
    return "general"


def _detect_doc_type(filename: str, rel_path: str) -> str:
    lower = filename.lower()
    if "agenda" in lower:
        return "agenda"
    if "minute" in lower:
        return "minutes"
    if "budget" in lower:
        return "budget"
    if "audit" in lower or "amr" in lower:
        return "audit"
    if "financial" in lower or "fs" in lower or "cafr" in lower or "comprehensive" in lower:
        return "financial_statement"
    if "resolution" in lower:
        return "resolution"
    if "performance report" in lower:
        return "performance_report"
    if "civilcase" in lower or "olszewski" in lower or "reply brief" in lower:
        return "legal"
    if "opra" in lower or "ferpa" in lower:
        return "records_request"
    if "presentation" in lower or ".pptx" in lower:
        return "presentation"
    return "general"


def _detect_fiscal_year(filename: str) -> str | None:
    import re
    m = re.search(r'(20\d{2})[-/](20\d{2}|\d{2})', filename)
    if m:
        return m.group(0)
    m = re.search(r'(20\d{2})', filename)
    if m:
        return m.group(1)
    return None


@router.get("/{document_id}/view-url")
def get_view_url(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Always use our proxy endpoint — avoids cross-origin iframe issues
    return {"url": f"/api/documents/{document_id}/file"}


@router.get("/{document_id}/file")
def serve_document_file(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream the actual file content — works in iframes without CORS issues."""
    from fastapi.responses import Response
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        content = s3.download_file(doc.s3_key)
        content_type = doc.content_type or "application/pdf"
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{doc.filename}\"",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")


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
