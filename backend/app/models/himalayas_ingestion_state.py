from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HimalayasIngestionState(Base):
    __tablename__ = "himalayas_ingestion_state"

    # A single shared state row, always using id=1.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("automation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Retain every task result so retries remain safe after later batches run.
    processed_batches: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", server_default=text("'running'")
    )

    pages_fetched: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text('0')
    )
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))
    expired: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
