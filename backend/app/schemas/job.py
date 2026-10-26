from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    employment_type: str | None = Field(default=None, max_length=100)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    location: str | None
    description: str | None
    source_url: str | None
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
    published_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime



class JobSearchResult(BaseModel):
    items: list[JobRead]
    total: int
    skip: int
    limit: int
