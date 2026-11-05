"""add application campaigns

Revision ID: 617d0748db5c
Revises: d4f6a8b2c901
Create Date: 2026-11-05 16:31:35.646592

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "617d0748db5c"
down_revision: Union[str, Sequence[str], None] = "d4f6a8b2c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column(
            "target_applications",
            sa.Integer(),
            server_default=sa.text("500"),
            nullable=False,
        ),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("deadline_on", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'draft'"),
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
    )

    op.create_index(
        "ix_application_campaigns_id",
        "application_campaigns",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_application_campaigns_status",
        "application_campaigns",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_application_campaigns_user_id",
        "application_campaigns",
        ["user_id"],
        unique=False,
    )

    op.add_column(
        "application_batches",
        sa.Column("campaign_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_application_batches_campaign_id",
        "application_batches",
        ["campaign_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_application_batches_campaign_id_application_campaigns",
        "application_batches",
        "application_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "application_executions",
        sa.Column("campaign_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_application_executions_campaign_id",
        "application_executions",
        ["campaign_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_application_executions_campaign_id_application_campaigns",
        "application_executions",
        "application_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_application_executions_campaign_id_application_campaigns",
        "application_executions",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_application_executions_campaign_id",
        table_name="application_executions",
    )
    op.drop_column("application_executions", "campaign_id")

    op.drop_constraint(
        "fk_application_batches_campaign_id_application_campaigns",
        "application_batches",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_application_batches_campaign_id",
        table_name="application_batches",
    )
    op.drop_column("application_batches", "campaign_id")

    op.drop_index(
        "ix_application_campaigns_user_id",
        table_name="application_campaigns",
    )
    op.drop_index(
        "ix_application_campaigns_status",
        table_name="application_campaigns",
    )
    op.drop_index(
        "ix_application_campaigns_id",
        table_name="application_campaigns",
    )
    op.drop_table("application_campaigns")
