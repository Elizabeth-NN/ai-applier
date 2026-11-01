from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic import AwareDatetime

class ApplicationExecutionPrepare(BaseModel):
    application_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    cover_letter_draft_id: int | None = Field(default=None, gt=0)
    batch_item_id: int | None = Field(default=None, gt=0)
    candidate_answer_ids: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("candidate_answer_ids")
    @classmethod
    def validate_candidate_answer_ids(cls, value: list[int]) -> list[int]:
        if any(answer_id <= 0 for answer_id in value):
            raise ValueError("Candidate answer IDs must be positive.")
        if len(value) != len(set(value)):
            raise ValueError("Candidate answer IDs must be unique.")
        return value

class ExtensionHandoffIssueResponse(BaseModel):
    token: str
    expires_at: AwareDatetime

class ExtensionHandoffRedeemRequest(BaseModel):
    token: SecretStr = Field(min_length=32, max_length=256)
    active_url: str = Field(min_length=1, max_length=2048)


class ExtensionHandoffRedeemResponse(BaseModel):
    execution_id: int
    target_url: str
    ats_platform: str
    job_snapshot: dict[str, Any]
    resume_filename: str
    cover_letter: str | None
    candidate_answers: list[dict[str, Any]] = Field(default_factory=list)

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



class ApplicationExecutionFail(BaseModel):
    failure_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("failure_reason")
    @classmethod
    def validate_failure_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Failure reason cannot be blank.")
        return value


class ApplicationExecutionAttention(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Attention reason cannot be blank.")
        return value
