from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.application import Application
from app.models.application_batch import ApplicationBatch, ApplicationBatchItem
from app.models.application_campaign import ApplicationCampaign
from app.schemas.application_batch import (
    ApplicationBatchCreate,
    ApplicationBatchItemSelection,
    ApplicationBatchRead,
)


router = APIRouter(
    prefix="/api/application-batches",
    tags=["Application Batches"],
)


def _get_owned_batch(
    db: Session,
    batch_id: int,
    user_id: str,
) -> ApplicationBatch:
    statement = (
        select(ApplicationBatch)
        .options(
            selectinload(ApplicationBatch.items).selectinload(
                ApplicationBatchItem.job
            )
        )
        .where(
            ApplicationBatch.id == batch_id,
            ApplicationBatch.user_id == user_id,
        )
    )
    batch = db.scalar(statement)

    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application batch not found",
        )

    return batch


def _ensure_draft(batch: ApplicationBatch) -> None:
    if batch.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft batches can be modified",
        )


@router.post(
    "",
    response_model=ApplicationBatchRead,
    status_code=status.HTTP_201_CREATED,
)
def create_application_batch(
    payload: ApplicationBatchCreate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    if len(payload.job_ids) != len(set(payload.job_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duplicate job IDs are not allowed",
        )

    if payload.campaign_id is not None:
        campaign = db.scalar(
            select(ApplicationCampaign.id).where(
                ApplicationCampaign.id == payload.campaign_id,
                ApplicationCampaign.user_id == user_id,
            )
        )
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application campaign not found",
            )

    statement = (
        select(Application.job_id)
        .where(
            Application.user_id == user_id,
            Application.job_id.in_(payload.job_ids),
        )
    )
    saved_job_ids = set(db.scalars(statement).all())

    missing_job_ids = sorted(set(payload.job_ids) - saved_job_ids)
    if missing_job_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Every job must already be saved by you",
                "job_ids": missing_job_ids,
            },
        )

    batch = ApplicationBatch(
        user_id=user_id,
        campaign_id=payload.campaign_id,
        name=payload.name.strip(),
    )

    if not batch.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch name cannot be blank",
        )

    batch.items = [
        ApplicationBatchItem(job_id=job_id, selected=False)
        for job_id in payload.job_ids
    ]

    db.add(batch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create the application batch",
        )

    return _get_owned_batch(db, batch.id, user_id)


@router.get("", response_model=list[ApplicationBatchRead])
def list_application_batches(
    user_id: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(ApplicationBatch)
        .options(
            selectinload(ApplicationBatch.items).selectinload(
                ApplicationBatchItem.job
            )
        )
        .where(ApplicationBatch.user_id == user_id)
        .order_by(ApplicationBatch.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.get("/{batch_id}", response_model=ApplicationBatchRead)
def get_application_batch(
    batch_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    return _get_owned_batch(db, batch_id, user_id)


@router.patch(
    "/{batch_id}/items/{item_id}",
    response_model=ApplicationBatchRead,
)
def update_application_batch_item(
    batch_id: int,
    item_id: int,
    payload: ApplicationBatchItemSelection,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    batch = _get_owned_batch(db, batch_id, user_id)
    _ensure_draft(batch)

    item = next(
        (item for item in batch.items if item.id == item_id),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch item not found",
        )

    item.selected = payload.selected
    db.commit()

    return _get_owned_batch(db, batch_id, user_id)


@router.post(
    "/{batch_id}/approve",
    response_model=ApplicationBatchRead,
)
def approve_application_batch(
    batch_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    batch = _get_owned_batch(db, batch_id, user_id)
    _ensure_draft(batch)

    selected_items = [item for item in batch.items if item.selected]
    if not selected_items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one job before approving the batch",
        )

    approved_at = datetime.now(timezone.utc)
    batch.status = "approved"
    batch.approved_at = approved_at

    for item in selected_items:
        item.approved_at = approved_at

    db.commit()

    return _get_owned_batch(db, batch_id, user_id)
