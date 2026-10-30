"""API endpoints for preparing application executions."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.schemas.application_execution import (
    ApplicationExecutionComplete,
    ApplicationExecutionFail,
    ApplicationExecutionPrepare,
    ApplicationExecutionRead,
)
from app.services.application_preparation import (
    approve_application_execution,
    complete_application_submission,
    fail_application_submission,
    prepare_application_execution,
    review_application_execution,
    start_application_submission,
)


router = APIRouter(
    prefix="/api/application-executions",
    tags=["Application Executions"],
)


@router.post(
    "/prepare",
    response_model=ApplicationExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
def prepare_execution(
    payload: ApplicationExecutionPrepare,
    user_id: CurrentUser,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=100,
    ),
    db: Session = Depends(get_db),
):
    """Prepare an application for human review without submitting it."""
    return prepare_application_execution(
        db,
        user_id=user_id,
        application_id=payload.application_id,
        resume_id=payload.resume_id,
        cover_letter_draft_id=payload.cover_letter_draft_id,
        batch_item_id=payload.batch_item_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/{execution_id}/review",
    response_model=ApplicationExecutionRead,
)
def review_execution(
    execution_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Record that the authenticated user reviewed the prepared payload."""
    return review_application_execution(
        db,
        user_id=user_id,
        execution_id=execution_id,
    )


@router.post(
    "/{execution_id}/approve",
    response_model=ApplicationExecutionRead,
)
def approve_execution(
    execution_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Explicitly approve a previously reviewed application execution."""
    return approve_application_execution(
        db,
        user_id=user_id,
        execution_id=execution_id,
    )

@router.post(
    "/{execution_id}/start",
    response_model=ApplicationExecutionRead,
)
def start_execution(
    execution_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Record the start of one approved submission attempt."""
    return start_application_submission(
        db,
        user_id=user_id,
        execution_id=execution_id,
    )



@router.post(
    "/{execution_id}/complete",
    response_model=ApplicationExecutionRead,
)
def complete_execution(
    execution_id: int,
    payload: ApplicationExecutionComplete,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Record a confirmed application submission."""
    return complete_application_submission(
        db,
        user_id=user_id,
        execution_id=execution_id,
        submission_reference=payload.submission_reference,
    )



@router.post(
    "/{execution_id}/fail",
    response_model=ApplicationExecutionRead,
)
def fail_execution(
    execution_id: int,
    payload: ApplicationExecutionFail,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Record a definitive failure for a submission attempt."""
    return fail_application_submission(
        db,
        user_id=user_id,
        execution_id=execution_id,
        failure_reason=payload.failure_reason,
    )
