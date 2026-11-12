"""add screening result ranking metadata

Revision ID: d4b0451ae9d2
Revises: 337b9d1a287c
Create Date: 2026-11-12 13:51:19.679997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b0451ae9d2"
down_revision: Union[str, Sequence[str], None] = "337b9d1a287c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "automation_screening_results",
        sa.Column("ranking_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "automation_screening_results",
        sa.Column("match_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "automation_screening_results",
        sa.Column("job_created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE automation_screening_results AS screening
        SET
            ranking_score = COALESCE(
                NULLIF(screening.result->>'profile_match_score', '')::integer,
                NULLIF(screening.result->>'match_score', '')::integer,
                0
            ),
            match_score = COALESCE(
                NULLIF(screening.result->>'match_score', '')::integer,
                0
            ),
            job_created_at = jobs.created_at
        FROM jobs
        WHERE jobs.id = screening.job_id
        """
    )

    op.alter_column(
        "automation_screening_results",
        "ranking_score",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "automation_screening_results",
        "match_score",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "automation_screening_results",
        "job_created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("automation_screening_results", "job_created_at")
    op.drop_column("automation_screening_results", "match_score")
    op.drop_column("automation_screening_results", "ranking_score")
