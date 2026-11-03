from datetime import datetime
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    application_url: str | None = Field(default=None, max_length=2048)
    employment_type: str | None = Field(default=None, max_length=100)

class ApplicationUrlUpdate(BaseModel):
    """Admin update for a verified employer application URL."""

    application_url: AnyHttpUrl | None

    @field_validator("application_url")
    @classmethod
    def validate_application_url(cls, value):
        if value is None:
            return value

        if value.scheme != "https":
            raise ValueError("Application URLs must use HTTPS.")

        if value.username is not None or value.password is not None:
            raise ValueError(
                "Application URLs must not contain embedded credentials."
            )

        return value

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
    experience_level: str


class JobSearchResult(BaseModel):
    items: list[JobSearchItem]
    total: int
    skip: int
    limit: int


class ResumeJobMatchItem(JobRead):
    """A job with explainable resume-only and profile-aware text matching."""

    # Resume-only baseline. These fields retain their existing meaning.
    match_score: int = Field(ge=0, le=100)
    matched_terms: list[str]
    terms_not_found_in_resume: list[str]
    required_terms_found: list[str]
    required_terms_not_found: list[str]
    preferred_terms_found: list[str]
    preferred_terms_not_found: list[str]
    term_evidence: dict[str, list[str]]
    match_reasons: list[str]

    # Combined resume + candidate-profile evidence. None means no usable
    # candidate-profile evidence was available for matching.
    profile_match_score: int | None = Field(default=None, ge=0, le=100)
    profile_matched_terms: list[str] = Field(default_factory=list)
    profile_only_matched_terms: list[str] = Field(default_factory=list)
    terms_not_found_in_resume_or_profile: list[str] = Field(default_factory=list)
    required_terms_found_in_profile: list[str] = Field(default_factory=list)
    required_terms_found_in_resume_or_profile: list[str] = Field(default_factory=list)
    required_terms_not_found_in_resume_or_profile: list[str] = Field(default_factory=list)
    preferred_terms_found_in_profile: list[str] = Field(default_factory=list)
    preferred_terms_found_in_resume_or_profile: list[str] = Field(default_factory=list)
    preferred_terms_not_found_in_resume_or_profile: list[str] = Field(default_factory=list)
    profile_term_evidence: dict[str, list[str]] = Field(default_factory=dict)
    profile_match_reasons: list[str] = Field(default_factory=list)


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
