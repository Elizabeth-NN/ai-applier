"""Synchronize the verified status of imported Jobicy listings."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.services.jobicy_adapter import fetch_jobicy_statuses


def sync_jobicy_statuses(db: Session) -> dict[str, int]:
    """Update listing statuses only after all requested status checks succeed."""
    jobs = db.scalars(
        select(Job).where(
            Job.source_name == "jobicy",
            Job.source_job_id.is_not(None),
        )
    ).all()

    valid_ids = list(
        dict.fromkeys(
            job.source_job_id
            for job in jobs
            if job.source_job_id
            and job.source_job_id.isdigit()
            and int(job.source_job_id) > 0
        )
    )

    # Nothing to check when the catalog contains no valid Jobicy IDs.
    # Avoid unnecessary API calls for catalogs containing only manual jobs.
    if not valid_ids:
        return {"checked": 0, "active": 0, "closed": 0, "unknown": 0}

    # Fetch all batches before changing any database records. If an API
    # request fails, existing statuses remain untouched.
    statuses = fetch_jobicy_statuses(valid_ids)
    checked_at = datetime.now(timezone.utc)

    counts = {"checked": 0, "active": 0, "closed": 0, "unknown": 0}

    try:
        for job in jobs:
            source_id = job.source_job_id or ""

            # Never change a listing whose status was not verified by
            # the source API.
            if source_id not in statuses:
                continue

            status_value = statuses[source_id]
            job.listing_status = status_value
            job.listing_status_checked_at = checked_at
                                                                    

            counts["checked"] += 1
            counts[status_value] += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    return counts
