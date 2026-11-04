from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)


def clean_question_aliases(value, info: ValidationInfo):
    if value is None:
        return None

    if not isinstance(value, list):
        raise ValueError("Question aliases must be a list.")

    primary_label = str(info.data.get("question_label", "")).strip().casefold()
    cleaned = []
    seen = {primary_label} if primary_label else set()

    for alias in value:
        if not isinstance(alias, str):
            raise ValueError("Every question alias must be text.")

        alias = " ".join(alias.split())

        if not alias:
            raise ValueError("Question aliases cannot be empty.")

        if len(alias) > 255:
            raise ValueError("Question aliases cannot exceed 255 characters.")

        key = alias.casefold()
        if key not in seen:
            cleaned.append(alias)
            seen.add(key)

    if len(cleaned) > 20:
        raise ValueError("You can add at most 20 question aliases.")

    return cleaned


class CandidateAnswerCreate(BaseModel):
    question_key: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )
    question_label: str = Field(min_length=1, max_length=255)
    question_aliases: list[str] = Field(default_factory=list, max_length=20)
    answer: str = Field(min_length=1, max_length=10000)
    confirm_user_authored: Literal[True]

    @field_validator("question_label", "answer", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("This field cannot be empty.")
        return value

    @field_validator("question_aliases")
    @classmethod
    def validate_aliases(cls, value, info):
        return clean_question_aliases(value, info)


class CandidateAnswerUpdate(BaseModel):
    question_label: str = Field(min_length=1, max_length=255)
    question_aliases: list[str] | None = Field(default=None, max_length=20)
    answer: str = Field(min_length=1, max_length=10000)
    confirm_user_authored: Literal[True]

    @field_validator("question_label", "answer", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("This field cannot be empty.")
        return value

    @field_validator("question_aliases")
    @classmethod
    def validate_aliases(cls, value, info):
        return clean_question_aliases(value, info)


class CandidateAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_key: str
    question_label: str
    question_aliases: list[str]
    answer: str
    is_user_authored: bool
    is_approved: bool
    created_at: datetime
    updated_at: datetime
