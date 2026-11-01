from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CandidateAnswerCreate(BaseModel):
    question_key: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )
    question_label: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1, max_length=10000)

    # Creating an answer requires an explicit authorship confirmation.
    confirm_user_authored: Literal[True]


class CandidateAnswerUpdate(BaseModel):
    question_label: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1, max_length=10000)

    # Editing requires confirming authorship of the revised text again.
    confirm_user_authored: Literal[True]


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
