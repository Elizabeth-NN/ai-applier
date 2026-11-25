"""add cover letter draft titles

Revision ID: d4f6a8b2c901
Revises: c31a9e7d5f20
Create Date: 2026-11-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f6a8b2c901"
down_revision: Union[str, Sequence[str], None] = "c31a9e7d5f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cover_letter_drafts",
        sa.Column("title", sa.String(length=255), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE cover_letter_drafts AS drafts
            SET title = LEFT(jobs.title || ' — ' || jobs.company, 255)
            FROM applications
            JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.id = drafts.application_id
            """
        )
    )

    op.alter_column(
        "cover_letter_drafts",
        "title",
        existing_type=sa.String(length=255),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("cover_letter_drafts", "title")
