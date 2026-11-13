from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class JobMatchingCorpusState(Base):
    __tablename__ = "job_matching_corpus_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    term_weights: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
