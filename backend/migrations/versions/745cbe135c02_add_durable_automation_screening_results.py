"""add durable automation screening results

Revision ID: 745cbe135c02
Revises: b1d31306d1a1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "745cbe135c02"
down_revision: Union[str, Sequence[str], None] = "b1d31306d1a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_screening_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"], ["resumes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["automation_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "job_id",
            name="uq_automation_screening_run_job",
        ),
    )

    op.create_index(
        op.f("ix_automation_screening_results_id"),
        "automation_screening_results",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_screening_results_job_id"),
        "automation_screening_results",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_screening_results_resume_id"),
        "automation_screening_results",
        ["resume_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_screening_results_run_id"),
        "automation_screening_results",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automation_screening_results_user_id"),
        "automation_screening_results",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_automation_screening_results_user_id"),
        table_name="automation_screening_results",
    )
    op.drop_index(
        op.f("ix_automation_screening_results_run_id"),
        table_name="automation_screening_results",
    )
    op.drop_index(
        op.f("ix_automation_screening_results_resume_id"),
        table_name="automation_screening_results",
    )
    op.drop_index(
        op.f("ix_automation_screening_results_job_id"),
        table_name="automation_screening_results",
    )
    op.drop_index(
        op.f("ix_automation_screening_results_id"),
        table_name="automation_screening_results",
    )
    op.drop_table("automation_screening_results")
