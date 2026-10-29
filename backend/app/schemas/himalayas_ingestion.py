from typing import Literal

from pydantic import BaseModel, Field


class HimalayasBatchIngestionResult(BaseModel):
    """Progress and counts returned by a bounded Himalayas ingestion batch."""

    status: Literal["running", "completed"]

    # Counts for this individual request.
    pages_this_batch: int = Field(ge=0)
    fetched_this_batch: int = Field(ge=0)
    inserted_this_batch: int = Field(ge=0)
    updated_this_batch: int = Field(ge=0)
    expired_this_batch: int = Field(ge=0)

    # Cumulative counts for the current ingestion run.
    pages_fetched: int = Field(ge=0)
    fetched: int = Field(ge=0)
    inserted: int = Field(ge=0)
    updated: int = Field(ge=0)
    expired: int = Field(ge=0)

    completed: bool
