"""add verified job application url

Revision ID: bc0e7433d389
Revises: 489dbb7f8694
Create Date: 2026-11-01 10:52:55.221092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bc0e7433d389"
down_revision: Union[str, Sequence[str], None] = "489dbb7f8694"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the verified employer application URL."""
    op.add_column(
        "jobs",
        sa.Column("application_url", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    """Remove the verified employer application URL."""
    op.drop_column("jobs", "application_url")