from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentAdmin
from app.db.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobRead, JobSearchResult
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




@router.get("/search", response_model=JobSearchResult)
def search_jobs(
    q: str = Query(default="", max_length=255),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search all stored jobs and return one page plus the total match count."""
    statement = select(Job)
    count_statement = select(func.count()).select_from(Job)

    term = q.strip()
    if term:
        pattern = f"%{term}%"
        search_filter = or_(
            Job.title.ilike(pattern),
            Job.company.ilike(pattern),
            Job.location.ilike(pattern),
        )
        statement = statement.where(search_filter)
        count_statement = count_statement.where(search_filter)

    total = db.scalar(count_statement) or 0
    items = db.scalars(
        statement
        .order_by(Job.created_at.desc(), Job.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    return {
        "items": items,
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
