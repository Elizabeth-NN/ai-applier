from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.application import Application
from app.models.cover_letter_draft import CoverLetterDraft
from app.models.job import Job
from app.schemas.cover_letter_draft import (
    CoverLetterDraftCreate,
    CoverLetterDraftRead,
    CoverLetterDraftUpdate,
)


router = APIRouter(
    prefix="/api/cover-letter-drafts",
    tags=["Cover Letter Drafts"],
)


@router.post(
    "",
    response_model=CoverLetterDraftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_cover_letter_draft(
    payload: CoverLetterDraftCreate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    application = db.scalar(
        select(Application).where(
            Application.id == payload.application_id,
            Application.user_id == user_id,
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail="Application not found",
        )

    job = db.get(Job, application.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    generated_title = f"{job.title} — {job.company}"[:255]

    draft = CoverLetterDraft(
        application_id=application.id,
        user_id=user_id,
        title=payload.title or generated_title,
        content=payload.content,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@router.get("", response_model=list[CoverLetterDraftRead])
def list_cover_letter_drafts(
    user_id: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(CoverLetterDraft)
        .where(CoverLetterDraft.user_id == user_id)
        .order_by(CoverLetterDraft.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(statement).all()


@router.get("/{draft_id}", response_model=CoverLetterDraftRead)
def get_cover_letter_draft(
    draft_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    draft = db.scalar(
        select(CoverLetterDraft).where(
            CoverLetterDraft.id == draft_id,
            CoverLetterDraft.user_id == user_id,
        )
    )

    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    return draft


@router.patch("/{draft_id}", response_model=CoverLetterDraftRead)
def update_cover_letter_draft(
    draft_id: int,
    payload: CoverLetterDraftUpdate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    draft = db.scalar(
        select(CoverLetterDraft).where(
            CoverLetterDraft.id == draft_id,
            CoverLetterDraft.user_id == user_id,
        )
    )

    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    if payload.title is not None:
        draft.title = payload.title

    if payload.content is not None:
        draft.content = payload.content

    db.commit()
    db.refresh(draft)
    return draft
