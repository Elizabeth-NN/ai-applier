from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import JobRead


BatchStatus = Literal["draft", "approved", "archived"]


class ApplicationBatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    job_ids: list[int] = Field(min_length=1, max_length=100)
    campaign_id: int | None = None


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
