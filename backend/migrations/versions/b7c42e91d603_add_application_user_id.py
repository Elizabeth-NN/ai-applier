
"""add user ownership to applications

Revision ID: b7c42e91d603
Revises: f9d1bb3e11e0
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c42e91d603"
down_revision = "f9d1bb3e11e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("user_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_applications_user_id",
        "applications",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_applications_user_id",
        table_name="applications",
    )
    op.drop_column("applications", "user_id")
