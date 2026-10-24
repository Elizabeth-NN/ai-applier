from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentAdmin
from app.db.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobRead
from app.services.job_ingestion import ingest_jobicy_jobs
from app.services.jobicy_adapter import JobicyAPIError
from app.services.job_status_sync import sync_jobicy_statuses


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


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job
