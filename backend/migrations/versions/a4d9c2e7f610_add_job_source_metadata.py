"""Add normalized job source metadata.

Revision ID: a4d9c2e7f610
Revises: c8e1a2f4b6d9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4d9c2e7f610"
down_revision: Union[str, Sequence[str], None] = "c8e1a2f4b6d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("source_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("remote_type", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("eligible_countries", sa.JSON(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "eligibility_status",
            sa.String(length=30),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "listing_status",
            sa.String(length=30),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_jobs_source_name", "jobs", ["source_name"])
    op.create_index("ix_jobs_listing_status", "jobs", ["listing_status"])
    op.create_index("ix_jobs_published_at", "jobs", ["published_at"])

    op.create_unique_constraint(
        "uq_jobs_source_external_id",
        "jobs",
        ["source_name", "source_job_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_jobs_source_external_id",
        "jobs",
        type_="unique",
    )
    op.drop_index("ix_jobs_published_at", table_name="jobs")
    op.drop_index("ix_jobs_listing_status", table_name="jobs")
    op.drop_index("ix_jobs_source_name", table_name="jobs")

    op.drop_column("jobs", "last_seen_at")
    op.drop_column("jobs", "published_at")
    op.drop_column("jobs", "listing_status")
    op.drop_column("jobs", "eligibility_status")
    op.drop_column("jobs", "eligible_countries")
    op.drop_column("jobs", "remote_type")
    op.drop_column("jobs", "source_job_id")
    op.drop_column("jobs", "source_name")
