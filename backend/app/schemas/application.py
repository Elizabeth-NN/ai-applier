from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ApplicationStatus = Literal[
    "saved",
    "applied",
    "interview",
    "rejected",
    "offer",
]


class ApplicationCreate(BaseModel):
    job_id: int = Field(gt=0)
    notes: str | None = None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    status: str
    notes: str | None
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
