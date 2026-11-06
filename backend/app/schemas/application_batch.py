
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.schemas.job import JobRead


BatchStatus = Literal["draft", "approved", "archived"]


class ApplicationBatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    job_ids: list[int] = Field(min_length=1, max_length=100)
    campaign_id: int | None = None


class ApplicationBatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()
        if not value:
            raise ValueError("Session name cannot be blank.")

        return value


class ApplicationBatchAddItems(BaseModel):
    job_ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("job_ids")
    @classmethod
    def validate_unique_job_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate job IDs are not allowed.")

        if any(job_id <= 0 for job_id in value):
            raise ValueError("Job IDs must be positive.")

        return value


class ApplicationBatchItemSelection(BaseModel):
    selected: bool


class ApplicationBatchPrepare(BaseModel):
    resume_id: int = Field(gt=0)
    cover_letter_draft_ids: dict[int, int] = Field(
        default_factory=dict,
        max_length=100,
    )
    candidate_answer_ids: list[int] = Field(
        default_factory=list,
        max_length=50,
    )

    @field_validator("cover_letter_draft_ids")
    @classmethod
    def validate_cover_letter_ids(
        cls,
        value: dict[int, int],
    ) -> dict[int, int]:
        if any(item_id <= 0 or draft_id <= 0
               for item_id, draft_id in value.items()):
            raise ValueError("Batch item and cover letter IDs must be positive.")

        return value

    @field_validator("candidate_answer_ids")
    @classmethod
    def validate_candidate_answer_ids(
        cls,
        value: list[int],
    ) -> list[int]:
        if any(answer_id <= 0 for answer_id in value):
            raise ValueError("Candidate answer IDs must be positive.")

        if len(value) != len(set(value)):
            raise ValueError("Duplicate candidate answer IDs are not allowed.")

        return value


class ApplicationBatchPrepareItemResult(BaseModel):
    batch_item_id: int
    job_id: int
    status: Literal["prepared", "already_prepared", "failed"]
    execution_id: int | None = None
    execution_status: str | None = None
    reason: str | None = None


class ApplicationBatchPrepareRead(BaseModel):
    batch_id: int
    prepared_count: int
    already_prepared_count: int
    failed_count: int
    items: list[ApplicationBatchPrepareItemResult]


class ApplicationBatchItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    selected: bool
    approved_at: datetime | None
    created_at: datetime
    job: JobRead


class ApplicationBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    campaign_id: int | None
    status: BatchStatus
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[ApplicationBatchItemRead]
