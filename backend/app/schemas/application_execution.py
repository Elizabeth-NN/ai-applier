from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApplicationExecutionPrepare(BaseModel):
    application_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    cover_letter_draft_id: int | None = Field(default=None, gt=0)
    batch_item_id: int | None = Field(default=None, gt=0)


class ApplicationExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    batch_item_id: int | None
    resume_id: int | None
    cover_letter_draft_id: int | None

    resume_filename_snapshot: str | None
    resume_sha256: str | None
    cover_letter_snapshot: str | None

    job_snapshot: dict[str, Any]
    application_payload: dict[str, Any]

    target_url: str
    ats_platform: str
    status: Literal[
        "prepared",
        "approved",
        "submitting",
        "submitted",
        "failed",
        "needs_attention",
    ]

    reviewed_at: datetime | None
    approved_at: datetime | None
    submitted_at: datetime | None
    submission_attempt_id: str | None
    submission_started_at: datetime | None
    submission_reference: str | None
    submission_result: dict[str, Any] | None
    failure_reason: str | None

    created_at: datetime
    updated_at: datetime

class ApplicationExecutionComplete(BaseModel):
    submission_reference: str | None = Field(
        default=None,
        max_length=255,
    )
