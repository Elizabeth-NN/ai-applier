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
