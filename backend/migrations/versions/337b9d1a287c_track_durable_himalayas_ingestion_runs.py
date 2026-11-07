"""track durable Himalayas ingestion runs

Revision ID: 337b9d1a287c
Revises: 745cbe135c02
Create Date: 2026-11-07 20:32:11.746254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '337b9d1a287c'
down_revision: Union[str, Sequence[str], None] = '745cbe135c02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "himalayas_ingestion_state",
        sa.Column("automation_run_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "himalayas_ingestion_state",
        sa.Column(
            "processed_batches",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_foreign_key(
        "fk_himalayas_ingestion_state_automation_run",
        "himalayas_ingestion_state",
        "automation_runs",
        ["automation_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_himalayas_ingestion_state_automation_run_id",
        "himalayas_ingestion_state",
        ["automation_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_himalayas_ingestion_state_automation_run_id",
        table_name="himalayas_ingestion_state",
    )
    op.drop_constraint(
        "fk_himalayas_ingestion_state_automation_run",
        "himalayas_ingestion_state",
        type_="foreignkey",
    )
    op.drop_column("himalayas_ingestion_state", "processed_batches")
    op.drop_column("himalayas_ingestion_state", "automation_run_id")
