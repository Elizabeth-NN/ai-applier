import os
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


class GenerateCoverLetterRequest(BaseModel):
    application_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)


class GeneratedCoverLetter(BaseModel):
    content: str


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
    except (OSError, ValueError, BadZipFile, ET.ParseError) as exc:
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

    return text[:16000]


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

Rules:
- Use only facts supported by the resume.
- Do not invent qualifications, employers, achievements, dates, or metrics.
- Connect relevant experience and skills to the actual job requirements.
- Do not claim the applicant has experience that the resume does not establish.
- Use a professional, natural tone and avoid generic filler.
- Return only the cover letter, without explanations or markdown fences.
- Leave out postal addresses and other personal details not supplied.

JOB TITLE: {job.title}
COMPANY: {job.company or "Not specified"}

JOB DESCRIPTION:
{description[:10000]}

RESUME TEXT:
{resume_text}
""".strip()

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )

    try:
        response = httpx.post(
            endpoint,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 1200,
                },
            },
            timeout=45.0,
        )
        response.raise_for_status()
        data = response.json()

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="AI generation timed out. Please try again.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="The AI provider could not generate the letter. Check the API key, model, quota, and try again.",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not communicate with the AI provider.",
        ) from exc

    candidates = data.get("candidates") or []
    parts = (
        candidates[0].get("content", {}).get("parts", [])
        if candidates
        else []
    )
    content = "\n".join(
        part.get("text", "") for part in parts if part.get("text")
    ).strip()

    if not content:
        raise HTTPException(
            status_code=502,
            detail="The AI provider returned an empty letter. Please try again.",
        )

    return GeneratedCoverLetter(content=content[:20000])
