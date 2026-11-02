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
URL_RE = re.compile(r"(?:https?://|www\.)[^\s)>\],;]+", re.I)
LOCATION_RE = re.compile(
    r"\b([A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){0,2},\s*"
    r"(?:[A-Z]{2}|[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){0,2}))\b"
)
LOCATION_ONLY_RE = re.compile(
    r"[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){0,2},\s*"
    r"[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){0,2}"
)

SECTION_HEADINGS = {
    "summary": {"summary", "professional summary", "profile", "professional profile",
                "objective", "career objective", "about", "about me", "personal statement",
                "career summary"},
    "skills": {"skills", "technical skills", "core competencies", "key skills",
               "skills and tools", "technologies", "competencies", "skills and competencies",
               "areas of expertise", "tech stack"},
    "experience": {"experience", "work experience", "professional experience",
                   "employment history", "work history", "career history",
                   "relevant experience", "internships", "internship experience",
                   "employment", "professional background"},
    "education": {"education", "academic background", "education and training",
                  "academic qualifications", "qualifications", "education and qualifications"},
    "projects": {"projects", "personal projects", "selected projects", "key projects",
                 "academic projects", "technical projects"},
    "certifications": {"certifications", "certificates", "licenses and certifications",
                       "courses", "training", "certifications and training",
                       "professional certifications", "courses and certifications",
                       "training and certifications"},
    "other": {"awards", "languages", "interests", "references", "publications",
              "volunteer experience", "achievements", "hobbies", "referees",
              "extracurricular activities", "leadership"},
}
ALL_HEADINGS = set().union(*SECTION_HEADINGS.values())

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+\d{4}"
_DATE_TOKEN = rf"(?:{_MONTH}|\d{{1,2}}/\d{{4}}|\d{{4}})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:-|–|—|to|until)\s*"
    rf"(?P<end>{_DATE_TOKEN}|present|current|now|ongoing|date)\b",
    re.I,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
BULLET_RE = re.compile(r"^\s*[•·▪●■◦○►➢✓*\-–—>]+\s*")

TITLE_RE = re.compile(
    r"engineer|developer|manager|analyst|intern|officer|assistant|lead|director|designer|"
    r"consultant|specialist|administrator|coordinator|associate|architect|scientist|"
    r"technician|accountant|executive|representative|supervisor|teacher|tutor|volunteer|"
    r"attendant|clerk|programmer|trainee|attach[eé]|head|president|founder|owner|"
    r"researcher|lecturer|instructor|writer|editor|agent|advisor|adviser",
    re.I,
)
COMPANY_RE = re.compile(
    r"\b(?:ltd|limited|inc|llc|corp|corporation|company|co\.|group|bank|technologies|"
    r"solutions|systems|hospital|agency|foundation|services|labs|studio|ngo|plc|"
    r"enterprises|holdings|university|college|school|institute|ministry|authority)\b",
    re.I,
)
INSTITUTION_RE = re.compile(
    r"universit|college|school|institute|academy|polytechnic|campus", re.I
)


def _heading_of(line: str) -> str | None:
    cleaned = re.sub(r"[:\-–—_=*#\s]+$", "", line.strip()).strip().lower()
    cleaned = re.sub(r"\s*&\s*", " and ", cleaned)
    if len(cleaned) > 45 or cleaned not in ALL_HEADINGS:
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


def _is_bullet(line: str) -> bool:
    return bool(BULLET_RE.match(line)) and len(line.strip()) > 1


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line).strip()


def _parse_skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    for line in lines:
        line = _strip_bullet(line)
        if ":" in line:  # "Languages: Python, Go"
            line = line.split(":", 1)[1]
        for part in re.split(r"[,;|•·▪●/]|\s{2,}", line):
            skill = part.strip(" .-–")
            if 1 < len(skill) <= 40 and skill.lower() not in seen:
                seen.add(skill.lower())
                skills.append(skill)
    return skills[:50]


# ----- dates / entries ------------------------------------------------------
def _norm_date(token: str | None) -> str | None:
    if not token:
        return None
    t = token.strip().lower().strip(".,")
    if t in {"present", "current", "now", "ongoing", "date"}:
        return "Present"
    if m := re.match(r"([a-z]{3})[a-z]*\.?,?\s+(\d{4})", t):
        month = MONTHS.get(m.group(1))
        return f"{m.group(2)}-{month:02d}" if month else m.group(2)
    if m := re.match(r"(\d{1,2})/(\d{4})", t):
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    return t


def _split_header(text: str) -> list[str]:
    text = re.sub(r"[()\[\]]", " ", text)
    parts = re.split(r"\s*\|\s*|\s+[-–—]\s+|\s+at\s+|\s+@\s+", text)
    parts = [p.strip(" ,;:-–—•·") for p in parts]
    parts = [p for p in parts if p]
    if len(parts) == 1 and "," in parts[0]:
        pieces = [p.strip() for p in parts[0].split(",", 1)]
        looks_like_location = LOCATION_ONLY_RE.fullmatch(parts[0]) and not (
            TITLE_RE.search(parts[0]) or COMPANY_RE.search(parts[0])
        )
        if all(pieces) and not looks_like_location:
            parts = pieces
    return parts


def _merge_wrapped(lines: list[str]) -> list[str]:
    """Join bullets with the continuation lines PDFs wrap them onto."""
    items: list[str] = []
    for line in lines:
        text = _strip_bullet(line)
        if not text:
            continue
        if _is_bullet(line) or not items:
            items.append(text)
        else:
            items[-1] = f"{items[-1]} {text}"
    return items


def _header_like(line: str) -> bool:
    return (
        not _is_bullet(line)
        and len(line) <= 80
        and len(line.split()) <= 10
        and (line[0].isupper() or line[0].isdigit())
        and not line.endswith((".", ",", ";"))
    )


def _collect_entries(lines: list[str], allow_single_year: bool = False) -> list[dict]:
    anchors = [
        i
        for i, line in enumerate(lines)
        if not _is_bullet(line)
        and len(line) <= 140
        and (
            DATE_RANGE_RE.search(line)
            or (allow_single_year and len(line) <= 100 and YEAR_RE.search(line))
        )
    ]

    info = []
    for n, i in enumerate(anchors):
        line = lines[i]
        m = DATE_RANGE_RE.search(line)
        if m:
            start, end = _norm_date(m.group("start")), _norm_date(m.group("end"))
            rest = f"{line[: m.start()]} {line[m.end():]}"
        else:
            ym = YEAR_RE.search(line)
            start, end = None, ym.group(0)  # type: ignore[union-attr]
            rest = f"{line[: ym.start()]} {line[ym.end():]}"  # type: ignore[union-attr]

        parts = _split_header(rest)
        back: list[str] = []
        if len(parts) < 2:
            prev_anchor = anchors[n - 1] if n else -1
            j = i - 1
            while j > prev_anchor and len(back) < 2 and _header_like(lines[j]):
                back.insert(0, lines[j])
                j -= 1
        back_parts = [p for line_ in back for p in _split_header(line_)]
        info.append(
            {
                "anchor": i,
                "header_start": i - len(back),
                "parts": back_parts + parts,
                "start": start,
                "end": end,
            }
        )

    entries = []
    for n, item in enumerate(info):
        stop = info[n + 1]["header_start"] if n + 1 < len(info) else len(lines)
        body = lines[item["anchor"] + 1 : stop]
        entries.append(
            {
                "parts": item["parts"],
                "start": item["start"],
                "end": item["end"],
                "description": "\n".join(_merge_wrapped(body))[:3000],
            }
        )
    return entries


def _classify_job(parts: list[str]) -> tuple[str | None, str | None]:
    title = company = None
    for p in parts:
        if title is None and TITLE_RE.search(p):
            title = p
        elif company is None and COMPANY_RE.search(p):
            company = p
    rest = [
        p for p in parts
        if p not in (title, company) and not LOCATION_ONLY_RE.fullmatch(p)
    ]
    if title is None and rest:
        title = rest.pop(0)
    if company is None and rest:
        company = rest.pop(0)
    return title, company


def _parse_experience(lines: list[str]) -> list[dict]:
    out = []
    for e in _collect_entries(lines):
        title, company = _classify_job(e["parts"])
        if not (title or company):
            continue
        item = {
            "company": company,
            "title": title,
            "description": e["description"],
            "start_date": e["start"],
            "end_date": e["end"],
        }
        out.append({k: v for k, v in item.items() if v})
    return out[:15]


def _parse_education(lines: list[str]) -> list[dict]:
    out = []
    for e in _collect_entries(lines, allow_single_year=True):
        parts = [p for p in e["parts"] if not LOCATION_ONLY_RE.fullmatch(p)]
        if not parts:
            continue
        institution = next((p for p in parts if INSTITUTION_RE.search(p)), None)
        rest = [p for p in parts if p != institution]
        qualification = rest[0] if rest else None
        if institution is None and len(parts) > 1:
            institution, qualification = parts[1], parts[0]
        item = {
            "institution": institution or (parts[0] if not qualification else None),
            "qualification": qualification,
            "start_date": e["start"],
            "end_date": e["end"],
        }
        item = {k: v for k, v in item.items() if v}
        if item:
            out.append(item)
    return out[:10]


def _parse_projects(lines: list[str]) -> list[dict]:
    projects: list[dict] = []
    cur: dict | None = None
    last_bullet = False
    for line in lines:
        text = _strip_bullet(line)
        if not text:
            continue
        bullet = _is_bullet(line)
        is_title = (
            not bullet
            and _header_like(line)
            and not URL_RE.search(text)
            and (
                cur is None
                or last_bullet
                or (cur["plain"] >= 1 and len(text.split()) <= 6)
            )
        )
        if is_title:
            parts = _split_header(text)
            cur = {"name": parts[0] if parts else text, "desc": [], "text": text, "plain": 0}
            if len(parts) > 1:
                cur["desc"].append(" | ".join(parts[1:]))
            projects.append(cur)
        elif cur is not None:
            if not bullet and text[0].islower() and cur["desc"]:
                cur["desc"][-1] = f"{cur['desc'][-1]} {text}"  # wrapped line
            else:
                cur["desc"].append(text)
                if not bullet:
                    cur["plain"] += 1
            cur["text"] += f" {text}"
        last_bullet = bullet

    out = []
    for p in projects:
        item = {"name": p["name"][:150], "description": "\n".join(p["desc"])[:2000]}
        if m := URL_RE.search(p["text"]):
            item["url"] = _with_scheme(m.group(0))
        out.append({k: v for k, v in item.items() if v})
    return out[:10]


def _parse_certifications(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        text = _strip_bullet(line)
        if not 4 <= len(text) <= 150:
            continue
        date = None
        if ym := YEAR_RE.search(text):
            date = ym.group(0)
            text = f"{text[: ym.start()]} {text[ym.end():]}"
        by = re.split(r"\s+by\s+", text, maxsplit=1, flags=re.I)
        parts = _split_header(by[0])
        name = parts[0] if parts else None
        issuer = parts[1] if len(parts) > 1 else (by[1].strip(" ,.-") if len(by) > 1 else None)
        if not name:
            continue
        item = {"name": name, "issuer": issuer, "date": date}
        out.append({k: v for k, v in item.items() if v})
    return out[:15]


# ----- main entry point -----------------------------------------------------
def _with_scheme(url: str) -> str:
    url = url.rstrip("/.,")
    return url if url.lower().startswith("http") else f"https://{url}"


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

    links: dict[str, str] = {}
    if m := LINKEDIN_RE.search(text):
        result["linkedin_url"] = links["linkedin"] = _with_scheme(m.group(0))
    if m := GITHUB_RE.search(text):
        result["github_url"] = links["github"] = _with_scheme(m.group(0))
    for m in URL_RE.finditer(text):
        url = m.group(0)
        if not re.search(r"linkedin\.com|github\.com|mailto:", url, re.I):
            if "@" not in url:
                links["portfolio"] = _with_scheme(url)
                break
    if "portfolio" not in links:
        domain_re = re.compile(
            r"(?<![\w@/.])((?:[\w-]+\.)+(?:dev|io|me|co\.ke|com|net|org|app|tech)(?:/[^\s|,;]*)?)",
            re.I,
        )
        for line in header:
            for m in domain_re.finditer(EMAIL_RE.sub(" ", line)):
                if not re.search(r"linkedin|github", m.group(1), re.I):
                    links["portfolio"] = _with_scheme(m.group(1))
                    break
            if "portfolio" in links:
                break
    if links:
        result["links"] = links

    name_index = None
    for i, line in enumerate(header[:6]):
        if _looks_like_name(line):
            full = " ".join(line.replace(",", " ").split())
            result["full_name"] = full.title() if line.isupper() else full
            parts = result["full_name"].split()
            result["first_name"] = parts[0]
            result["last_name"] = " ".join(parts[1:])
            name_index = i
            break

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
            result["target_roles"] = [candidate]

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
    if experience := _parse_experience(sections.get("experience", [])):
        result["experience"] = experience
    if education := _parse_education(sections.get("education", [])):
        result["education"] = education
    if projects := _parse_projects(sections.get("projects", [])):
        result["projects"] = projects
    if certs := _parse_certifications(sections.get("certifications", [])):
        result["certifications"] = certs

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