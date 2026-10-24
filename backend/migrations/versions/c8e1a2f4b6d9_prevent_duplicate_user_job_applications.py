"""Prevent duplicate applications for the same user and job.

Revision ID: c8e1a2f4b6d9
Revises: b7c42e91d603
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8e1a2f4b6d9"
down_revision: Union[str, Sequence[str], None] = "b7c42e91d603"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_applications_user_job",
        "applications",
        ["user_id", "job_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_applications_user_job",
        "applications",
        type_="unique",
    )
