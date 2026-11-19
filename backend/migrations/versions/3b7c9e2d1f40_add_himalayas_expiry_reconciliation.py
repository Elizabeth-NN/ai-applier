"""add once-per-scan Himalayas expiry reconciliation marker

Revision ID: 3b7c9e2d1f40
Revises: 01ac77883614
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b7c9e2d1f40"
down_revision: Union[str, Sequence[str], None] = "01ac77883614"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "himalayas_ingestion_state",
        sa.Column("expiry_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("himalayas_ingestion_state", "expiry_reconciled_at")
