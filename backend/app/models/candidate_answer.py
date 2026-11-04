from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    JSON,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CandidateAnswer(Base):
    __tablename__ = "candidate_answers"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "question_key",
            name="uq_candidate_answers_user_question",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    question_key: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    question_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    question_aliases: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )

    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_user_authored: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
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
