"""Background worker for durable automation tasks."""

import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import AutomationRun, AutomationTask
from app.services.automation_queue import (
    claim_next_task,
    complete_automation_task,
    fail_automation_task,
    recover_expired_tasks,
    renew_automation_task_lease,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 3
RECOVERY_INTERVAL_SECONDS = 30
LEASE_SECONDS = 180
HEARTBEAT_SECONDS = 45


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)



def process_screening_task(
    db: Session,
    task_id: int,
    *,
    worker_id: str,
    lease_lost: threading.Event | None = None,
) -> dict:
    """Screen all jobs against the user's selected resume and persist results."""
    from app.models import (
        AutomationRun,
        AutomationScreeningResult,
        AutomationTask,
        CandidateProfile,
        Job,
        Resume,
    )
    from app.schemas.job import JobScreeningItem
    from app.services.automation_screening import save_screening_results
    from app.services.job_screening import screen_job

    from app.services.durable_job_screening import (
        prepare_durable_screening_context,
        score_durable_screening_batch,
    )

    task = db.get(AutomationTask, task_id)
    if task is None or task.status != "running":
        raise ValueError("Screening task is missing or not running.")

    if not worker_id or task.locked_by != worker_id:
        raise ValueError("Screening task is not owned by this worker.")

    if lease_lost is not None and lease_lost.is_set():
        raise RuntimeError("Task lease was lost.")

    if task.task_type != "screen_jobs" or not task.user_id:
        raise ValueError("Task is not a valid user screening task.")

    run = db.get(AutomationRun, task.run_id)
    if run is None or run.user_id != task.user_id:
        raise ValueError("Automation run ownership validation failed.")

    if run.pipeline_type != "job_screening":
        raise ValueError("Automation run is not a job-screening run.")

    payload = task.payload or {}
    resume_id = payload.get("resume_id")

    if isinstance(resume_id, bool) or not isinstance(resume_id, int) or resume_id < 1:
        raise ValueError("Task payload must contain a valid resume_id.")

    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != task.user_id:
        raise ValueError("Selected resume does not belong to this user.")

    profile = db.query(CandidateProfile).filter(
        CandidateProfile.user_id == task.user_id
    ).first()

    profile_data = {
        "target_roles": profile.target_roles if profile else [],
        "work_preferences": profile.work_preferences if profile else {},
    }

    run.status = "running"
    if run.started_at is None:
        run.started_at = _utc_now()

    summary = dict(run.summary or {})
    corpus_max_job_id = summary.get("corpus_max_job_id")

    if corpus_max_job_id is None:
        corpus_max_job_id = db.scalar(select(func.max(Job.id))) or 0
        summary["corpus_max_job_id"] = corpus_max_job_id
    elif (
        isinstance(corpus_max_job_id, bool)
        or not isinstance(corpus_max_job_id, int)
        or corpus_max_job_id < 0
    ):
        raise ValueError("Stored corpus_max_job_id is invalid.")

    summary["phase"] = "preparing_corpus"
    summary["resume_id"] = resume_id
    run.summary = summary
    db.commit()

    if lease_lost is not None and lease_lost.is_set():
        raise RuntimeError("Task lease was lost before corpus preparation.")

    context = prepare_durable_screening_context(
        db,
        user_id=task.user_id,
        resume_id=resume_id,
        max_job_id=corpus_max_job_id,
    )

    if lease_lost is not None and lease_lost.is_set():
        raise RuntimeError("Task lease was lost during corpus preparation.")

    expected_total = context["expected_total"]

    existing_results = db.scalars(
        select(AutomationScreeningResult).where(
            AutomationScreeningResult.run_id == run.id,
            AutomationScreeningResult.user_id == task.user_id,
            AutomationScreeningResult.resume_id == resume_id,
        )
    ).all()

    processed = len(existing_results)
    last_job_id = max(
        (result.job_id for result in existing_results),
        default=0,
    )

    prioritized = 0
    review = 0
    excluded = 0

    for existing in existing_results:
        recommendation = (existing.result or {}).get("recommendation")
        if recommendation == "prioritize":
            prioritized += 1
        elif recommendation == "review":
            review += 1
        elif recommendation == "exclude":
            excluded += 1

    run.summary = {
        **(run.summary or {}),
        "phase": "screening",
        "expected_total": expected_total,
        "processed_count": processed,
        "prioritized_count": prioritized,
        "review_count": review,
        "excluded_count": excluded,
        "last_job_id": last_job_id,
    }
    db.commit()

    while True:
        if lease_lost is not None and lease_lost.is_set():
            raise RuntimeError("Task lease was lost during screening.")

        items = score_durable_screening_batch(
            db,
            context=context,
            last_job_id=last_job_id,
            batch_size=100,
        )

        if not items:
            break

        screening_results = []
        batch_prioritized = 0
        batch_review = 0
        batch_excluded = 0

        for item in items:
            screening = screen_job(
                item,
                profile=profile_data,
                match=item,
            )

            validated = JobScreeningItem.model_validate({
                **item,
                **screening,
            })

            result = validated.model_dump(mode="json")
            screening_results.append(result)

            recommendation = result.get("recommendation")
            if recommendation == "prioritize":
                batch_prioritized += 1
            elif recommendation == "review":
                batch_review += 1
            elif recommendation == "exclude":
                batch_excluded += 1

        if lease_lost is not None and lease_lost.is_set():
            raise RuntimeError(
                "Task lease was lost before saving screening results."
            )

        save_screening_results(
            db,
            run_id=run.id,
            user_id=task.user_id,
            resume_id=resume_id,
            results=screening_results,
        )

        processed += len(screening_results)
        prioritized += batch_prioritized
        review += batch_review
        excluded += batch_excluded
        last_job_id = max(item["id"] for item in items)

        run.summary = {
            **(run.summary or {}),
            "phase": "screening",
            "expected_total": expected_total,
            "processed_count": processed,
            "prioritized_count": prioritized,
            "review_count": review,
            "excluded_count": excluded,
            "last_job_id": last_job_id,
        }
        db.commit()

    run.summary = {
        **(run.summary or {}),
        "phase": "completed",
        "expected_total": expected_total,
        "processed_count": processed,
        "prioritized_count": prioritized,
        "review_count": review,
        "excluded_count": excluded,
        "last_job_id": last_job_id,
    }
    db.commit()

    return {
        "resume_id": resume_id,
        "total": expected_total,
        "processed_count": processed,
        "prioritized_count": prioritized,
        "review_count": review,
        "excluded_count": excluded,
    }


def process_himalayas_ingestion_task(
    db: Session,
    task_id: int,
    *,
    worker_id: str,
    lease_lost: threading.Event | None = None,
) -> dict:
    """Process one durable batch of the shared Himalayas job feed."""
    from app.services.automation_queue import enqueue_automation_task
    from app.services.job_ingestion import ingest_himalayas_batch

    task = db.get(AutomationTask, task_id)
    if task is None or task.status != "running":
        raise ValueError("Himalayas ingestion task is missing or not running.")

    if not worker_id or task.locked_by != worker_id:
        raise ValueError("Himalayas ingestion task is not owned by this worker.")

    if lease_lost is not None and lease_lost.is_set():
        raise RuntimeError("Task lease was lost.")

    if task.task_type != "ingest_himalayas_batch" or task.user_id is not None:
        raise ValueError("Task is not a valid global Himalayas ingestion task.")

    run = db.get(AutomationRun, task.run_id)
    if (
        run is None
        or run.user_id is not None
        or run.pipeline_type != "himalayas_ingestion"
    ):
        raise ValueError("Himalayas automation run validation failed.")

    payload = task.payload or {}
    max_pages = payload.get("max_pages", 25)
    if (
        isinstance(max_pages, bool)
        or not isinstance(max_pages, int)
        or not 1 <= max_pages <= 25
    ):
        raise ValueError("Task payload max_pages must be an integer from 1 to 25.")

    result = ingest_himalayas_batch(
        db,
        max_pages=max_pages,
        automation_run_id=run.id,
        task_id=task.id,
    )

    if lease_lost is not None and lease_lost.is_set():
        raise RuntimeError("Task lease was lost after ingestion.")

    successor_id = None
    if not result["completed"]:
        successor, _created = enqueue_automation_task(
            db,
            run_id=run.id,
            user_id=None,
            task_type="ingest_himalayas_batch",
            idempotency_key=f"batch-after-{task.id}",
            payload={"max_pages": max_pages},
        )
        successor_id = successor.id

    run.status = "running"
    if run.started_at is None:
        run.started_at = _utc_now()

    run.summary = {
        **(run.summary or {}),
        "pages_fetched": result["pages_fetched"],
        "fetched": result["fetched"],
        "inserted": result["inserted"],
        "updated": result["updated"],
        "expired": result["expired"],
        "last_batch_pages": result["pages_this_batch"],
        "last_batch_fetched": result["fetched_this_batch"],
        "completed": result["completed"],
    }
    db.commit()

    return {
        **result,
        "successor_task_id": successor_id,
    }


def _heartbeat(
    *,
    task_id: int,
    worker_id: str,
    stop_event: threading.Event,
    lease_lost: threading.Event,
) -> None:
    """Renew the task lease from an independent database session."""
    while not stop_event.wait(HEARTBEAT_SECONDS):
        try:
            with SessionLocal() as db:
                renew_automation_task_lease(
                    db,
                    task_id=task_id,
                    worker_id=worker_id,
                    lease_seconds=LEASE_SECONDS,
                )
        except Exception:
            logger.exception("Lease renewal failed for task %s", task_id)
            lease_lost.set()
            return


def _reconcile_run(db: Session, run_id: int) -> None:
    """Derive a run's status from all its tasks."""
    run = db.get(AutomationRun, run_id)
    if run is None:
        return

    tasks = db.scalars(
        select(AutomationTask).where(AutomationTask.run_id == run_id)
    ).all()

    if not tasks:
        return

    statuses = {task.status for task in tasks}

    if "running" in statuses:
        new_status = "running"
    elif "queued" in statuses:
        new_status = "queued"
    elif "failed" in statuses:
        new_status = "failed"
    elif statuses == {"succeeded"}:
        new_status = "succeeded"
    else:
        return

    run.status = new_status

    if new_status in {"succeeded", "failed"}:
        run.finished_at = run.finished_at or _utc_now()

    if new_status == "failed":
        failed_task = next(
            (task for task in tasks if task.status == "failed"),
            None,
        )
        if failed_task is not None:
            run.error_summary = (
                failed_task.last_error or "An automation task failed."
            )[:4000]
    elif new_status == "succeeded":
        run.error_summary = None

    db.commit()


def _reconcile_all_runs(db: Session) -> None:
    """Reconcile parent runs after task recovery or completion."""
    run_ids = db.scalars(
        select(AutomationTask.run_id).distinct()
    ).all()

    for run_id in run_ids:
        _reconcile_run(db, run_id)


def process_one_task(worker_id: str) -> bool:
    """Claim and process one task. Return False when the queue is empty."""
    with SessionLocal() as db:
        task = claim_next_task(
            db,
            worker_id=worker_id,
            lease_seconds=LEASE_SECONDS,
        )
        if task is None:
            return False

        task_id = task.id
        run_id = task.run_id
        task_type = task.task_type

    stop_event = threading.Event()
    lease_lost = threading.Event()

    heartbeat = threading.Thread(
        target=_heartbeat,
        kwargs={
            "task_id": task_id,
            "worker_id": worker_id,
            "stop_event": stop_event,
            "lease_lost": lease_lost,
        },
        name=f"automation-heartbeat-{task_id}",
        daemon=True,
    )
    heartbeat.start()

    try:
        with SessionLocal() as db:
            if task_type == "screen_jobs":
                result = process_screening_task(
                    db,
                    task_id=task_id,
                    worker_id=worker_id,
                    lease_lost=lease_lost,
                )
            elif task_type == "ingest_himalayas_batch":
                result = process_himalayas_ingestion_task(
                    db,
                    task_id=task_id,
                    worker_id=worker_id,
                    lease_lost=lease_lost,
                )
            else:
                raise ValueError(f"Unsupported automation task type: {task_type}")

        stop_event.set()
        heartbeat.join()

        if lease_lost.is_set():
            raise RuntimeError("Task lease was lost before completion.")

        with SessionLocal() as db:
            complete_automation_task(
                db,
                task_id=task_id,
                worker_id=worker_id,
                result=result,
            )

        logger.info("Automation task %s completed.", task_id)

    except Exception as exc:
        stop_event.set()
        heartbeat.join()

        if not lease_lost.is_set():
            try:
                with SessionLocal() as db:
                    failed_task = fail_automation_task(
                        db,
                        task_id=task_id,
                        worker_id=worker_id,
                        error=str(exc),
                    )
                    logger.warning(
                        "Task %s ended with status %s (attempt %s/%s).",
                        task_id,
                        failed_task.status,
                        failed_task.attempts,
                        failed_task.max_attempts,
                    )
            except Exception:
                logger.exception(
                    "Could not record failure for task %s. "
                    "Lease recovery will handle it if it expires.",
                    task_id,
                )
        else:
            logger.warning(
                "Task %s lost its lease. Leaving recovery to the queue.",
                task_id,
            )

        logger.exception("Automation task %s did not complete.", task_id)

    finally:
        stop_event.set()
        heartbeat.join()

    try:
        with SessionLocal() as db:
            _reconcile_run(db, run_id)
    except Exception:
        logger.exception("Could not reconcile automation run %s.", run_id)

    return True


def run_worker(
    worker_id: str | None = None,
    poll_seconds: int = POLL_SECONDS,
) -> None:
    """Continuously recover expired leases and process queued tasks."""
    if poll_seconds < 1:
        raise ValueError("poll_seconds must be at least 1.")

    worker_id = worker_id or f"automation-worker-{uuid.uuid4()}"
    last_recovery = 0.0

    logger.info("Automation worker started: %s", worker_id)

    while True:
        now = time.monotonic()

        if now - last_recovery >= RECOVERY_INTERVAL_SECONDS:
            try:
                with SessionLocal() as db:
                    recovered = recover_expired_tasks(db)
                    _reconcile_all_runs(db)

                if recovered:
                    logger.warning("Recovered %s expired task(s).", recovered)

            except Exception:
                logger.exception("Task recovery cycle failed.")

            last_recovery = now

        processed = process_one_task(worker_id)

        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Automation worker stopped.")
