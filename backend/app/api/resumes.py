import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.resume import Resume


router = APIRouter(prefix="/api/resumes", tags=["Resumes"])

MAX_FILE_SIZE = 5 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
STORAGE_DIR = Path(
    os.environ.get(
        "RESUME_STORAGE_DIR",
        str(Path(__file__).resolve().parents[2] / "private_uploads"),
    )
).resolve()

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
PDF_SIGNATURE = b"%PDF-"
DOCX_SIGNATURE = b"PK\\x03\\x04"


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "resume").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return (name or "resume")[:255]


def _validate_docx(content: bytes) -> bool:
    """Reject non-Word ZIP files and archives with suspicious expansion sizes."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = {item.filename: item for item in archive.infolist()}
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(entries):
                return False

            # Limit total uncompressed content and individual entry sizes.
            total_uncompressed = 0
            for item in entries.values():
                if item.file_size < 0 or item.file_size > 20 * 1024 * 1024:
                    return False
                total_uncompressed += item.file_size
                if total_uncompressed > 40 * 1024 * 1024:
                    return False

            # Verify essential entries can actually be decompressed.
            for name in required:
                if not archive.read(name):
                    return False
            return True
    except (zipfile.BadZipFile, OSError, RuntimeError, KeyError, ValueError):
        return False


def _validate_file(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Only PDF and DOCX files are supported.")
    if extension == ".pdf" and not content.startswith(PDF_SIGNATURE):
        raise HTTPException(400, "The file does not appear to be a valid PDF.")
    if extension == ".docx" and not _validate_docx(content):
        raise HTTPException(400, "The file does not appear to be a valid DOCX.")
    return (
        "application/pdf"
        if extension == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def _owned_resume(resume_id: int, user_id: str, db: Session) -> Resume:
    resume = db.scalar(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == user_id,
        )
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user_id: CurrentUser,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = _safe_filename(file.filename)
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Only PDF and DOCX files are supported.")

    content = bytearray()
    try:
        while chunk := await file.read(CHUNK_SIZE):
            content.extend(chunk)
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(413, "Resume must be 5 MB or smaller.")
    finally:
        await file.close()

    if not content:
        raise HTTPException(400, "The uploaded file is empty.")

    content_type = _validate_file(filename, bytes(content))
    storage_key = f"{uuid.uuid4().hex}{extension}"
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = STORAGE_DIR / storage_key

    try:
        with stored_path.open("xb") as destination:
            destination.write(content)

        resume = Resume(
            user_id=user_id,
            original_filename=filename,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    return {
        "id": resume.id,
        "original_filename": resume.original_filename,
        "content_type": resume.content_type,
        "size_bytes": resume.size_bytes,
        "created_at": resume.created_at,
    }


@router.get("")
def list_resumes(
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    resumes = db.scalars(
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.created_at.desc(), Resume.id.desc())
    ).all()
    return [
        {
            "id": resume.id,
            "original_filename": resume.original_filename,
            "content_type": resume.content_type,
            "size_bytes": resume.size_bytes,
            "created_at": resume.created_at,
        }
        for resume in resumes
    ]


@router.get("/{resume_id}/download")
def download_resume(
    resume_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    resume = _owned_resume(resume_id, user_id, db)
    stored_path = (STORAGE_DIR / resume.storage_key).resolve()

    if stored_path.parent != STORAGE_DIR or not stored_path.is_file():
        raise HTTPException(404, "Resume file not found")

    return FileResponse(
        path=stored_path,
        media_type=resume.content_type,
        filename=resume.original_filename,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    resume = _owned_resume(resume_id, user_id, db)
    stored_path = (STORAGE_DIR / resume.storage_key).resolve()

    if stored_path.parent != STORAGE_DIR:
        raise HTTPException(400, "Invalid resume storage key")

    db.delete(resume)
    db.commit()
    stored_path.unlink(missing_ok=True)
    return None
