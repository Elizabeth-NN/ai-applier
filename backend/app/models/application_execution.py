from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ApplicationExecution(Base):
    """A prepared application submission awaiting explicit human approval."""

    __tablename__ = "application_executions"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_application_execution_user_idempotency",
        ),
        UniqueConstraint(
            "extension_handoff_token_hash",
            name="uq_application_execution_extension_handoff_token_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    batch_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_batch_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    cover_letter_draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("cover_letter_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Immutable preparation snapshots. These preserve exactly what was
    # reviewed even if the original resume or draft is later changed/deleted.
    resume_filename_snapshot: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    resume_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    cover_letter_snapshot: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    job_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    application_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    target_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    ats_platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unsupported",
        server_default=text("'unsupported'"),
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="prepared",
        server_default=text("'prepared'"),
        index=True,
    )

    # Unique per preparation request to make API retries safe.
    idempotency_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Short-lived, single-use Chrome extension handoff credential.
    # Only the SHA-256 hash is persisted; the raw token is never stored.
    extension_handoff_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    extension_handoff_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    extension_handoff_redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Submission attempt audit information.
    submission_attempt_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    submission_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    submission_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    submission_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
