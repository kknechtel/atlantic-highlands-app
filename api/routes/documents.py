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


@router.get("", response_model=List[DocumentListItem], include_in_schema=False)
@router.get("/", response_model=List[DocumentListItem])
def list_documents(
    project_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
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
    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
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


@router.get("/count")
def count_documents(
    project_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Total document count for pagination."""
    query = db.query(Document)
    if project_id:
        query = query.filter(Document.project_id == project_id)
    if category:
        query = query.filter(Document.category == category)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    return {"count": query.count()}


class PresignedUploadRequest(BaseModel):
    filename: str
    content_type: str | None = None
    project_id: str
    doc_type: str | None = None
    category: str | None = None
    fiscal_year: str | None = None
    file_size: int


class PresignedUploadResponse(BaseModel):
    upload_url: str
    s3_key: str
    document_id: str  # Pre-allocated UUID; client confirms via /confirm-upload
    project_id: str  # Resolved project id (may differ from request if 'default' was sent)


class ConfirmUploadRequest(BaseModel):
    document_id: str
    s3_key: str
    filename: str
    file_size: int
    content_type: str | None = None
    project_id: str
    doc_type: str | None = None
    category: str | None = None
    fiscal_year: str | None = None


def _resolve_project(db: Session, project_id: str, user: User) -> Project:
    """Get project by id, or auto-create a default 'User Uploads' project."""
    if project_id and project_id != "default":
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            return project
    # Use or create the default 'User Uploads' project
    project = db.query(Project).filter(Project.name == "User Uploads").first()
    if not project:
        project = Project(
            name="User Uploads",
            description="Documents uploaded by users",
            entity_type="general",
            created_by=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
    return project


@router.post("/presigned-upload", response_model=PresignedUploadResponse)
def presigned_upload(
    req: PresignedUploadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a presigned S3 URL for direct browser-to-S3 upload (bypasses Amplify proxy)."""
    project = _resolve_project(db, req.project_id, user)

    # Duplicate check
    existing = db.query(Document).filter(
        Document.filename == req.filename,
        Document.file_size == req.file_size,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate document: '{req.filename}' ({req.file_size} bytes) already exists"
        )

    # Generate document ID and S3 key
    doc_id = str(uuid.uuid4())
    safe_name = req.filename.replace("/", "_").replace("\\", "_")
    s3_key = f"uploads/{project.id}/{doc_id}/{safe_name}"

    try:
        upload_url = s3.get_presigned_upload_url(s3_key, content_type=req.content_type)
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise HTTPException(status_code=500, detail=f"Could not generate upload URL: {e}")

    return PresignedUploadResponse(
        upload_url=upload_url,
        s3_key=s3_key,
        document_id=doc_id,
        project_id=str(project.id),
    )


@router.post("/confirm-upload", response_model=DocumentResponse)
def confirm_upload(
    req: ConfirmUploadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Register a document in the DB after the browser has uploaded directly to S3."""
    project = _resolve_project(db, req.project_id, user)

    # Verify file actually exists in S3
    try:
        s3.client.head_object(Bucket=s3.bucket, Key=req.s3_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File not found in S3: {e}")

    doc = Document(
        id=req.document_id,
        project_id=project.id,
        filename=req.filename,
        original_filename=req.filename,
        s3_key=req.s3_key,
        s3_bucket=s3.bucket,
        file_size=req.file_size,
        content_type=req.content_type,
        doc_type=req.doc_type,
        category=req.category,
        fiscal_year=req.fiscal_year,
        status="uploaded",
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
    # AMR = Auditor's Management Report — only the Excess Surplus worksheet,
    # not a full audit. Tag separately so the financial dashboard distinguishes.
    import re as _re
    if _re.search(r'\bamr\b', lower) or "auditor's management" in lower or "auditors management" in lower:
        return "audit_management_report"
    if "audit" in lower:
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
    """Pull a fiscal year from a filename.

    Accepts YYYY, YYYY-YYYY, or YYYY-YY. School-year ranges are only valid
    when the second half is year+1 — otherwise filenames like
    "2026-071 Payment of Bills" get mis-tagged as "2026-07".
    """
    import re
    for m in re.finditer(r'(20\d{2})[-/](20\d{2})', filename):
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 == y1 + 1:
            return f"{y1}-{y2}"
    for m in re.finditer(r'(20\d{2})[-/](\d{2})(?!\d)', filename):
        y1, suffix = int(m.group(1)), int(m.group(2))
        if suffix == (y1 + 1) % 100:
            return f"{y1}-{m.group(2)}"
    m = re.search(r'(?<!\d)(20\d{2})(?!\d)', filename)
    if m:
        return m.group(1)
    return None


def _looks_like_clean_year(value: str | None) -> bool:
    """Return True if a stored fiscal_year value is already in a clean form."""
    if not value:
        return False
    import re
    if re.fullmatch(r"(19|20)\d{2}", value):
        return True
    m = re.fullmatch(r"((?:19|20)\d{2})-(\d{2,4})", value)
    if not m:
        return False
    y1, suf = int(m.group(1)), m.group(2)
    return (len(suf) == 4 and int(suf) == y1 + 1) or (len(suf) == 2 and int(suf) == (y1 + 1) % 100)


def filename_year_backfill(db: Session) -> dict:
    """Filename-only pass: clean junk fiscal_year values and fill missing ones.

    Idempotent and cheap — safe to run on every startup. Touches only rows
    whose stored value isn't already clean. AI inference for docs that the
    filename regex can't help with happens automatically as part of normal
    document processing (services.document_processor.process_document calls
    analyze_document, which sets fiscal_year when missing).
    """
    cleaned = 0
    filled = 0
    for doc in db.query(Document).all():
        if _looks_like_clean_year(doc.fiscal_year):
            continue
        new_year = _detect_fiscal_year(doc.filename)
        if new_year:
            if doc.fiscal_year is None:
                filled += 1
            else:
                cleaned += 1
            doc.fiscal_year = new_year
        elif doc.fiscal_year:
            # Junk value with no recoverable year from the filename — clear it.
            doc.fiscal_year = None
            cleaned += 1
    if cleaned or filled:
        db.commit()
    return {"cleaned": cleaned, "filled": filled}


async def ai_year_inference_pass(
    batch_size: int = 25,
    max_per_run: int = 200,
    delay: float = 0.5,
):
    """Background pass: LLM-infer fiscal_year for docs that have extracted text but no year.

    Fires after startup as a fire-and-forget asyncio task. Idempotent across
    restarts:
      - Successes write the year.
      - LLM responded but couldn't find a year → marked metadata.ai_year_attempted
        so we don't keep asking the same question.
      - LLM call raised (network, rate limit) → not marked, will retry next time.
    Capped at max_per_run per process so each restart's AI cost is bounded; the
    next restart picks up the remaining backlog.
    """
    import asyncio
    from sqlalchemy import func, or_
    from sqlalchemy.orm.attributes import flag_modified
    from services.document_processor import analyze_document
    from database import SessionLocal

    processed = 0
    total_filled = 0
    while processed < max_per_run:
        with SessionLocal() as db:
            docs = (
                db.query(Document)
                .filter(Document.fiscal_year.is_(None))
                .filter(Document.extracted_text.isnot(None))
                .filter(func.length(Document.extracted_text) > 200)
                .filter(
                    or_(
                        Document.metadata_["ai_year_attempted"].astext.is_(None),
                        Document.metadata_["ai_year_attempted"].astext != "true",
                    )
                )
                .limit(batch_size)
                .all()
            )
            if not docs:
                logger.info(
                    f"ai_year_inference_pass: done (processed={processed} filled={total_filled})"
                )
                return

            batch_filled = 0
            for doc in docs:
                if processed >= max_per_run:
                    break
                try:
                    analysis = await analyze_document(doc.extracted_text, doc.filename)
                except Exception as e:
                    # Likely transient — leave the doc unmarked so it retries later.
                    logger.warning(f"ai_year_inference_pass: {doc.filename}: {e}")
                    await asyncio.sleep(delay)
                    continue

                if analysis is None:
                    # All providers failed — also treat as transient.
                    await asyncio.sleep(delay)
                    continue

                candidate = analysis.get("fiscal_year")
                if candidate and _looks_like_clean_year(candidate):
                    doc.fiscal_year = candidate
                    batch_filled += 1
                    total_filled += 1

                # LLM answered (even if "no year") — mark attempted to skip next time.
                doc.metadata_ = {**(doc.metadata_ or {}), "ai_year_attempted": "true"}
                flag_modified(doc, "metadata_")
                processed += 1
                await asyncio.sleep(delay)

            db.commit()
            logger.info(
                f"ai_year_inference_pass batch: filled={batch_filled}/{len(docs)} "
                f"(running totals: processed={processed} filled={total_filled})"
            )

    logger.info(
        f"ai_year_inference_pass: hit per-run cap ({max_per_run}); "
        f"filled={total_filled} this run"
    )


@router.get("/{document_id}/view-url")
def get_view_url(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # If using S3, return a presigned URL (works in iframes — no auth header needed)
    if not s3.use_local:
        try:
            url = s3.get_presigned_url(doc.s3_key, expires_in=3600)
            return {"url": url}
        except Exception as e:
            logger.warning(f"Could not generate presigned URL for {doc.s3_key}: {e}")
    # Fall back to proxy endpoint (requires auth, won't work in iframe)
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
