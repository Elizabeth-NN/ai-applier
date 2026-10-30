"""Prepare immutable, human-reviewable application execution records."""

import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_batch import ApplicationBatch, ApplicationBatchItem
from app.models.application_execution import ApplicationExecution
from app.models.cover_letter_draft import CoverLetterDraft
from app.models.job import Job
from app.models.resume import Resume
from app.services.resume_text import extract_resume_text


def _resume_storage_dir() -> Path:
    return Path(
        os.environ.get(
            "RESUME_STORAGE_DIR",
            str(Path(__file__).resolve().parents[2] / "private_uploads"),
        )
    ).resolve()



def _validate_target_url(url: str | None) -> str:
    """Accept only absolute HTTP(S) URLs with a valid hostname and port."""
    if not url or len(url) > 2048 or any(char.isspace() for char in url):
        raise HTTPException(
            status_code=422,
            detail="This job does not have a valid application URL.",
        )

    try:
        parsed = urlsplit(url)
        # Accessing .port validates that the port is numeric and in range.
        port = parsed.port

        valid = (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid = False

    if not valid:
        raise HTTPException(
            status_code=422,
            detail="This job does not have a valid application URL.",
        )

    return url


def _existing_execution(
    db: Session,
    user_id: str,
    idempotency_key: str,
    application_id: int,
    resume_id: int,
    cover_letter_draft_id: int | None,
    batch_item_id: int | None,
) -> ApplicationExecution | None:
    """Return an existing matching request, or reject key reuse."""
    existing = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.idempotency_key == idempotency_key,
        )
    )

    if existing is None:
        return None

    same_request = (
        existing.application_id == application_id
        and existing.resume_id == resume_id
        and existing.cover_letter_draft_id == cover_letter_draft_id
        and existing.batch_item_id == batch_item_id
    )

    if not same_request:
        raise HTTPException(
            status_code=409,
            detail="This idempotency key was already used for a different preparation request.",
        )

    return existing


def prepare_application_execution(
    db: Session,
    *,
    user_id: str,
    application_id: int,
    resume_id: int,
    idempotency_key: str,
    cover_letter_draft_id: int | None = None,
    batch_item_id: int | None = None,
) -> ApplicationExecution:
    """Validate ownership and create a reviewable execution snapshot."""

    key = idempotency_key.strip()
    if not key or len(key) > 100:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must contain between 1 and 100 characters.",
        )

    existing = _existing_execution(
        db,
        user_id,
        key,
        application_id,
        resume_id,
        cover_letter_draft_id,
        batch_item_id,
    )
    if existing is not None:
        return existing

    application = db.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    job = db.get(Job, application.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    target_url = _validate_target_url(job.source_url)

    resume = db.scalar(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == user_id,
        )
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")

    storage_dir = _resume_storage_dir()
    resume_path = (storage_dir / resume.storage_key).resolve()

    if resume_path.parent != storage_dir or not resume_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored resume file not found.",
        )

    try:
        resume_bytes = resume_path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=422,
            detail="The selected resume file could not be read.",
        ) from exc

    if len(resume_bytes) != resume.size_bytes:
        raise HTTPException(
            status_code=422,
            detail="The stored resume file does not match its recorded size.",
        )

    # Validate that the file contains readable resume text.
    # The extracted text is deliberately not persisted in the execution record.
    extract_resume_text(resume_path, resume.original_filename)
    resume_sha256 = hashlib.sha256(resume_bytes).hexdigest()

    cover_letter = None
    if cover_letter_draft_id is not None:
        cover_letter = db.scalar(
            select(CoverLetterDraft).where(
                CoverLetterDraft.id == cover_letter_draft_id,
                CoverLetterDraft.user_id == user_id,
                CoverLetterDraft.application_id == application_id,
            )
        )
        if cover_letter is None:
            raise HTTPException(
                status_code=404,
                detail="Cover letter draft not found for this application.",
            )

    if batch_item_id is not None:
        batch_item = db.scalar(
            select(ApplicationBatchItem)
            .join(
                ApplicationBatch,
                ApplicationBatch.id == ApplicationBatchItem.batch_id,
            )
            .where(
                ApplicationBatchItem.id == batch_item_id,
                ApplicationBatchItem.job_id == job.id,
                ApplicationBatchItem.selected.is_(True),
                ApplicationBatchItem.approved_at.is_not(None),
                ApplicationBatch.user_id == user_id,
                ApplicationBatch.status == "approved",
                ApplicationBatch.approved_at.is_not(None),
            )
        )
        if batch_item is None:
            raise HTTPException(
                status_code=422,
                detail="The batch item must be selected and approved in one of your approved batches.",
            )

    job_snapshot = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "source_url": target_url,
        "employment_type": job.employment_type,
        "source_name": job.source_name,
        "remote_type": job.remote_type,
        "eligible_countries": job.eligible_countries,
        "eligibility_status": job.eligibility_status,
        "eligibility_evidence_url": job.eligibility_evidence_url,
        "eligibility_evidence": job.eligibility_evidence,
    }

    cover_letter_content = cover_letter.content if cover_letter else None

    # These are known facts and references only. Candidate answers and
    # additional personal information must be supplied and reviewed separately.
    application_payload = {
        "job": job_snapshot,
        "resume": {
            "resume_id": resume.id,
            "filename": resume.original_filename,
            "sha256": resume_sha256,
        },
        "cover_letter": cover_letter_content,
    }

    execution = ApplicationExecution(
        user_id=user_id,
        application_id=application.id,
        batch_item_id=batch_item_id,
        resume_id=resume.id,
        cover_letter_draft_id=cover_letter.id if cover_letter else None,
        resume_filename_snapshot=resume.original_filename,
        resume_sha256=resume_sha256,
        cover_letter_snapshot=cover_letter_content,
        job_snapshot=job_snapshot,
        application_payload=application_payload,
        target_url=target_url,
        ats_platform="unsupported",
        status="prepared",
        idempotency_key=key,
    )

    db.add(execution)

    try:
        db.commit()
        db.refresh(execution)
        return execution
    except IntegrityError:
        db.rollback()

        # A concurrent retry may have inserted the same key.
        existing = _existing_execution(
            db,
            user_id,
            key,
            application_id,
            resume_id,
            cover_letter_draft_id,
            batch_item_id,
        )
        if existing is not None:
            return existing
        raise
