from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job_matching_corpus_state import JobMatchingCorpusState


def mark_job_matching_corpus_changed(db: Session) -> None:
    """Invalidate cached corpus weights in the current transaction."""
    state = db.scalar(
        select(JobMatchingCorpusState)
        .where(JobMatchingCorpusState.id == 1)
        .with_for_update()
    )

    if state is None:
        # Production databases are seeded by the Alembic migration.
        # This fallback also supports isolated test databases.
        state = JobMatchingCorpusState(
            id=1,
            revision=2,
            term_weights=None,
        )
        db.add(state)
        return

    state.revision += 1
    state.term_weights = None
    state.updated_at = datetime.now(timezone.utc)
