from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


PROFILE_JSON = JSON().with_variant(JSONB, "postgresql")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_candidate_profiles_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str | None] = mapped_column(String(255))
    headline: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    professional_summary: Mapped[str | None] = mapped_column(Text)

    skills: Mapped[list[str]] = mapped_column(
        PROFILE_JSON,
        default=list,
        nullable=False,
    )
    experience: Mapped[list[dict[str, Any]]] = mapped_column(
        PROFILE_JSON,
        default=list,
        nullable=False,
    )
    education: Mapped[list[dict[str, Any]]] = mapped_column(
        PROFILE_JSON,
        default=list,
        nullable=False,
    )
    projects: Mapped[list[dict[str, Any]]] = mapped_column(
        PROFILE_JSON,
        default=list,
        nullable=False,
    )
    certifications: Mapped[list[dict[str, Any]]] = mapped_column(
        PROFILE_JSON,
        default=list,
        nullable=False,
    )
    links: Mapped[dict[str, str]] = mapped_column(
        PROFILE_JSON,
        default=dict,
        nullable=False,
    )
    target_roles: Mapped[list[str]] = mapped_column(
        PROFILE_JSON,
        default=list,
        nullable=False,
    )
    work_preferences: Mapped[dict[str, Any]] = mapped_column(
        PROFILE_JSON,
        default=dict,
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
