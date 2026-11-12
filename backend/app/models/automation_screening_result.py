from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AutomationScreeningResult(Base):
    """A durable, user-specific screening result for one job in one run."""

    __tablename__ = "automation_screening_results"

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "job_id",
            name="uq_automation_screening_run_job",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Complete match and screening snapshot. This preserves the result
    # even when matching or screening logic changes in a future release.
    result: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    ranking_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    match_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    job_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
