from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.automation_run import AutomationRun
from app.models.automation_task import AutomationTask


def create_automation_run(
    db: Session,
    *,
    user_id: str | None,
    pipeline_type: str,
    trigger_type: str = "manual",
    idempotency_key: str | None = None,
) -> tuple[AutomationRun, bool]:
    """Create a run, returning an existing user-scoped run for duplicate keys."""

    if not pipeline_type.strip():
        raise ValueError("pipeline_type cannot be empty.")

    if user_id is None and idempotency_key is not None:
        raise ValueError(
            "Global runs cannot currently use idempotency keys."
        )

    if user_id is not None and idempotency_key:
        existing = db.scalar(
            select(AutomationRun).where(
                AutomationRun.user_id == user_id,
                AutomationRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing, False

    run = AutomationRun(
        user_id=user_id,
        pipeline_type=pipeline_type.strip(),
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        status="queued",
        summary={},
    )

    db.add(run)

    try:
        db.commit()
        db.refresh(run)
        return run, True
    except IntegrityError:
        db.rollback()

        # A concurrent request may have created the same user-scoped run.
        if user_id is not None and idempotency_key:
            existing = db.scalar(
                select(AutomationRun).where(
                    AutomationRun.user_id == user_id,
                    AutomationRun.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return existing, False

        raise


def enqueue_automation_task(
    db: Session,
    *,
    run_id: int,
    user_id: str | None,
    task_type: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 3,
    available_at: datetime | None = None,
) -> tuple[AutomationTask, bool]:
    """Enqueue a task, returning the existing task for a duplicate run/key."""

    if not task_type.strip():
        raise ValueError("task_type cannot be empty.")

    if not idempotency_key.strip():
        raise ValueError("idempotency_key cannot be empty.")

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    run = db.get(AutomationRun, run_id)
    if run is None:
        raise ValueError("Automation run does not exist.")

    if run.user_id != user_id:
        raise ValueError("Task ownership must match its automation run.")

    existing = db.scalar(
        select(AutomationTask).where(
            AutomationTask.run_id == run_id,
            AutomationTask.idempotency_key == idempotency_key,
        )
    )

    if existing is not None:
        if existing.user_id != user_id or existing.task_type != task_type:
            raise ValueError(
                "The idempotency key is already used by a different task."
            )
        return existing, False

    task = AutomationTask(
        run_id=run_id,
        user_id=user_id,
        task_type=task_type.strip(),
        idempotency_key=idempotency_key,
        payload=payload or {},
        max_attempts=max_attempts,
        available_at=available_at,
        status="queued",
    )

    db.add(task)

    try:
        db.commit()
        db.refresh(task)
        return task, True
    except IntegrityError:
        db.rollback()

        # Another request may have enqueued the same task concurrently.
        existing = db.scalar(
            select(AutomationTask).where(
                AutomationTask.run_id == run_id,
                AutomationTask.idempotency_key == idempotency_key,
            )
        )

        if existing is not None:
            if existing.user_id != user_id or existing.task_type != task_type:
                raise ValueError(
                    "The idempotency key is already used by a different task."
                )
            return existing, False

        raise


def claim_next_task(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> AutomationTask | None:
    """Atomically claim the oldest available queued task."""

    from datetime import timedelta, timezone

    if not worker_id.strip():
        raise ValueError("worker_id cannot be empty.")

    if len(worker_id) > 150:
        raise ValueError("worker_id cannot exceed 150 characters.")

    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1.")

    claimed_at = now or datetime.now(timezone.utc)

    statement = (
        select(AutomationTask)
        .where(
            AutomationTask.status == "queued",
            AutomationTask.available_at <= claimed_at,
            AutomationTask.attempts < AutomationTask.max_attempts,
        )
        .order_by(
            AutomationTask.available_at.asc(),
            AutomationTask.id.asc(),
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    try:
        task = db.scalar(statement)

        if task is None:
            db.rollback()
            return None

        task.status = "running"
        task.attempts += 1
        task.locked_by = worker_id
        task.locked_until = claimed_at + timedelta(seconds=lease_seconds)

        if task.started_at is None:
            task.started_at = claimed_at

        db.commit()
        db.refresh(task)
        return task

    except Exception:
        db.rollback()
        raise



def _utc_datetime(value: datetime) -> datetime:
    """Normalize SQLite and PostgreSQL datetimes for UTC comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def renew_automation_task_lease(
    db: Session,
    *,
    task_id: int,
    worker_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> AutomationTask:
    """Extend an active task lease owned by this worker."""

    if not worker_id.strip():
        raise ValueError("worker_id cannot be empty.")

    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1.")

    renewed_at = now or datetime.now(timezone.utc)

    try:
        task = db.scalar(
            select(AutomationTask)
            .where(AutomationTask.id == task_id)
            .with_for_update()
        )

        if task is None:
            raise ValueError("Automation task does not exist.")

        if task.status != "running":
            raise ValueError("Only running tasks can renew a lease.")

        if task.locked_by != worker_id:
            raise ValueError("Worker does not own this task.")

        if (
            task.locked_until is None
            or _utc_datetime(task.locked_until) <= _utc_datetime(renewed_at)
        ):
            raise ValueError("Worker lease has expired.")

        task.locked_until = renewed_at + timedelta(seconds=lease_seconds)

        db.commit()
        db.refresh(task)
        return task

    except Exception:
        db.rollback()
        raise


def complete_automation_task(
    db: Session,
    *,
    task_id: int,
    worker_id: str,
    result: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AutomationTask:
    """Complete a running task owned by the specified worker."""

    from datetime import timezone

    if not worker_id.strip():
        raise ValueError("worker_id cannot be empty.")

    completed_at = now or datetime.now(timezone.utc)

    try:
        task = db.scalar(
            select(AutomationTask)
            .where(AutomationTask.id == task_id)
            .with_for_update()
        )

        if task is None:
            raise ValueError("Automation task does not exist.")

        if task.status != "running":
            raise ValueError("Only running tasks can be completed.")

        if task.locked_by != worker_id:
            raise ValueError("Worker does not own this task.")

        if (
            task.locked_until is None
            or _utc_datetime(task.locked_until) <= _utc_datetime(completed_at)
        ):
            raise ValueError("Worker lease has expired.")

        task.status = "succeeded"
        task.result = result
        task.completed_at = completed_at
        task.locked_by = None
        task.locked_until = None

        db.commit()
        db.refresh(task)
        return task

    except Exception:
        db.rollback()
        raise


def fail_automation_task(
    db: Session,
    *,
    task_id: int,
    worker_id: str,
    error: str,
    retry_delay_seconds: int = 60,
    now: datetime | None = None,
) -> AutomationTask:
    """Record a task failure and retry it if attempts remain."""

    from datetime import timedelta, timezone

    if not worker_id.strip():
        raise ValueError("worker_id cannot be empty.")

    if not error.strip():
        raise ValueError("error cannot be empty.")

    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative.")

    failed_at = now or datetime.now(timezone.utc)

    try:
        task = db.scalar(
            select(AutomationTask)
            .where(AutomationTask.id == task_id)
            .with_for_update()
        )

        if task is None:
            raise ValueError("Automation task does not exist.")

        if task.status != "running":
            raise ValueError("Only running tasks can be failed.")

        if task.locked_by != worker_id:
            raise ValueError("Worker does not own this task.")

        if (
            task.locked_until is None
            or _utc_datetime(task.locked_until) <= _utc_datetime(failed_at)
        ):
            raise ValueError("Worker lease has expired.")

        task.last_error = error.strip()[:4000]
        task.locked_by = None
        task.locked_until = None

        if task.attempts < task.max_attempts:
            task.status = "queued"
            task.available_at = failed_at + timedelta(
                seconds=retry_delay_seconds
            )
        else:
            task.status = "failed"
            task.completed_at = failed_at

        db.commit()
        db.refresh(task)
        return task

    except Exception:
        db.rollback()
        raise


def recover_expired_tasks(
    db: Session,
    *,
    batch_size: int = 100,
    retry_delay_seconds: int = 60,
    now: datetime | None = None,
) -> int:
    """Recover expired worker leases, returning the number of tasks recovered."""

    from datetime import timedelta, timezone

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative.")

    recovered_at = now or datetime.now(timezone.utc)

    statement = (
        select(AutomationTask)
        .where(
            AutomationTask.status == "running",
            AutomationTask.locked_until <= recovered_at,
        )
        .order_by(
            AutomationTask.locked_until.asc(),
            AutomationTask.id.asc(),
        )
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    try:
        tasks = list(db.scalars(statement).all())

        for task in tasks:
            task.last_error = "Worker lease expired before task completion."
            task.locked_by = None
            task.locked_until = None

            if task.attempts < task.max_attempts:
                task.status = "queued"
                task.available_at = recovered_at + timedelta(
                    seconds=retry_delay_seconds
                )
            else:
                task.status = "failed"
                task.completed_at = recovered_at

        if tasks:
            db.commit()
        else:
            db.rollback()

        return len(tasks)

    except Exception:
        db.rollback()
        raise
