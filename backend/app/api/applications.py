from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.models.application import Application
from app.models.job import Job
from app.schemas.application import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
)


router = APIRouter(
    prefix="/api/applications",
    tags=["Applications"],
)


@router.post(
    "",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
):
    job = db.get(Job, payload.job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    application = Application(
        job_id=payload.job_id,
        notes=payload.notes,
    )

    db.add(application)
    db.commit()
    db.refresh(application)

    return application


@router.get("", response_model=list[ApplicationRead])
def list_applications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(Application)
        .order_by(Application.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    application.status = payload.status

    if payload.status == "applied" and application.applied_at is None:
        application.applied_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(application)

    return application
