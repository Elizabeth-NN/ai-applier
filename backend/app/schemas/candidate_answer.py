from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CandidateAnswerCreate(BaseModel):
    question_key: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )
    question_label: str = Field(min_length=1, max_length=255)
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


class CandidateAnswerUpdate(BaseModel):
    question_label: str = Field(min_length=1, max_length=255)
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


class CandidateAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_key: str
    question_label: str
    answer: str
    is_user_authored: bool
    is_approved: bool
    created_at: datetime
    updated_at: datetime
