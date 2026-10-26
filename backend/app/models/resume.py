from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    content_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
