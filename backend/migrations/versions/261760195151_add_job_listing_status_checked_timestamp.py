"""Add job listing status checked timestamp."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d71c9a4e82bf"
down_revision: Union[str, Sequence[str], None] = "64f566ad600a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "listing_status_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "listing_status_checked_at")