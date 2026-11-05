from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CampaignStatus = Literal[
    "draft",
    "active",
    "paused",
    "completed",
    "archived",
]


class ApplicationCampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    target_applications: int = Field(default=500, gt=0)
    starts_on: date = Field(default_factory=date.today)
    deadline_on: date | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Campaign name cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.deadline_on is None:
            self.deadline_on = self.starts_on + timedelta(days=56)

        if self.deadline_on <= self.starts_on:
            raise ValueError("Campaign deadline must be after its start date")

        return self


class ApplicationCampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    target_applications: int | None = Field(default=None, gt=0)
    starts_on: date | None = None
    deadline_on: date | None = None
    status: CampaignStatus | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value

        value = value.strip()
        if not value:
            raise ValueError("Campaign name cannot be blank")
        return value


class ApplicationCampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_applications: int
    starts_on: date
    deadline_on: date
    status: CampaignStatus


class ApplicationCampaignProgressRead(BaseModel):
    campaign_id: int
    target_applications: int
    submitted: int
    remaining: int
    percentage: float
    days_remaining: int
    required_per_week: float | None
