from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ApplicationBatch(Base):
    __tablename__ = "application_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    items: Mapped[list["ApplicationBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ApplicationBatchItem.id",
    )


class ApplicationBatchItem(Base):
    __tablename__ = "application_batch_items"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "job_id",
            name="uq_application_batch_items_batch_job",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("application_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    batch: Mapped["ApplicationBatch"] = relationship(back_populates="items")
    job: Mapped["Job"] = relationship()
