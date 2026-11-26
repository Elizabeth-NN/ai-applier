"""add durable pending state for resume deletion

Revision ID: a91d6c4e2b70
Revises: 3b7c9e2d1f40
Create Date: 2026-11-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a91d6c4e2b70"
down_revision: Union[str, Sequence[str], None] = "3b7c9e2d1f40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column(
            "deletion_pending",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("resumes", "deletion_pending")
