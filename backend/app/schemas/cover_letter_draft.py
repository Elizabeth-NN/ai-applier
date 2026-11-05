from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class CoverLetterDraftCreate(BaseModel):
    application_id: int = Field(gt=0)
    title: str | None = Field(default=None, max_length=255)
    content: str = Field(default="", max_length=20000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Title cannot be empty.")
        return cleaned


class CoverLetterDraftUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=20000,
    )

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Title cannot be empty.")
        return cleaned

    @model_validator(mode="after")
    def require_an_update(self):
        if self.title is None and self.content is None:
            raise ValueError("Provide a title or content to update.")
        return self


class CoverLetterDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
