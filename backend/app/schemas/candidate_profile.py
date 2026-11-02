from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CandidateProfileUpsert(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    headline: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    professional_summary: str | None = Field(default=None, max_length=10000)

    skills: list[str] = Field(default_factory=list, max_length=100)
    experience: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=50,
    )
    education: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=30,
    )
    projects: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=50,
    )
    certifications: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=50,
    )
    links: dict[str, str] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list, max_length=30)
    work_preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "full_name",
        "headline",
        "email",
        "phone",
        "location",
        "professional_summary",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("skills", "target_roles")
    @classmethod
    def clean_string_lists(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class CandidateProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str | None
    headline: str | None
    email: str | None
    phone: str | None
    location: str | None
    professional_summary: str | None
    skills: list[str]
    experience: list[dict[str, Any]]
    education: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    certifications: list[dict[str, Any]]
    links: dict[str, str]
    target_roles: list[str]
    work_preferences: dict[str, Any]
    created_at: datetime
    updated_at: datetime
