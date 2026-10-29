"""add job full text search index

Revision ID: 4efd3747d71f
Revises: 771d64bee416
Create Date: 2026-10-29 15:55:06.260131
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4efd3747d71f"
down_revision: Union[str, Sequence[str], None] = "771d64bee416"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ix_jobs_title_description_fts"

SEARCH_VECTOR = """
(
    setweight(to_tsvector('english', coalesce(title, '')), 'A')
    ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
    ||
    setweight(to_tsvector('english', coalesce(employment_type, '')), 'C')
)
"""


def upgrade() -> None:
    """Create a full-text index without blocking ordinary writes."""
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY {INDEX_NAME}
            ON jobs USING GIN ({SEARCH_VECTOR})
            """
        )


def downgrade() -> None:
    """Remove the full-text index without blocking ordinary writes."""
    with op.get_context().autocommit_block():
        op.execute(
            f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"
        )
