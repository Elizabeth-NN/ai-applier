"""Persist jobs fetched from external sources."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.services.himalayas_adapter import fetch_himalayas_jobs
from app.services.jobicy_adapter import fetch_jobicy_jobs


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """Return whether a listing's known expiry is in the past."""
    if expires_at is None:
        return False

    # SQLite may return a naive datetime even when timezone=True.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return expires_at <= now


def _update_existing_job(existing: Job, fields: dict) -> None:
    """Refresh source fields without erasing verified metadata."""
    for field, value in fields.items():
        if value is None:
            continue

        if field == "eligible_countries":
            setattr(existing, field, value)
        elif field == "eligibility_status":
            if value != "unknown":
                setattr(existing, field, value)
        elif field == "listing_status":
            # Feed data must not overwrite a reviewed listing status.
            continue
        else:
            setattr(existing, field, value)


def ingest_jobicy_jobs(db: Session) -> dict[str, int]:
    """Insert new Jobicy listings and refresh previously imported listings."""
    # Fetch everything first so feed failures cannot partially refresh data.
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
                db.add(Job(**fields, last_seen_at=now))
                inserted += 1
            else:
                _update_existing_job(existing, fields)
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


def ingest_himalayas_jobs(db: Session) -> dict[str, int]:
    """Import Himalayas listings and close listings whose expiry has passed."""
    # Fetch and validate the complete feed before modifying the database.
    incoming_jobs = fetch_himalayas_jobs()
    now = datetime.now(timezone.utc)

    inserted = 0
    updated = 0
    expired = 0

    try:
        # Close previously imported Himalayas listings whose expiry has passed,
        # including listings no longer present in the latest feed.
        existing_himalayas_jobs = db.scalars(
            select(Job).where(Job.source_name == "himalayas")
        ).all()

        for existing in existing_himalayas_jobs:
            if _is_expired(existing.expires_at, now):
                existing.listing_status = "closed"

        for fields in incoming_jobs:
            statement = select(Job).where(
                Job.source_name == fields["source_name"],
                Job.source_job_id == fields["source_job_id"],
            )
            existing = db.scalar(statement)
            is_expired = _is_expired(fields.get("expires_at"), now)

            if is_expired:
                expired += 1

                # Never create a new database record for an expired listing.
                # If already imported, refresh its source data and close it.
                if existing is not None:
                    _update_existing_job(existing, fields)
                    existing.listing_status = "closed"
                    existing.last_seen_at = now
                    updated += 1

                continue

            if existing is None:
                db.add(Job(**fields, last_seen_at=now))
                inserted += 1
            else:
                _update_existing_job(existing, fields)
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
        "expired": expired,
    }

def ingest_himalayas_batch(
    db: Session,
    *,
    max_pages: int = 5,
) -> dict:
    """Import a bounded Himalayas batch and persist resumable progress."""
    from sqlalchemy import update

    from app.models.himalayas_ingestion_state import (
        HimalayasIngestionState,
    )
    from app.services.himalayas_adapter import fetch_himalayas_batch

    if not 1 <= max_pages <= 25:
        raise ValueError("max_pages must be between 1 and 25")

    now = datetime.now(timezone.utc)

    try:
        # Create the singleton row if this is the first batch.
        # PostgreSQL's conflict handling makes initialization safe when
        # two administrators start at nearly the same time.
        db.execute(
            __import__("sqlalchemy").text(
                """
                INSERT INTO himalayas_ingestion_state (id, status)
                VALUES (1, 'running')
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        db.flush()

        state = db.scalar(
            select(HimalayasIngestionState)
            .where(HimalayasIngestionState.id == 1)
            .with_for_update()
        )
        if state is None:
            raise RuntimeError("Could not initialize ingestion state")

        # A completed scan starts a fresh scan when called again.
        if state.status == "completed":
            state.cursor = None
            state.status = "running"
            state.pages_fetched = 0
            state.fetched = 0
            state.inserted = 0
            state.updated = 0
            state.expired = 0
            state.started_at = now
            state.completed_at = None
        elif state.started_at is None:
            state.started_at = now

        batch = fetch_himalayas_batch(
            cursor=state.cursor,
            max_pages=max_pages,
        )

        inserted = updated = expired = 0

        for fields in batch["jobs"]:
            statement = select(Job).where(
                Job.source_name == fields["source_name"],
                Job.source_job_id == fields["source_job_id"],
            )
            existing = db.scalar(statement)
            is_expired = _is_expired(fields.get("expires_at"), now)

            if is_expired:
                expired += 1
                if existing is not None:
                    _update_existing_job(existing, fields)
                    existing.listing_status = "closed"
                    existing.last_seen_at = now
                    updated += 1
                continue

            if existing is None:
                db.add(Job(**fields, last_seen_at=now))
                inserted += 1
            else:
                _update_existing_job(existing, fields)
                existing.last_seen_at = now
                updated += 1

        state.cursor = batch["next_cursor"]
        state.pages_fetched += batch["pages_fetched"]
        state.fetched += len(batch["jobs"])
        state.inserted += inserted
        state.updated += updated
        state.expired += expired
        state.updated_at = now

        if batch["complete"]:
            state.status = "completed"
            state.completed_at = now
            state.cursor = None
        else:
            state.status = "running"

        db.commit()

        return {
            "status": state.status,
            "pages_this_batch": batch["pages_fetched"],
            "fetched_this_batch": len(batch["jobs"]),
            "inserted_this_batch": inserted,
            "updated_this_batch": updated,
            "expired_this_batch": expired,
            "pages_fetched": state.pages_fetched,
            "fetched": state.fetched,
            "inserted": state.inserted,
            "updated": state.updated,
            "expired": state.expired,
            "completed": batch["complete"],
        }
    except Exception:
        db.rollback()
        raise
