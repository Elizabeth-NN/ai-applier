"""Persist jobs fetched from external sources."""

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.job import Job
from app.services.himalayas_adapter import (
    fetch_himalayas_batch,
    fetch_himalayas_jobs,
)
from app.services.jobicy_adapter import fetch_jobicy_jobs
from app.services.job_matching_corpus import mark_job_matching_corpus_changed


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """Return whether a listing's known expiry is in the past."""
    if expires_at is None:
        return False

    # SQLite may return a naive datetime even when timezone=True.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return expires_at <= now


def _update_existing_job(existing: Job, fields: dict) -> bool:
    """Refresh source fields and report matching-text changes."""
    matching_fields_changed = False

    for field, value in fields.items():
        if value is None:
            continue

        if field == "eligible_countries":
            if existing.eligibility_verified_at is None:
                setattr(existing, field, value)
        elif field == "eligibility_status":
            if (
                value != "unknown"
                and existing.eligibility_verified_at is None
            ):
                setattr(existing, field, value)
        elif field == "application_url":
            if existing.application_url is None:
                setattr(existing, field, value)
        elif field == "listing_status":
            # Feed data must not overwrite a reviewed listing status.
            continue
        else:
            if field in {"title", "description", "company"}:
                if getattr(existing, field) != value:
                    matching_fields_changed = True
            setattr(existing, field, value)

    return matching_fields_changed


def ingest_jobicy_jobs(db: Session) -> dict[str, int]:
    """Insert new Jobicy listings and refresh previously imported listings."""
    # Fetch everything first so feed failures cannot partially refresh data.
    incoming_jobs = fetch_jobicy_jobs()
    now = datetime.now(timezone.utc)

    inserted = 0
    updated = 0
    corpus_changed = False

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
                corpus_changed = True
            else:
                corpus_changed = (
                    _update_existing_job(existing, fields) or corpus_changed
                )
                existing.last_seen_at = now
                updated += 1

        if corpus_changed:
            mark_job_matching_corpus_changed(db)
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
    corpus_changed = False

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
                    corpus_changed = (
                        _update_existing_job(existing, fields) or corpus_changed
                    )
                    existing.listing_status = "closed"
                    existing.last_seen_at = now
                    updated += 1

                continue

            if existing is None:
                db.add(Job(**fields, last_seen_at=now))
                inserted += 1
                corpus_changed = True
            else:
                corpus_changed = (
                    _update_existing_job(existing, fields) or corpus_changed
                )
                existing.last_seen_at = now
                updated += 1

        if corpus_changed:
            mark_job_matching_corpus_changed(db)
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
    automation_run_id: int | None = None,
    task_id: int | None = None,
) -> dict:
    """Import a bounded batch with durable progress and task replay protection."""
    from app.models.himalayas_ingestion_state import (
        HimalayasIngestionState,
    )

    if not 1 <= max_pages <= 25:
        raise ValueError("max_pages must be between 1 and 25")

    if (automation_run_id is None) != (task_id is None):
        raise ValueError(
            "automation_run_id and task_id must be supplied together."
        )

    if automation_run_id is not None:
        if (
            isinstance(automation_run_id, bool)
            or not isinstance(automation_run_id, int)
            or automation_run_id < 1
        ):
            raise ValueError("automation_run_id must be a positive integer.")
        if (
            isinstance(task_id, bool)
            or not isinstance(task_id, int)
            or task_id < 1
        ):
            raise ValueError("task_id must be a positive integer.")

    now = datetime.now(timezone.utc)

    try:
        # Create the singleton row if this is the first batch.
        db.execute(
            text(
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

        # Never allow manual requests or another run to move an owned cursor.
        if automation_run_id is None:
            if state.automation_run_id is not None:
                raise RuntimeError(
                    "The Himalayas cursor is owned by an automation run."
                )
        elif state.automation_run_id != automation_run_id:
            raise RuntimeError(
                "Automation run does not own the Himalayas ingestion cursor."
            )

        # This check must precede completed-scan reset. A retry of the final
        # task must replay its result rather than start another full scan.
        processed_batches = dict(state.processed_batches or {})
        task_key = str(task_id) if task_id is not None else None

        if task_key is not None and task_key in processed_batches:
            return dict(processed_batches[task_key])

        if state.status == "completed":
            if automation_run_id is not None:
                raise RuntimeError(
                    "The automated ingestion scan is already completed."
                )
            state.cursor = None
            state.status = "running"
            state.pages_fetched = 0
            state.fetched = 0
            state.inserted = 0
            state.updated = 0
            state.expired = 0
            state.started_at = now
            state.completed_at = None
            state.processed_batches = {}
        elif state.started_at is None:
            state.started_at = now

        batch = fetch_himalayas_batch(
            cursor=state.cursor,
            max_pages=max_pages,
        )

        inserted = updated = expired = 0
        corpus_changed = False

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
                    corpus_changed = (
                        _update_existing_job(existing, fields) or corpus_changed
                    )
                    existing.listing_status = "closed"
                    existing.last_seen_at = now
                    updated += 1
                continue

            if existing is None:
                db.add(Job(**fields, last_seen_at=now))
                inserted += 1
                corpus_changed = True
            else:
                corpus_changed = (
                    _update_existing_job(existing, fields) or corpus_changed
                )
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

        result = {
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

        # Save the replay record in the same transaction as job imports and
        # cursor advancement. A crash cannot commit one without the others.
        if task_key is not None:
            processed_batches[task_key] = result
            state.processed_batches = processed_batches

        if corpus_changed:
            mark_job_matching_corpus_changed(db)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
