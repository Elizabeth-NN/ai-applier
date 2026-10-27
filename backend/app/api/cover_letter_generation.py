import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.core.config import settings
from app.db.dependencies import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume


router = APIRouter(
    prefix="/api/cover-letter-generation",
    tags=["Cover Letter Generation"],
)


COVER_LETTER_RE = re.compile(
    r"<cover_letter>\s*(.*?)\s*</cover_letter>", re.DOTALL | re.IGNORECASE
)

SYSTEM_INSTRUCTION = """You are an expert career coach who writes tailored cover letters.

Rules:
- Use only facts supported by the resume.
- Do not invent qualifications, employers, achievements, dates, or metrics.
- Never use words like "extensive", "expert", "seasoned" or "specialize" unless
  the resume clearly supports them. If the applicant is junior or early-career,
  present them honestly as a growing engineer with strong project work.
- If the resume lists professional experience, mention that employer and role
  by name, with one concrete thing the applicant did there.
- Name at most two or three specific projects and say what was built, not just
  the tools used.
- If the job requires something the resume does not show (a technology, or years
  of experience), do not claim it. Briefly acknowledge the gap by pointing to the
  closest related experience and showing willingness to learn.
- Avoid filler such as "valuable asset", "thrive in collaborative environments",
  "bridge the gap" and "proactive". Do not just repeat the job description's
  wording back.
- Use a professional, natural tone.
- Leave out postal addresses and other personal details not supplied.
- Keep the letter under 300 words.

Output format:
- Do NOT output analysis, notes, checklists, drafts, or reasoning.
- Output ONLY the final letter, wrapped in <cover_letter> and </cover_letter> tags.
- Start with the greeting and end with the sign-off. No markdown fences."""


class GenerateCoverLetterRequest(BaseModel):
    application_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)


class GeneratedCoverLetter(BaseModel):
    content: str


def _generation_config() -> dict:
    config: dict = {"temperature": 0.4, "maxOutputTokens": 2048}
    # Disable thinking on Flash models so the token budget goes to the letter.
    # (Not supported by 2.5 Pro or non-thinking models, so only set it here.)
    if "2.5-flash" in settings.gemini_model:
        config["thinkingConfig"] = {"thinkingBudget": 0}
    return config


def _extract_resume_text(path: Path, filename: str) -> str:
    """Extract readable text from a privately stored PDF or DOCX."""
    try:
        content = path.read_bytes()

        if filename.lower().endswith(".pdf"):
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise HTTPException(
                    status_code=422,
                    detail="The selected PDF is encrypted. Upload an unlocked PDF.",
                )

            text = "\n".join(page.extract_text() or "" for page in reader.pages)

        elif filename.lower().endswith(".docx"):
            with ZipFile(BytesIO(content)) as archive:
                xml_content = archive.read("word/document.xml")

            root = ET.fromstring(xml_content)
            namespace = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            }
            paragraphs = []

            for paragraph in root.findall(".//w:p", namespace):
                words = [
                    node.text or ""
                    for node in paragraph.findall(".//w:t", namespace)
                ]
                paragraphs.append("".join(words))

            text = "\n".join(paragraphs)

        else:
            raise HTTPException(
                status_code=422,
                detail="Only PDF and DOCX resumes are supported.",
            )

    except HTTPException:
        raise
    except (OSError, ValueError, BadZipFile, ET.ParseError, KeyError) as exc:
        raise HTTPException(
            status_code=422,
            detail="The selected resume could not be read. Upload a valid PDF or DOCX.",
        ) from exc

    text = text.strip()
    if len(text) < 40:
        raise HTTPException(
            status_code=422,
            detail="Not enough readable text was found. Try a text-based PDF or DOCX.",
        )

    return text[:8000]


@router.post("", response_model=GeneratedCoverLetter)
def generate_cover_letter(
    payload: GenerateCoverLetterRequest,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Generate an editable cover letter from an owned application and resume."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation is not configured. Set GEMINI_API_KEY in backend/.env.",
        )

    application = db.scalar(
        select(Application).where(
            Application.id == payload.application_id,
            Application.user_id == user_id,
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    job = db.get(Job, application.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    description = (job.description or "").strip()
    if len(description) < 40:
        raise HTTPException(
            status_code=422,
            detail="This job has no usable description. Choose a job with a description.",
        )

    resume = db.scalar(
        select(Resume).where(
            Resume.id == payload.resume_id,
            Resume.user_id == user_id,
        )
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")

    storage_dir = Path(
        os.environ.get(
            "RESUME_STORAGE_DIR",
            str(Path(__file__).resolve().parents[2] / "private_uploads"),
        )
    ).resolve()
    resume_path = (storage_dir / resume.storage_key).resolve()

    if resume_path.parent != storage_dir or not resume_path.is_file():
        raise HTTPException(status_code=404, detail="Stored resume file not found.")

    resume_text = _extract_resume_text(resume_path, resume.original_filename)

    prompt = f"""
Write a tailored cover letter for the job below using the supplied resume.

<job>
TITLE: {job.title}
COMPANY: {job.company or "Not specified"}

DESCRIPTION:
{description[:6000]}
</job>

<resume>
{resume_text}
</resume>
""".strip()

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )

    try:
        response = httpx.post(
            endpoint,
            headers={"x-goog-api-key": api_key},  # keeps the key out of URLs/logs
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": _generation_config(),
            },
            timeout=90.0,
        )
        response.raise_for_status()
        data = response.json()

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="AI generation timed out. Please try again.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        # Log provider diagnostics, but never log the request URL or API key.
        error_body = exc.response.text[:1500]
        print(
            "[cover-letter] Gemini HTTP error:",
            exc.response.status_code,
            error_body,
            flush=True,
        )
        raise HTTPException(
            status_code=502,
            detail="The AI provider could not generate the letter. Check backend logs for diagnostic details.",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not communicate with the AI provider.",
        ) from exc

    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(
            status_code=502,
            detail="The AI provider returned no result. Please try again.",
        )

    candidate = candidates[0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        raise HTTPException(
            status_code=502,
            detail="The AI response was cut off. Please try again.",
        )

    parts = candidate.get("content", {}).get("parts", [])
    raw_text = "\n".join(
        part["text"]
        for part in parts
        if part.get("text") and not part.get("thought")  # skip thought summaries
    ).strip()

    match = COVER_LETTER_RE.search(raw_text)
    if not match:
        # Model ignored the format (or leaked reasoning / was truncated).
        raise HTTPException(
            status_code=502,
            detail="The AI provider returned an unusable letter. Please try again.",
        )

    content = match.group(1).strip()
    if len(content) < 100:
        raise HTTPException(
            status_code=502,
            detail="The AI provider returned an empty letter. Please try again.",
        )

    return GeneratedCoverLetter(content=content[:20000])