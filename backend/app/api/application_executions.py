"""API endpoints for preparing application executions."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.application_execution import ApplicationExecution
from app.schemas.application_execution import (
    ApplicationExecutionComplete,
    ApplicationExecutionAttention,
    ApplicationExecutionFail,
    ApplicationExecutionPrepare,
    ApplicationExecutionRead,
    ExtensionHandoffIssueResponse,
)
from app.services.application_preparation import (
    approve_application_execution,
    complete_application_submission,
    flag_application_submission_for_attention,
    fail_application_submission,
    prepare_application_execution,
    review_application_execution,
    start_application_submission,
    create_extension_handoff,
)


router = APIRouter(
    prefix="/api/application-executions",
    tags=["Application Executions"],
)


@router.get(
    "",
    response_model=list[ApplicationExecutionRead],
)
def list_application_executions(
    user_id: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List the authenticated user's application executions."""
    statement = (
        select(ApplicationExecution)
        .where(ApplicationExecution.user_id == user_id)
        .order_by(
            ApplicationExecution.created_at.desc(),
            ApplicationExecution.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(statement).all()


@router.delete(
    "/{execution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_application_execution(
    execution_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Remove an execution owned by the authenticated user when safe."""
    execution = db.scalar(
        select(ApplicationExecution).where(
            ApplicationExecution.id == execution_id,
            ApplicationExecution.user_id == user_id,
        )
    )

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application execution not found.",
        )

    protected_statuses = {"submitting", "submitted", "needs_attention"}
    if execution.status in protected_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This execution cannot be removed because its submission "
                "is in progress, completed, or requires investigation."
            ),
        )

    db.delete(execution)
    db.commit()


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
        candidate_answer_ids=payload.candidate_answer_ids,
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
    "/{execution_id}/extension-handoff",
    response_model=ExtensionHandoffIssueResponse,
)
def issue_extension_handoff(
    execution_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Issue a short-lived credential for the approved Chrome extension handoff."""
    return create_extension_handoff(
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



@router.post(
    "/{execution_id}/needs-attention",
    response_model=ApplicationExecutionRead,
)
def attention_execution(
    execution_id: int,
    payload: ApplicationExecutionAttention,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Flag an uncertain submission outcome for human investigation."""
    return flag_application_submission_for_attention(
        db,
        user_id=user_id,
        execution_id=execution_id,
        reason=payload.reason,
    )
