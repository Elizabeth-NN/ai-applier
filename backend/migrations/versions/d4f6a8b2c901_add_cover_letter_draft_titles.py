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

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT drafts.id, jobs.title, jobs.company
            FROM cover_letter_drafts AS drafts
            JOIN applications ON applications.id = drafts.application_id
            JOIN jobs ON jobs.id = applications.job_id
            """
        )
    ).all()

    for draft_id, job_title, company in rows:
        title = f"{job_title} — {company}"[:255]
        connection.execute(
            sa.text(
                "UPDATE cover_letter_drafts SET title = :title WHERE id = :id"
            ),
            {"title": title, "id": draft_id},
        )

    op.alter_column(
        "cover_letter_drafts",
        "title",
        existing_type=sa.String(length=255),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("cover_letter_drafts", "title")
