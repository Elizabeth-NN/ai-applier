"""add candidate answers

Revision ID: 7bdaea0d131d
Revises: bc0e7433d389
Create Date: 2026-11-01 16:35:30.273234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7bdaea0d131d"
down_revision: Union[str, Sequence[str], None] = "bc0e7433d389"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the candidate answers table."""
    op.create_table(
        "candidate_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("question_key", sa.String(length=80), nullable=False),
        sa.Column("question_label", sa.String(length=255), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column(
            "is_user_authored",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "is_approved",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "question_key",
            name="uq_candidate_answers_user_question",
        ),
    )
    op.create_index(
        op.f("ix_candidate_answers_id"),
        "candidate_answers",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_answers_user_id"),
        "candidate_answers",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the candidate answers table."""
    op.drop_index(
        op.f("ix_candidate_answers_user_id"),
        table_name="candidate_answers",
    )
    op.drop_index(
        op.f("ix_candidate_answers_id"),
        table_name="candidate_answers",
    )
    op.drop_table("candidate_answers")
