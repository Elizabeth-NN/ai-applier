import html
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
# FIX: was b"PK\\x03\\x04" (a literal backslash string), and was never used.
DOCX_SIGNATURE = b"PK\x03\x04"

MAX_DOCX_ENTRY_BYTES = 20 * 1024 * 1024
MAX_DOCX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_PDF_PAGES = 20


# ---------------------------------------------------------------------------
# Upload validation / storage helpers
# ---------------------------------------------------------------------------
def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "resume").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return (name or "resume")[:255]


def _validate_docx(content: bytes) -> bool:
    """Reject non-Word ZIP files and archives with suspicious expansion sizes."""
    if not content.startswith(DOCX_SIGNATURE):
        return False
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = {item.filename: item for item in archive.infolist()}
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(entries):
                return False

            total_uncompressed = 0
            for item in entries.values():
                if item.file_size < 0 or item.file_size > MAX_DOCX_ENTRY_BYTES:
                    return False
                total_uncompressed += item.file_size
                if total_uncompressed > MAX_DOCX_TOTAL_BYTES:
                    return False

            # Verify essential entries decompress (bounded read, header sizes
            # can lie, so never trust them for the actual read).
            for name in required:
                with archive.open(name) as fh:
                    if not fh.read(MAX_DOCX_ENTRY_BYTES + 1):
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


def get_owned_resume(resume_id: int, user_id: str, db: Session) -> Resume:
    resume = db.scalar(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == user_id,
        )
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


# Backwards-compatible alias.
_owned_resume = get_owned_resume


def _resolve_stored_path(resume: Resume) -> Path:
    stored_path = (STORAGE_DIR / resume.storage_key).resolve()
    if stored_path.parent != STORAGE_DIR:
        raise HTTPException(400, "Invalid resume storage key")
    return stored_path


def read_resume_bytes(resume: Resume) -> bytes:
    stored_path = _resolve_stored_path(resume)
    if not stored_path.is_file():
        raise HTTPException(404, "Resume file not found")
    return stored_path.read_bytes()


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # pip install pypdf
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(500, "PDF parsing requires the 'pypdf' package.") from exc

    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise HTTPException(422, "Password-protected PDFs cannot be read.")
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((page.extract_text() or "") for page in pages)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "Could not read text from this PDF.") from exc


def _extract_docx_text(content: bytes) -> str:
    """Regex based extraction (avoids stdlib XML entity-expansion issues)."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            with archive.open("word/document.xml") as fh:
                raw = fh.read(MAX_DOCX_ENTRY_BYTES + 1)
        if len(raw) > MAX_DOCX_ENTRY_BYTES:
            raise HTTPException(422, "DOCX content is too large to parse.")
        xml = raw.decode("utf-8", errors="ignore")
    except HTTPException:
        raise
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(422, "Could not read text from this DOCX.") from exc

    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:(?:br|cr)\s*/?>", "\n", xml)
    xml = re.sub(r"<w:tab\s*/?>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(text)


def extract_resume_text(resume: Resume) -> str:
    content = read_resume_bytes(resume)
    if resume.content_type == "application/pdf":
        text = _extract_pdf_text(content)
    else:
        text = _extract_docx_text(content)

    text = text.replace("\x00", "").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 20:
        raise HTTPException(
            422,
            "No readable text found in this resume (scanned/image-only files are not supported).",
        )
    return text


# ---------------------------------------------------------------------------
# Heuristic field parsing
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w@])(\+?\d[\d\s().-]{7,}\d)(?![\w@])")
LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9_%-]+/?",
    re.I,
)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9-]+/?", re.I)
LOCATION_RE = re.compile(
    r"\b([A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){0,2},\s*"
    r"(?:[A-Z]{2}|[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){0,2}))\b"
)

SECTION_HEADINGS = {
    "summary": {"summary", "professional summary", "profile", "professional profile",
                "objective", "career objective", "about", "about me"},
    "skills": {"skills", "technical skills", "core competencies", "key skills",
               "skills & tools", "skills and tools", "technologies", "competencies"},
    "other": {"experience", "work experience", "professional experience",
              "employment history", "education", "projects", "certifications",
              "certificates", "awards", "languages", "interests", "references",
              "publications", "volunteer experience", "work history", "achievements"},
}
ALL_HEADINGS = set().union(*SECTION_HEADINGS.values())


def _heading_of(line: str) -> str | None:
    cleaned = re.sub(r"[:\-–—_=*#\s]+$", "", line.strip()).strip().lower()
    if len(cleaned) > 40 or cleaned not in ALL_HEADINGS:
        return None
    for key, names in SECTION_HEADINGS.items():
        if cleaned in names:
            return key
    return None


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        heading = _heading_of(line)
        if heading is not None:
            current = heading if heading != "other" else None
            if current:
                sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def _looks_like_name(line: str) -> bool:
    if EMAIL_RE.search(line) or any(ch.isdigit() for ch in line):
        return False
    if _heading_of(line) or "http" in line.lower() or "|" in line:
        return False
    words = line.replace(",", " ").split()
    if not 2 <= len(words) <= 4:
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'’-]*", w) for w in words)


def _parse_skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    for line in lines:
        line = re.sub(r"^[\s•·▪●■\-*–]+", "", line)
        if ":" in line:  # "Languages: Python, Go"
            line = line.split(":", 1)[1]
        for part in re.split(r"[,;|•·▪●/]|\s{2,}", line):
            skill = part.strip(" .-–")
            if 1 < len(skill) <= 40 and skill.lower() not in seen:
                seen.add(skill.lower())
                skills.append(skill)
    return skills[:50]


def parse_resume_fields(text: str) -> dict:
    """Best-effort extraction. Only keys that were actually found are returned."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    header = lines[:10]
    result: dict = {}

    if m := EMAIL_RE.search(text):
        result["email"] = m.group(0).lower()

    for m in PHONE_RE.finditer("\n".join(header) or text):
        digits = re.sub(r"\D", "", m.group(1))
        if 8 <= len(digits) <= 15:
            result["phone"] = re.sub(r"\s+", " ", m.group(1)).strip()
            break

    if m := LINKEDIN_RE.search(text):
        url = m.group(0).rstrip("/")
        result["linkedin_url"] = url if url.lower().startswith("http") else f"https://{url}"

    if m := GITHUB_RE.search(text):
        url = m.group(0).rstrip("/")
        result["github_url"] = url if url.lower().startswith("http") else f"https://{url}"

    name_index = None
    for i, line in enumerate(header[:6]):
        if _looks_like_name(line):
            result["full_name"] = " ".join(line.replace(",", " ").split()).title() \
                if line.isupper() else " ".join(line.replace(",", " ").split())
            parts = result["full_name"].split()
            result["first_name"] = parts[0]
            result["last_name"] = " ".join(parts[1:])
            name_index = i
            break

    # Headline: the line right after the name if it is not contact info.
    if name_index is not None and name_index + 1 < len(header):
        candidate = header[name_index + 1]
        if (
            len(candidate) <= 80
            and not EMAIL_RE.search(candidate)
            and not _heading_of(candidate)
            and "http" not in candidate.lower()
            and sum(ch.isdigit() for ch in candidate) == 0
        ):
            result["headline"] = candidate

    for line in header:
        if EMAIL_RE.search(line) and "|" not in line and "," not in line:
            continue
        scan = EMAIL_RE.sub("", line)
        scan = re.sub(r"https?://\S+|\S+\.(?:com|net|io)\S*", "", scan)
        if m := LOCATION_RE.search(scan):
            result["location"] = m.group(1)
            break

    sections = _split_sections(lines)
    if summary := " ".join(sections.get("summary", [])).strip():
        result["summary"] = summary[:2000]
    if skills := _parse_skills(sections.get("skills", [])):
        result["skills"] = skills

    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _resume_out(resume: Resume) -> dict:
    return {
        "id": resume.id,
        "original_filename": resume.original_filename,
        "content_type": resume.content_type,
        "size_bytes": resume.size_bytes,
        "created_at": resume.created_at,
    }


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

    return _resume_out(resume)


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
    return [_resume_out(resume) for resume in resumes]


@router.get("/{resume_id}/parse")
def parse_resume(
    resume_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Preview what would be extracted from the resume (nothing is saved)."""
    resume = get_owned_resume(resume_id, user_id, db)
    return parse_resume_fields(extract_resume_text(resume))


@router.get("/{resume_id}/download")
def download_resume(
    resume_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    resume = get_owned_resume(resume_id, user_id, db)
    stored_path = _resolve_stored_path(resume)

    if not stored_path.is_file():
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
    resume = get_owned_resume(resume_id, user_id, db)
    stored_path = _resolve_stored_path(resume)

    db.delete(resume)
    db.commit()
    stored_path.unlink(missing_ok=True)
    return None