"""API endpoints for preparing application executions."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.schemas.application_execution import (
    ApplicationExecutionPrepare,
    ApplicationExecutionRead,
)
from app.services.application_preparation import (
    prepare_application_execution,
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
