"""Prepare immutable, human-reviewable application execution records."""

import hashlib
import os
import secrets
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_batch import ApplicationBatch, ApplicationBatchItem
from app.models.candidate_answer import CandidateAnswer
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


def _detect_ats_platform(url: str) -> str:
    """Identify only ATS platforms explicitly supported by the extension."""
    hostname = (urlsplit(url).hostname or "").lower()

    if hostname in {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
    }:
        return "greenhouse"

    return "unsupported"


def _normalise_greenhouse_job_url(url: str) -> tuple | None:
    """Return comparable URL parts for a valid HTTPS Greenhouse job URL."""
    try:
        validated_url = _validate_target_url(url)
        parsed = urlsplit(validated_url)

        if parsed.scheme.lower() != "https":
            return None

        if _detect_ats_platform(validated_url) != "greenhouse":
            return None

        return (
            (parsed.hostname or "").lower(),
            parsed.port or 443,
            parsed.path.rstrip("/") or "/",
            parsed.query,
        )
    except (HTTPException, ValueError):
        return None


def _existing_execution(
    db: Session,
    user_id: str,
    idempotency_key: str,
    application_id: int,
    resume_id: int,
    cover_letter_draft_id: int | None,
    batch_item_id: int | None,
    candidate_answer_ids: list[int],
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
        and sorted(
            (existing.application_payload or {}).get("candidate_answer_ids", [])
        ) == candidate_answer_ids
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
    candidate_answer_ids: list[int] | None = None,
) -> ApplicationExecution:
    """Validate ownership and create a reviewable execution snapshot."""

    key = idempotency_key.strip()
    selected_answer_ids = sorted(candidate_answer_ids or [])
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
        selected_answer_ids,
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

    source_url = job.source_url

    application_url = (
        _validate_target_url(job.application_url)
        if job.application_url is not None
        else None
    )

    # Unsupported jobs still need a safe reference URL for review.
    target_url = application_url or _validate_target_url(source_url)

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

    candidate_answers = []
    if selected_answer_ids:
        candidate_answers = db.scalars(
            select(CandidateAnswer).where(
                CandidateAnswer.id.in_(selected_answer_ids),
                CandidateAnswer.user_id == user_id,
                CandidateAnswer.is_user_authored.is_(True),
                CandidateAnswer.is_approved.is_(True),
            )
        ).all()

        if len(candidate_answers) != len(selected_answer_ids):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Every selected candidate answer must belong to you "
                    "and be confirmed as user-authored and approved."
                ),
            )

        answers_by_id = {answer.id: answer for answer in candidate_answers}
        candidate_answers = [
            answers_by_id[answer_id] for answer_id in selected_answer_ids
        ]

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
        "source_url": source_url,
        "application_url": application_url,
        "employment_type": job.employment_type,
        "source_name": job.source_name,
        "remote_type": job.remote_type,
        "eligible_countries": job.eligible_countries,
        "eligibility_status": job.eligibility_status,
        "eligibility_evidence_url": job.eligibility_evidence_url,
        "eligibility_evidence": job.eligibility_evidence,
    }

    cover_letter_content = cover_letter.content if cover_letter else None

    # Candidate answers are included only when explicitly selected and
    # confirmed as user-authored and approved by this user.
    application_payload = {
        "job": job_snapshot,
        "resume": {
            "resume_id": resume.id,
            "filename": resume.original_filename,
            "sha256": resume_sha256,
        },
        "cover_letter": cover_letter_content,
        "candidate_answer_ids": selected_answer_ids,
        "candidate_answers": [
            {
                "id": answer.id,
                "question_key": answer.question_key,
                "question_label": answer.question_label,
                "answer": answer.answer,
            }
            for answer in candidate_answers
        ],
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
        ats_platform=(
            _detect_ats_platform(application_url)
            if application_url is not None
            else "unsupported"
        ),
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
            selected_answer_ids,
        )
        if existing is not None:
            return existing
        raise


def review_application_execution(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
) -> ApplicationExecution:
    """Record that the owner has reviewed the prepared application."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(status_code=404, detail="Application execution not found.")

    if execution.status != "prepared":
        raise HTTPException(
            status_code=409,
            detail="Only prepared executions can be reviewed.",
        )

    if execution.reviewed_at is None:
        execution.reviewed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(execution)

    return execution


def approve_application_execution(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
) -> ApplicationExecution:
    """Atomically approve a reviewed execution."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Application execution not found.",
        )

    if execution.status != "prepared":
        raise HTTPException(
            status_code=409,
            detail="Only prepared executions can be approved.",
        )

    if execution.reviewed_at is None:
        raise HTTPException(
            status_code=409,
            detail="Review the application execution before approving it.",
        )

    approved_at = datetime.now(timezone.utc)

    # The conditions are checked again by the database during the update.
    # This prevents two concurrent requests from approving the same execution.
    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.status == "prepared",
            ApplicationExecution.reviewed_at.is_not(None),
        )
        .values(
            status="approved",
            approved_at=approved_at,
        )
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This execution has already been approved or changed.",
        )

    db.commit()
    db.refresh(execution)

    return execution


def create_extension_handoff(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
) -> dict[str, Any]:
    """Issue a short-lived, single-use credential for an approved execution."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Application execution not found.",
        )

    if execution.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only approved executions can be handed off to the extension.",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Reissuing replaces the previous credential and invalidates it.
    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.status == "approved",
        )
        .values(
            extension_handoff_token_hash=token_hash,
            extension_handoff_expires_at=expires_at,
            extension_handoff_redeemed_at=None,
        )
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This execution has changed. Request a new handoff.",
        )

    db.commit()

    # The raw token is returned once and is never persisted.
    return {
        "token": token,
        "expires_at": expires_at,
    }

def redeem_extension_handoff(
    db: Session,
    *,
    token: str,
    active_url: str,
) -> dict[str, Any]:
    """Atomically redeem and invalidate a single-use handoff credential."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)

    execution_id = db.scalar(
        select(ApplicationExecution.id).where(
            ApplicationExecution.extension_handoff_token_hash == token_hash,
        )
    )

    if execution_id is None:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or already used handoff credential.",
        )

    execution = db.get(ApplicationExecution, execution_id)

    if execution is None:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or already used handoff credential.",
        )

    expected_url = _normalise_greenhouse_job_url(execution.target_url)
    supplied_url = _normalise_greenhouse_job_url(active_url)

    if (
        execution.ats_platform != "greenhouse"
        or expected_url is None
        or supplied_url is None
        or expected_url != supplied_url
    ):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Open the exact Greenhouse job associated with this execution.",
        )

    # Only one request can redeem the credential. Clear its hash in the
    # same conditional update so it cannot be reused or retained afterward.
    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.extension_handoff_token_hash == token_hash,
            ApplicationExecution.extension_handoff_expires_at > now,
            ApplicationExecution.extension_handoff_redeemed_at.is_(None),
            ApplicationExecution.status == "approved",
        )
        .values(
            extension_handoff_redeemed_at=now,
            extension_handoff_token_hash=None,
        )
        .execution_options(synchronize_session=False)
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or already used handoff credential.",
        )

    execution = db.get(ApplicationExecution, execution_id)

    if execution is None:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or already used handoff credential.",
        )

    response = {
        "execution_id": execution.id,
        "target_url": execution.target_url,
        "ats_platform": execution.ats_platform,
        "job_snapshot": execution.job_snapshot,
        "resume_filename": execution.resume_filename_snapshot,
        "cover_letter": execution.cover_letter_snapshot,
        "candidate_answers": (
            execution.application_payload or {}
        ).get("candidate_answers", []),
    }

    db.commit()
    return response


def start_application_submission(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
) -> ApplicationExecution:
    """Atomically claim one approved execution for a submission attempt.

    This records the start of an attempt only. It does not contact the
    employer's website or submit an application.
    """
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Application execution not found.",
        )

    if execution.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only approved executions can start a submission attempt.",
        )

    if execution.submission_attempt_id is not None:
        raise HTTPException(
            status_code=409,
            detail="A submission attempt has already been started.",
        )

    attempt_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    # Recheck the conditions inside the UPDATE to protect against
    # concurrent requests trying to start the same execution.
    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.status == "approved",
            ApplicationExecution.submission_attempt_id.is_(None),
        )
        .values(
            status="submitting",
            submission_attempt_id=attempt_id,
            submission_started_at=started_at,
        )
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This execution has already started or changed.",
        )

    db.commit()
    db.refresh(execution)

    return execution


def complete_application_submission(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
    submission_reference: str | None = None,
) -> ApplicationExecution:
    """Record a confirmed submission and update application tracking."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Application execution not found.",
        )

    if (
        execution.status != "submitting"
        or execution.submission_attempt_id is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Only an active submission attempt can be completed.",
        )

    submitted_at = datetime.now(timezone.utc)

    # Claim the completion atomically. A second outcome request cannot
    # complete an execution that has already changed state.
    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.status == "submitting",
            ApplicationExecution.submission_attempt_id.is_not(None),
            ApplicationExecution.submitted_at.is_(None),
        )
        .values(
            status="submitted",
            submitted_at=submitted_at,
            submission_reference=submission_reference,
        )
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This submission attempt has already been completed or changed.",
        )

    # Only advance a saved application. Never downgrade an existing
    # applied, interview, offer, or rejected status.
    db.execute(
        update(Application)
        .where(
            Application.id == execution.application_id,
            Application.user_id == user_id,
            Application.status == "saved",
        )
        .values(
            status="applied",
            applied_at=submitted_at,
        )
    )

    db.commit()
    db.refresh(execution)

    return execution


def fail_application_submission(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
    failure_reason: str,
) -> ApplicationExecution:
    """Record a definitive failure for an active submission attempt."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Application execution not found.",
        )

    if (
        execution.status != "submitting"
        or execution.submission_attempt_id is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Only an active submission attempt can be marked as failed.",
        )

    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.status == "submitting",
            ApplicationExecution.submission_attempt_id.is_not(None),
        )
        .values(
            status="failed",
            failure_reason=failure_reason,
        )
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This submission attempt has already ended or changed.",
        )

    db.commit()
    db.refresh(execution)

    return execution


def flag_application_submission_for_attention(
    db: Session,
    *,
    user_id: str,
    execution_id: int,
    reason: str,
) -> ApplicationExecution:
    """Record an uncertain submission outcome requiring human review."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Application execution not found.",
        )

    if (
        execution.status != "submitting"
        or execution.submission_attempt_id is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Only an active submission attempt can require attention.",
        )

    result = db.execute(
        update(ApplicationExecution)
        .where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.status == "submitting",
            ApplicationExecution.submission_attempt_id.is_not(None),
        )
        .values(
            status="needs_attention",
            failure_reason=reason,
        )
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This submission attempt has already ended or changed.",
        )

    db.commit()
    db.refresh(execution)

    return execution
