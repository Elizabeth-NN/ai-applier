"""Background scheduling for Jobicy listing status synchronization."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.job_status_sync import sync_jobicy_statuses

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_scheduled_jobicy_status_sync() -> None:
    """Run one sync with its own database session."""
    db: Session = SessionLocal()

    try:
        counts = sync_jobicy_statuses(db)
        logger.info(
            "Scheduled Jobicy status sync completed: "
            "checked=%s active=%s closed=%s unknown=%s",
            counts["checked"],
            counts["active"],
            counts["closed"],
            counts["unknown"],
        )
    except Exception:
        logger.exception("Scheduled Jobicy status sync failed")
    finally:
        db.close()


def create_jobicy_status_scheduler(
    interval_hours: int,
) -> BackgroundScheduler:
    """Create a scheduler without starting it."""
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        run_scheduled_jobicy_status_sync,
        trigger="interval",
        hours=interval_hours,
        id="jobicy_status_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    return scheduler


def start_jobicy_status_scheduler() -> None:
    """Start the scheduler when background sync is enabled."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = create_jobicy_status_scheduler(
        settings.jobicy_status_sync_interval_hours
    )
    _scheduler.start()

    logger.info(
        "Jobicy status scheduler started; interval=%s hours",
        settings.jobicy_status_sync_interval_hours,
    )


def stop_jobicy_status_scheduler() -> None:
    """Stop the scheduler during application shutdown."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)

    _scheduler = None
