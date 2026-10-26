"""Add job eligibility verification evidence.

Revision ID: 64f566ad600a
Revises: 07ef30cc0bfc
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "64f566ad600a"
down_revision: Union[str, Sequence[str], None] = "07ef30cc0bfc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "eligibility_evidence_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("eligibility_evidence", sa.Text(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "eligibility_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "eligibility_verified_by",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "eligibility_verified_by")
    op.drop_column("jobs", "eligibility_verified_at")
    op.drop_column("jobs", "eligibility_evidence")
    op.drop_column("jobs", "eligibility_evidence_url")
