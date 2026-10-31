"""add extension handoff credentials

Revision ID: 489dbb7f8694
Revises: c43f6652a98d
Create Date: 2026-10-31 13:34:48.122534

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '489dbb7f8694'
down_revision: Union[str, Sequence[str], None] = 'c43f6652a98d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "application_executions",
        sa.Column(
            "extension_handoff_token_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "application_executions",
        sa.Column(
            "extension_handoff_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "application_executions",
        sa.Column(
            "extension_handoff_redeemed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_application_execution_extension_handoff_token_hash",
        "application_executions",
        ["extension_handoff_token_hash"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_application_execution_extension_handoff_token_hash",
        "application_executions",
        type_="unique",
    )
    op.drop_column(
        "application_executions",
        "extension_handoff_redeemed_at",
    )
    op.drop_column(
        "application_executions",
        "extension_handoff_expires_at",
    )
    op.drop_column(
        "application_executions",
        "extension_handoff_token_hash",
    )
