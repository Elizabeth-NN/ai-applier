"""add candidate answer question aliases

Revision ID: c31a9e7d5f20
Revises: e2a7c91b4d30
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c31a9e7d5f20"
down_revision: Union[str, Sequence[str], None] = "e2a7c91b4d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    alias_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.add_column(
        "candidate_answers",
        sa.Column(
            "question_aliases",
            alias_type,
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("candidate_answers", "question_aliases")
