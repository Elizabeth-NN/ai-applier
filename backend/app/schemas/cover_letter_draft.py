from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CoverLetterDraftCreate(BaseModel):
    application_id: int = Field(gt=0)
    content: str = Field(default="", max_length=20000)


class CoverLetterDraftUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class CoverLetterDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    content: str
    created_at: datetime
    updated_at: datetime
