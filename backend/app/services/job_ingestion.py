"""Persist jobs fetched from external sources."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.services.jobicy_adapter import fetch_jobicy_jobs


def ingest_jobicy_jobs(db: Session) -> dict[str, int]:
    """Insert new Jobicy listings and refresh previously imported listings."""
    # Fetch everything first. A network or pagination failure must not lead
    # to a partial refresh or changes to existing listing statuses.
    incoming_jobs = fetch_jobicy_jobs()
    now = datetime.now(timezone.utc)

    inserted = 0
    updated = 0

    try:
        for fields in incoming_jobs:
            statement = select(Job).where(
                Job.source_name == fields["source_name"],
                Job.source_job_id == fields["source_job_id"],
            )
            existing = db.scalar(statement)

            if existing is None:
                db.add(
                    Job(
                        **fields,
                        last_seen_at=now,
                    )
                )
                inserted += 1
            else:
                for field, value in fields.items():
                    setattr(existing, field, value)

                existing.last_seen_at = now
                updated += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "fetched": len(incoming_jobs),
        "inserted": inserted,
        "updated": updated,
    }
