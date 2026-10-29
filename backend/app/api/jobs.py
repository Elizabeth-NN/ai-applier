from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pathlib import Path
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentAdmin, CurrentUser
from app.api import resumes as resumes_api
from app.db.dependencies import get_db
from app.models.job import Job
from app.services.resume_text import extract_resume_text
from app.services.resume_job_matching import score_resume_job_match
from app.schemas.job import (
    EligibilityVerificationRequest,
    JobCreate,
    JobRead,
    JobSearchResult,
    ResumeJobMatchResult,
)
from app.schemas.himalayas_ingestion import HimalayasBatchIngestionResult
from app.services.job_ingestion import (
    ingest_himalayas_jobs,
    ingest_jobicy_jobs,
)
from app.services.himalayas_adapter import HimalayasAPIError
from app.services.jobicy_adapter import JobicyAPIError
from app.services.job_status_sync import sync_jobicy_statuses
from app.services.job_relevance import score_job_relevance


router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    payload: JobCreate,
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    job = Job(**payload.model_dump())

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


@router.get("", response_model=list[JobRead])
def list_jobs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(Job)
        .order_by(Job.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()



@router.get("/search", response_model=JobSearchResult)
def search_jobs(
    q: str = Query(default="", max_length=255),
    remote_type: str | None = Query(
        default=None,
        pattern="^(remote|hybrid|onsite|unknown)$",
    ),
    eligibility_status: str | None = Query(
        default=None,
        pattern="^(eligible|ineligible|unknown)$",
    ),
    listing_status: str | None = Query(
        default=None,
        pattern="^(active|closed|unknown)$",
    ),
    sort_by: str = Query(default="newest", pattern="^(newest|relevance)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search stored jobs using text and discovery metadata."""
    statement = select(Job)
    count_statement = select(func.count()).select_from(Job)
    filters = []

    term = q.strip()
    if term:
        pattern = f"%{term}%"
        filters.append(
            or_(
                Job.title.ilike(pattern),
                Job.company.ilike(pattern),
                Job.location.ilike(pattern),
            )
        )

    if remote_type == "unknown":
        filters.append(
            or_(
                Job.remote_type.is_(None),
                Job.remote_type == "unknown",
            )
        )
    elif remote_type is not None:
        filters.append(Job.remote_type == remote_type)

    if eligibility_status is not None:
        filters.append(Job.eligibility_status == eligibility_status)

    if listing_status is not None:
        filters.append(Job.listing_status == listing_status)

    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)

    total = db.scalar(count_statement) or 0

    if sort_by == "relevance":
        # Score every matching job before pagination so the order is global,
        # not limited to the newest page.
        items = db.scalars(
            statement.order_by(Job.created_at.desc(), Job.id.desc())
        ).all()
    else:
        # Preserve the existing efficient newest-first behavior.
        items = db.scalars(
            statement
            .order_by(Job.created_at.desc(), Job.id.desc())
            .offset(skip)
            .limit(limit)
        ).all()

    search_items = []
    for job in items:
        job_data = JobRead.model_validate(job).model_dump()
        relevance = score_job_relevance(
            {
                "title": job.title,
                "description": job.description,
                "employment_type": job.employment_type,
            }
        )
        search_items.append(
            {
                **job_data,
                "relevance_score": relevance["score"],
                "matched_role_families": relevance["matched_role_families"],
                "relevance_reasons": relevance["reasons"],
            }
        )

    if sort_by == "relevance":
        search_items.sort(
            key=lambda item: (
                item["relevance_score"],
                item["created_at"],
                item["id"],
            ),
            reverse=True,
        )
        search_items = search_items[skip : skip + limit]

    return {
        "items": search_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/ingest/jobicy")
def refresh_jobicy_jobs(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Import and refresh jobs from the public Jobicy feed."""
    try:
        return ingest_jobicy_jobs(db)
    except JobicyAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Jobicy could not provide a complete, valid feed.",
        ) from exc


@router.post("/ingest/himalayas")
def refresh_himalayas_jobs(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Import and refresh jobs from the public Himalayas feed."""
    try:
        return ingest_himalayas_jobs(db)
    except HimalayasAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Himalayas could not provide a complete, valid feed.",
        ) from exc


@router.post("/sync/jobicy-status")
def sync_jobicy_listing_statuses(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Synchronize active, closed, and unknown status for imported listings."""
    try:
        return sync_jobicy_statuses(db)
    except JobicyAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Jobicy listing statuses could not be verified.",
        ) from exc


@router.post("/{job_id}/eligibility", response_model=JobRead)
def verify_job_eligibility(
    job_id: int,
    payload: EligibilityVerificationRequest,
    admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Record an admin's evidence-backed decision about Kenya eligibility."""
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.eligibility_status = payload.eligibility_status

    if payload.eligibility_status == "unknown":
        job.eligibility_evidence_url = None
        job.eligibility_evidence = None
        job.eligibility_verified_at = None
        job.eligibility_verified_by = None
    else:
        job.eligibility_evidence_url = str(payload.evidence_url)
        job.eligibility_evidence = payload.evidence.strip()
        job.eligibility_verified_at = datetime.now(timezone.utc)
        job.eligibility_verified_by = admin_id

        countries = list(job.eligible_countries or [])
        kenya_names = {"kenya"}

        if payload.eligibility_status == "eligible":
            if not any(
                country.strip().casefold() in kenya_names
                for country in countries
            ):
                countries.append("Kenya")
            job.eligible_countries = countries
        elif job.eligible_countries is not None:
            job.eligible_countries = [
                country
                for country in countries
                if country.strip().casefold() not in kenya_names
            ]

    db.commit()
    db.refresh(job)
    return job


@router.get("/matches", response_model=ResumeJobMatchResult)
def match_jobs_to_resume(
    user_id: CurrentUser,
    resume_id: int = Query(..., ge=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Rank stored jobs by text overlap with the authenticated user's resume."""
    # Resolve the resume using both its ID and the authenticated owner.
    resume = resumes_api._owned_resume(resume_id, user_id, db)
    storage_dir = resumes_api.STORAGE_DIR.resolve()
    stored_path = (storage_dir / resume.storage_key).resolve()

    if stored_path.parent != storage_dir or not stored_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume file not found",
        )

    resume_text = extract_resume_text(
        stored_path,
        resume.original_filename,
    )

    jobs = db.scalars(select(Job)).all()
    matches = []

    for job in jobs:
        match = score_resume_job_match(
            resume_text,
            title=job.title,
            description=job.description,
            employment_type=job.employment_type,
        )
        job_data = JobRead.model_validate(job).model_dump()
        matches.append({**job_data, **match})

    # Rank the full result set before applying pagination.
    matches.sort(
        key=lambda item: (
            item["match_score"],
            item["created_at"],
            item["id"],
        ),
        reverse=True,
    )

    return {
        "resume_id": resume.id,
        "resume_filename": resume.original_filename,
        "items": matches[skip : skip + limit],
        "total": len(matches),
        "skip": skip,
        "limit": limit,
    }


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.post(
    "/ingest/himalayas/batch",
    response_model=HimalayasBatchIngestionResult,
    responses={
        401: {"description": "Authentication is required."},
        403: {"description": "Admin access is required."},
        502: {"description": "The Himalayas API returned an invalid response or failed."},
    },
)
def refresh_himalayas_batch(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
    max_pages: int = Query(default=5, ge=1, le=25),
):
    """Import or resume a bounded batch from the Himalayas feed."""
    from app.services.job_ingestion import ingest_himalayas_batch

    try:
        return ingest_himalayas_batch(db, max_pages=max_pages)
    except HimalayasAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Himalayas could not provide a valid batch.",
        ) from exc
