from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import AutomationRun, AutomationTask
from app.services.automation_queue import (
    create_automation_run,
    enqueue_automation_task,
    claim_next_task,
    complete_automation_task,
    renew_automation_task_lease,
    fail_automation_task,
    recover_expired_tasks,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    session = factory()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_run(db, user_id="user-1", key="run-1"):
    return create_automation_run(
        db,
        user_id=user_id,
        pipeline_type="job_screening",
        idempotency_key=key,
    )


def test_create_run_returns_existing_run_for_duplicate_key(db):
    first, created_first = create_run(db)
    second, created_second = create_run(db)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert db.query(AutomationRun).count() == 1


def test_create_run_keeps_users_isolated(db):
    first, created_first = create_run(db, user_id="user-1")
    second, created_second = create_run(db, user_id="user-2")

    assert created_first is True
    assert created_second is True
    assert first.id != second.id
    assert db.query(AutomationRun).count() == 2


def test_create_run_rejects_empty_pipeline_type(db):
    with pytest.raises(ValueError, match="pipeline_type"):
        create_automation_run(
            db,
            user_id="user-1",
            pipeline_type=" ",
        )


def test_global_run_rejects_idempotency_key(db):
    with pytest.raises(ValueError, match="Global runs"):
        create_automation_run(
            db,
            user_id=None,
            pipeline_type="job_ingestion",
            idempotency_key="test-idempotency-key-0001",
        )


def test_enqueue_task_returns_existing_task_without_overwriting_payload(db):
    run, _ = create_run(db)

    first, created_first = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="screen-1",
        payload={"resume_id": 10},
    )

    second, created_second = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="screen-1",
        payload={"resume_id": 99},
    )

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert second.payload == {"resume_id": 10}
    assert db.query(AutomationTask).count() == 1


def test_enqueue_task_rejects_different_user_than_run_owner(db):
    run, _ = create_run(db, user_id="user-1")

    with pytest.raises(ValueError, match="ownership"):
        enqueue_automation_task(
            db,
            run_id=run.id,
            user_id="user-2",
            task_type="screen_jobs",
            idempotency_key="screen-1",
        )

    assert db.query(AutomationTask).count() == 0


def test_enqueue_task_rejects_missing_run(db):
    with pytest.raises(ValueError, match="does not exist"):
        enqueue_automation_task(
            db,
            run_id=999,
            user_id="user-1",
            task_type="screen_jobs",
            idempotency_key="screen-1",
        )


def test_enqueue_task_rejects_empty_idempotency_key(db):
    run, _ = create_run(db)

    with pytest.raises(ValueError, match="idempotency_key"):
        enqueue_automation_task(
            db,
            run_id=run.id,
            user_id="user-1",
            task_type="screen_jobs",
            idempotency_key=" ",
        )


def test_enqueue_task_rejects_zero_max_attempts(db):
    run, _ = create_run(db)

    with pytest.raises(ValueError, match="max_attempts"):
        enqueue_automation_task(
            db,
            run_id=run.id,
            user_id="user-1",
            task_type="screen_jobs",
            idempotency_key="screen-1",
            max_attempts=0,
        )


def test_enqueue_global_task_under_global_run(db):
    run, created = create_run(db, user_id=None, key=None)

    task, task_created = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id=None,
        task_type="ingest_jobs",
        idempotency_key="ingest-1",
        payload={"source": "himalayas"},
    )

    assert created is True
    assert task_created is True
    assert task.user_id is None
    assert task.run_id == run.id
    assert task.payload == {"source": "himalayas"}


def test_claim_next_task_assigns_lease_and_increments_attempts(db):
    run, _ = create_run(db)

    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="claim-1",
    )

    now = datetime.now(timezone.utc)

    claimed = claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=120,
        now=now,
    )

    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.locked_by == "worker-1"
    assert claimed.locked_until is not None
    assert claimed.started_at is not None


def test_claim_next_task_returns_oldest_available_task(db):
    run, _ = create_run(db)
    now = datetime.now(timezone.utc)

    later, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="later",
        available_at=now - timedelta(minutes=1),
    )

    earlier, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="earlier",
        available_at=now - timedelta(minutes=5),
    )

    claimed = claim_next_task(
        db,
        worker_id="worker-1",
        now=now,
    )

    assert claimed is not None
    assert claimed.id == earlier.id
    assert claimed.id != later.id


def test_claim_next_task_skips_future_tasks(db):
    run, _ = create_run(db)

    enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="future",
        available_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    claimed = claim_next_task(
        db,
        worker_id="worker-1",
    )

    assert claimed is None


def test_claim_next_task_returns_none_for_empty_queue(db):
    assert claim_next_task(db, worker_id="worker-1") is None


@pytest.mark.parametrize(
    ("worker_id", "lease_seconds", "message"),
    [
        (" ", 60, "worker_id"),
        ("x" * 151, 60, "150 characters"),
        ("worker-1", 0, "lease_seconds"),
    ],
)
def test_claim_next_task_validates_worker_settings(
    db,
    worker_id,
    lease_seconds,
    message,
):
    with pytest.raises(ValueError, match=message):
        claim_next_task(
            db,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )


def test_complete_task_stores_result_and_releases_lease(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="complete-1",
    )

    now = datetime.now(timezone.utc)

    claim_next_task(db, worker_id="worker-1", now=now)

    completed = complete_automation_task(
        db,
        task_id=task.id,
        worker_id="worker-1",
        result={"screened": 25},
        now=now + timedelta(seconds=10),
    )

    assert completed.status == "succeeded"
    assert completed.result == {"screened": 25}
    assert completed.completed_at is not None
    assert completed.locked_by is None
    assert completed.locked_until is None


def test_complete_task_rejects_different_worker(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="complete-owner",
    )

    claim_next_task(db, worker_id="worker-1")

    with pytest.raises(ValueError, match="does not own"):
        complete_automation_task(
            db,
            task_id=task.id,
            worker_id="worker-2",
        )

    db.refresh(task)
    assert task.status == "running"
    assert task.locked_by == "worker-1"


def test_complete_task_rejects_non_running_task(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="complete-state",
    )

    with pytest.raises(ValueError, match="Only running"):
        complete_automation_task(
            db,
            task_id=task.id,
            worker_id="worker-1",
        )


def test_fail_task_requeues_when_attempts_remain(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="retry-1",
        max_attempts=3,
    )

    now = datetime.now(timezone.utc)
    claim_next_task(db, worker_id="worker-1", now=now)

    failed = fail_automation_task(
        db,
        task_id=task.id,
        worker_id="worker-1",
        error="Temporary API failure",
        retry_delay_seconds=120,
        now=now,
    )

    assert failed.status == "queued"
    assert failed.attempts == 1
    assert failed.last_error == "Temporary API failure"
    assert failed.locked_by is None
    assert failed.locked_until is None
    assert failed.completed_at is None

    # SQLite returns timezone-naive datetimes.
    expected = (now + timedelta(seconds=120)).replace(tzinfo=None)
    assert failed.available_at.replace(tzinfo=None) == expected


def test_fail_task_marks_exhausted_task_failed(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="retry-exhausted",
        max_attempts=1,
    )

    now = datetime.now(timezone.utc)
    claim_next_task(db, worker_id="worker-1", now=now)

    failed = fail_automation_task(
        db,
        task_id=task.id,
        worker_id="worker-1",
        error="Permanent failure",
        now=now,
    )

    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.completed_at is not None
    assert failed.last_error == "Permanent failure"
    assert failed.locked_by is None
    assert failed.locked_until is None


def test_fail_task_rejects_different_worker(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="fail-owner",
    )

    claim_next_task(db, worker_id="worker-1")

    with pytest.raises(ValueError, match="does not own"):
        fail_automation_task(
            db,
            task_id=task.id,
            worker_id="worker-2",
            error="Failure",
        )

    db.refresh(task)
    assert task.status == "running"
    assert task.locked_by == "worker-1"


@pytest.mark.parametrize(
    ("error", "retry_delay", "message"),
    [
        (" ", 60, "error"),
        ("Failure", -1, "retry_delay_seconds"),
    ],
)
def test_fail_task_validates_failure_settings(
    db,
    error,
    retry_delay,
    message,
):
    with pytest.raises(ValueError, match=message):
        fail_automation_task(
            db,
            task_id=1,
            worker_id="worker-1",
            error=error,
            retry_delay_seconds=retry_delay,
        )


def test_recover_expired_task_requeues_when_attempts_remain(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="recover-1",
        max_attempts=3,
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=30,
        now=now,
    )

    recovered = recover_expired_tasks(
        db,
        retry_delay_seconds=90,
        now=now + timedelta(seconds=31),
    )

    db.refresh(task)

    assert recovered == 1
    assert task.status == "queued"
    assert task.attempts == 1
    assert task.locked_by is None
    assert task.locked_until is None
    assert "lease expired" in task.last_error.lower()
    expected = (now + timedelta(seconds=121)).replace(tzinfo=None)
    assert task.available_at.replace(tzinfo=None) == expected


def test_recover_expired_task_fails_when_attempts_exhausted(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="recover-exhausted",
        max_attempts=1,
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=30,
        now=now,
    )

    recovered_at = now + timedelta(seconds=31)
    recovered = recover_expired_tasks(db, now=recovered_at)

    db.refresh(task)

    assert recovered == 1
    assert task.status == "failed"
    assert task.completed_at is not None
    assert task.locked_by is None
    assert task.locked_until is None


def test_recover_expired_tasks_ignores_active_leases(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="active-lease",
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=300,
        now=now,
    )

    recovered = recover_expired_tasks(
        db,
        now=now + timedelta(seconds=100),
    )

    db.refresh(task)

    assert recovered == 0
    assert task.status == "running"
    assert task.locked_by == "worker-1"


def test_recover_expired_tasks_respects_batch_size(db):
    run, _ = create_run(db)
    now = datetime.now(timezone.utc)

    tasks = []
    for index in range(3):
        task, _ = enqueue_automation_task(
            db,
            run_id=run.id,
            user_id="user-1",
            task_type="screen_jobs",
            idempotency_key=f"batch-recovery-{index}",
        )
        tasks.append(task)

    for index in range(3):
        claim_next_task(
            db,
            worker_id=f"worker-{index}",
            lease_seconds=10,
            now=now,
        )

    recovered = recover_expired_tasks(
        db,
        batch_size=2,
        now=now + timedelta(seconds=11),
    )

    assert recovered == 2
    assert sum(task.status == "queued" for task in tasks) == 2
    assert sum(task.status == "running" for task in tasks) == 1


@pytest.mark.parametrize(
    ("batch_size", "retry_delay", "message"),
    [
        (0, 60, "batch_size"),
        (10, -1, "retry_delay_seconds"),
    ],
)
def test_recover_expired_tasks_validates_settings(
    db,
    batch_size,
    retry_delay,
    message,
):
    with pytest.raises(ValueError, match=message):
        recover_expired_tasks(
            db,
            batch_size=batch_size,
            retry_delay_seconds=retry_delay,
        )


def test_renew_task_lease_extends_active_lease(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="renew-1",
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=60,
        now=now,
    )

    renewed = renew_automation_task_lease(
        db,
        task_id=task.id,
        worker_id="worker-1",
        lease_seconds=180,
        now=now + timedelta(seconds=30),
    )

    expected = (now + timedelta(seconds=210)).replace(tzinfo=None)
    assert renewed.locked_until.replace(tzinfo=None) == expected
    assert renewed.status == "running"
    assert renewed.locked_by == "worker-1"


def test_renew_task_lease_rejects_expired_lease(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="renew-expired",
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=10,
        now=now,
    )

    with pytest.raises(ValueError, match="lease has expired"):
        renew_automation_task_lease(
            db,
            task_id=task.id,
            worker_id="worker-1",
            now=now + timedelta(seconds=11),
        )


def test_complete_task_rejects_expired_lease(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="complete-expired",
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=10,
        now=now,
    )

    with pytest.raises(ValueError, match="lease has expired"):
        complete_automation_task(
            db,
            task_id=task.id,
            worker_id="worker-1",
            now=now + timedelta(seconds=11),
        )

    db.refresh(task)
    assert task.status == "running"


def test_fail_task_rejects_expired_lease(db):
    run, _ = create_run(db)
    task, _ = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="fail-expired",
    )

    now = datetime.now(timezone.utc)
    claim_next_task(
        db,
        worker_id="worker-1",
        lease_seconds=10,
        now=now,
    )

    with pytest.raises(ValueError, match="lease has expired"):
        fail_automation_task(
            db,
            task_id=task.id,
            worker_id="worker-1",
            error="Late failure",
            now=now + timedelta(seconds=11),
        )

    db.refresh(task)
    assert task.status == "running"

