"""add job matching corpus state

Revision ID: 01ac77883614
Revises: d4b0451ae9d2
Create Date: 2026-11-13 20:34:29.678428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01ac77883614'
down_revision: Union[str, Sequence[str], None] = 'd4b0451ae9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create persistent job-matching corpus cache state."""
    op.create_table(
        "job_matching_corpus_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("term_weights", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO job_matching_corpus_state (id, revision)
            VALUES (1, 1)
            """
        )
    )


def downgrade() -> None:
    """Remove persistent job-matching corpus cache state."""
    op.drop_table("job_matching_corpus_state")
