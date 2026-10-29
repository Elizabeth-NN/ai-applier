"""add resumable Himalayas ingestion state"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a2f6c1d8b40"
down_revision: Union[str, Sequence[str], None] = "66e9d2eca819"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "himalayas_ingestion_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column(
            "pages_fetched",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "fetched", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "inserted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "updated", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "expired", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("himalayas_ingestion_state")
