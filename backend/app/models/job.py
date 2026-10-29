from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "source_job_id",
            name="uq_jobs_source_external_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # External source identity. Both remain nullable for manually created jobs.
    source_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    source_job_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Normalized discovery metadata. Unknown means we have not verified it.
    remote_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    eligible_countries: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    eligibility_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="unknown",
        server_default=text("'unknown'"),
    )
    # Evidence supporting a human-reviewed country eligibility decision.
    eligibility_evidence_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    eligibility_evidence: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    eligibility_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    eligibility_verified_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    listing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="unknown",
        server_default=text("'unknown'"),
        index=True,
    )
    listing_status_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
