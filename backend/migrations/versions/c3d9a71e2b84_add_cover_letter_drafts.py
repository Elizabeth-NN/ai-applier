"""add cover letter drafts

Revision ID: c3d9a71e2b84
Revises: f6688d4f731c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d9a71e2b84"
down_revision: Union[str, Sequence[str], None] = "f6688d4f731c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cover_letter_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "content",
            sa.Text(),
            server_default="",
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
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cover_letter_drafts_id"),
        "cover_letter_drafts",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letter_drafts_application_id"),
        "cover_letter_drafts",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letter_drafts_user_id"),
        "cover_letter_drafts",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_cover_letter_drafts_user_id"),
        table_name="cover_letter_drafts",
    )
    op.drop_index(
        op.f("ix_cover_letter_drafts_application_id"),
        table_name="cover_letter_drafts",
    )
    op.drop_index(
        op.f("ix_cover_letter_drafts_id"),
        table_name="cover_letter_drafts",
    )
    op.drop_table("cover_letter_drafts")
