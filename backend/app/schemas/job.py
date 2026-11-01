from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    application_url: str | None = Field(default=None, max_length=2048)
    employment_type: str | None = Field(default=None, max_length=100)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    location: str | None
    description: str | None
    source_url: str | None
    application_url: str | None
    employment_type: str | None
    source_name: str | None
    source_job_id: str | None
    remote_type: str | None
    eligible_countries: list[str] | None
    eligibility_status: str
    eligibility_evidence_url: str | None
    eligibility_evidence: str | None
    eligibility_verified_at: datetime | None
    eligibility_verified_by: str | None
    listing_status: str
    listing_status_checked_at: datetime | None
    published_at: datetime | None
    expires_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime



class JobSearchItem(JobRead):
    """A job with explainable, heuristic relevance metadata."""

    relevance_score: int = Field(ge=0, le=100)
    matched_role_families: list[str]
    relevance_reasons: list[str]


class JobSearchResult(BaseModel):
    items: list[JobSearchItem]
    total: int
    skip: int
    limit: int


class ResumeJobMatchItem(JobRead):
    """A job with explainable text overlap against a selected resume."""

    match_score: int = Field(ge=0, le=100)
    matched_terms: list[str]
    terms_not_found_in_resume: list[str]
    match_reasons: list[str]


class ResumeJobMatchResult(BaseModel):
    """Paginated personalized job matches for a user's resume."""

    resume_id: int
    resume_filename: str
    items: list[ResumeJobMatchItem]
    total: int
    skip: int
    limit: int


class EligibilityVerificationRequest(BaseModel):
    """Evidence-backed verification of a job's eligibility in Kenya."""

    eligibility_status: Literal["eligible", "ineligible", "unknown"]
    evidence_url: AnyHttpUrl | None = None
    evidence: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.eligibility_status in {"eligible", "ineligible"}:
            if self.evidence_url is None:
                raise ValueError(
                    "An evidence URL is required for a verified decision."
                )
            if not self.evidence or not self.evidence.strip():
                raise ValueError(
                    "Supporting evidence is required for a verified decision."
                )
        return self
