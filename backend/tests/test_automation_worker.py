import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.job_matching_corpus_state import JobMatchingCorpusState
from app.models.job_matching_corpus_state import JobMatchingCorpusState
from app.models import (
    AutomationScreeningResult,
    AutomationTask,
    HimalayasIngestionState,
    Job,
    Resume,
    CandidateProfile,
)
from app.schemas.job import JobRead
from app.services.automation_queue import (
    create_automation_run,
    enqueue_automation_task,
)
from app.services.durable_job_screening import (
    prepare_durable_screening_context,
)
from app.services.durable_job_screening import (
    score_durable_screening_batch,
)
from app.services.resume_job_matching import prepare_resume_features
from app.workers import automation_worker
from app.workers.automation_worker import process_screening_task


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
    session.add(JobMatchingCorpusState(id=1, revision=1))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_screening_task(db, *, job_count=2):
    resume = Resume(
        user_id="user-1",
        original_filename="resume.pdf",
        storage_key="user-1/resume.pdf",
        content_type="application/pdf",
        size_bytes=1024,
    )

    jobs = [
        Job(
            title=f"Junior Python Developer {index}",
            company="Example Company",
            description="Python and FastAPI development.",
        )
        for index in range(job_count)
    ]

    db.add(resume)
    db.add_all(jobs)
    db.flush()

    run, created = create_automation_run(
        db,
        user_id="user-1",
        pipeline_type="job_screening",
        idempotency_key="worker-test-run",
    )
    assert created is True

    task, created = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id="user-1",
        task_type="screen_jobs",
        idempotency_key="worker-test-task",
        payload={"resume_id": resume.id},
    )
    assert created is True

    task.status = "running"
    task.locked_by = "worker-1"
    db.commit()
    db.refresh(task)

    return run, task, resume, jobs


def make_match_item(job):
    item = JobRead.model_validate(job).model_dump(mode="json")

    item.update({
        "match_score": 75,
        "matched_terms": ["python"],
        "terms_not_found_in_resume": [],
        "required_terms_found": ["python"],
        "required_terms_not_found": [],
        "preferred_terms_found": [],
        "preferred_terms_not_found": [],
        "term_evidence": {"python": ["Python development"]},
        "match_reasons": ["Python appears in the job description."],
        "profile_match_score": None,
    })

    return item

def test_screening_worker_persists_results_and_updates_run_summary(
    db,
    monkeypatch,
):
    run, task, resume, jobs = create_screening_task(db)

    items = [make_match_item(job) for job in jobs]
    context_calls = []
    batch_calls = []

    def fake_prepare(db, *, user_id, resume_id, max_job_id):
        context_calls.append({
            "user_id": user_id,
            "resume_id": resume_id,
            "max_job_id": max_job_id,
        })
        return {
            "expected_total": len(jobs),
            "max_job_id": max(job.id for job in jobs),
            "profile_data": {
                "target_roles": [],
                "work_preferences": {},
            },
        }

    def fake_score(db, *, context, last_job_id, batch_size):
        batch_calls.append({
            "last_job_id": last_job_id,
            "batch_size": batch_size,
        })

        return [
            item for item in items
            if item["id"] > last_job_id
        ][:1]

    monkeypatch.setattr(
        "app.services.durable_job_screening.prepare_durable_screening_context",
        fake_prepare,
    )
    monkeypatch.setattr(
        "app.services.durable_job_screening.score_durable_screening_batch",
        fake_score,
    )

    result = process_screening_task(
        db,
        task.id,
        worker_id="worker-1",
    )

    assert result == {
        "resume_id": resume.id,
        "total": 2,
        "processed_count": 2,
        "prioritized_count": 0,
        "review_count": 2,
        "excluded_count": 0,
    }

    assert len(context_calls) == 1
    assert context_calls[0]["user_id"] == "user-1"
    assert context_calls[0]["resume_id"] == resume.id

    assert [call["last_job_id"] for call in batch_calls] == [
        0,
        jobs[0].id,
        jobs[1].id,
    ]
    assert all(call["batch_size"] == 100 for call in batch_calls)

    saved = db.scalars(
        select(AutomationScreeningResult).where(
            AutomationScreeningResult.run_id == run.id
        )
    ).all()

    assert len(saved) == 2
    assert {row.job_id for row in saved} == {
        job.id for job in jobs
    }

    for row in saved:
        assert row.user_id == "user-1"
        assert row.resume_id == resume.id
        assert row.result["recommendation"] == "review"
        assert row.result["match_score"] == 75

    db.refresh(run)

    assert run.status == "running"
    assert run.summary["resume_id"] == resume.id
    assert run.summary["expected_total"] == 2
    assert run.summary["processed_count"] == 2
    assert run.summary["review_count"] == 2
    assert run.summary["phase"] == "completed"

def test_screening_worker_resumes_after_persisted_results(
    db,
    monkeypatch,
):
    run, task, resume, jobs = create_screening_task(db, job_count=3)

    # Simulate a result persisted by an earlier worker attempt.
    db.add(
        AutomationScreeningResult(
            run_id=run.id,
            user_id="user-1",
            resume_id=resume.id,
            job_id=jobs[0].id,
            result={
                "recommendation": "prioritize",
                "match_score": 90,
            },
            ranking_score=90,
            match_score=90,
            job_created_at=jobs[0].created_at,
        )
    )
    db.commit()

    context_calls = []
    batch_calls = []
    remaining_items = [make_match_item(job) for job in jobs[1:]]

    def fake_prepare(db, *, user_id, resume_id, max_job_id):
        context_calls.append(max_job_id)
        return {
            "expected_total": 3,
            "max_job_id": max_job_id,
            "profile_data": {
                "target_roles": [],
                "work_preferences": {},
            },
        }

    def fake_score(db, *, context, last_job_id, batch_size):
        batch_calls.append(last_job_id)
        return [
            item for item in remaining_items
            if item["id"] > last_job_id
        ][:batch_size]

    monkeypatch.setattr(
        "app.services.durable_job_screening.prepare_durable_screening_context",
        fake_prepare,
    )
    monkeypatch.setattr(
        "app.services.durable_job_screening.score_durable_screening_batch",
        fake_score,
    )

    result = process_screening_task(
        db,
        task.id,
        worker_id="worker-1",
    )

    assert result == {
        "resume_id": resume.id,
        "total": 3,
        "processed_count": 3,
        "prioritized_count": 1,
        "review_count": 2,
        "excluded_count": 0,
    }

    assert len(context_calls) == 1
    assert batch_calls == [jobs[0].id, jobs[2].id]

    saved = db.scalars(
        select(AutomationScreeningResult).where(
            AutomationScreeningResult.run_id == run.id
        )
    ).all()

    assert len(saved) == 3
    assert {row.job_id for row in saved} == {
        job.id for job in jobs
    }

    db.refresh(run)
    assert run.summary["processed_count"] == 3
    assert run.summary["prioritized_count"] == 1
    assert run.summary["review_count"] == 2
    assert run.summary["last_job_id"] == jobs[2].id

def test_screening_worker_does_not_save_page_after_lease_is_lost(
    db,
    monkeypatch,
):
    run, task, resume, jobs = create_screening_task(db, job_count=1)
    lease_lost = threading.Event()

    def fake_prepare(db, *, user_id, resume_id, max_job_id):
        return {
            "expected_total": 1,
            "max_job_id": jobs[0].id,
            "profile_data": {
                "target_roles": [],
                "work_preferences": {},
            },
        }

    def fake_score(db, *, context, last_job_id, batch_size):
        lease_lost.set()
        return [make_match_item(jobs[0])]

    monkeypatch.setattr(
        "app.services.durable_job_screening.prepare_durable_screening_context",
        fake_prepare,
    )
    monkeypatch.setattr(
        "app.services.durable_job_screening.score_durable_screening_batch",
        fake_score,
    )

    with pytest.raises(RuntimeError, match="lease was lost"):
        process_screening_task(
            db,
            task.id,
            worker_id="worker-1",
            lease_lost=lease_lost,
        )

    saved = db.scalars(
        select(AutomationScreeningResult).where(
            AutomationScreeningResult.run_id == run.id
        )
    ).all()

    assert saved == []


def test_screening_worker_rejects_task_owned_by_another_worker(db):
    run, task, resume, jobs = create_screening_task(db)

    with pytest.raises(ValueError, match="not owned by this worker"):
        process_screening_task(
            db,
            task.id,
            worker_id="different-worker",
        )

    saved = db.scalars(
        select(AutomationScreeningResult).where(
            AutomationScreeningResult.run_id == run.id
        )
    ).all()

    assert saved == []




def create_himalayas_task(db, *, max_pages=25):
    from app.models import AutomationRun

    run = AutomationRun(
        user_id=None,
        pipeline_type="himalayas_ingestion",
        trigger_type="manual",
        status="queued",
        summary={},
    )
    db.add(run)
    db.flush()

    task, created = enqueue_automation_task(
        db,
        run_id=run.id,
        user_id=None,
        task_type="ingest_himalayas_batch",
        idempotency_key="initial-batch",
        payload={"max_pages": max_pages},
    )
    assert created is True

    task.status = "running"
    task.locked_by = "worker-1"

    state = HimalayasIngestionState(
        id=1,
        automation_run_id=run.id,
        status="running",
        cursor="test-cursor",
        processed_batches={},
    )
    db.add(state)
    db.commit()
    db.refresh(task)

    return run, task, state

def prepare_queued_task(db, *, max_attempts=3):
    run, task, resume, jobs = create_screening_task(db)

    task.status = "queued"
    task.locked_by = None
    task.locked_until = None
    task.attempts = 0
    task.max_attempts = max_attempts
    db.commit()
    db.refresh(task)

    return run, task, resume, jobs


def configure_worker_sessions(db, monkeypatch):
    factory = sessionmaker(
        bind=db.get_bind(),
        class_=Session,
        expire_on_commit=False,
    )

    monkeypatch.setattr(automation_worker, "SessionLocal", factory)
    monkeypatch.setattr(
        automation_worker,
        "_heartbeat",
        lambda **kwargs: None,
    )


def test_heartbeat_retries_transient_database_failure(monkeypatch):
    stop_event = threading.Event()
    lease_lost = threading.Event()
    calls = 0

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_renew(db, **kwargs):
        nonlocal calls
        calls += 1

        if calls == 1:
            raise automation_worker.OperationalError(
                "renew lease",
                {},
                RuntimeError("temporary database failure"),
            )

        stop_event.set()

    monkeypatch.setattr(
        automation_worker,
        "SessionLocal",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        automation_worker,
        "renew_automation_task_lease",
        fake_renew,
    )
    monkeypatch.setattr(automation_worker, "HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(automation_worker, "HEARTBEAT_RETRY_SECONDS", 0)

    automation_worker._heartbeat(
        task_id=123,
        worker_id="worker-1",
        stop_event=stop_event,
        lease_lost=lease_lost,
    )

    assert calls == 2
    assert lease_lost.is_set() is False


def test_heartbeat_stops_on_permanent_lease_failure(monkeypatch):
    stop_event = threading.Event()
    lease_lost = threading.Event()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_renew(db, **kwargs):
        raise ValueError("Task is no longer owned by this worker.")

    monkeypatch.setattr(
        automation_worker,
        "SessionLocal",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        automation_worker,
        "renew_automation_task_lease",
        fake_renew,
    )
    monkeypatch.setattr(automation_worker, "HEARTBEAT_SECONDS", 0)

    automation_worker._heartbeat(
        task_id=123,
        worker_id="worker-1",
        stop_event=stop_event,
        lease_lost=lease_lost,
    )

    assert lease_lost.is_set() is True


def test_process_one_task_completes_task_and_reconciles_run(db, monkeypatch):
    run, task, _, _ = prepare_queued_task(db)
    configure_worker_sessions(db, monkeypatch)

    def fake_process(db, task_id, *, worker_id, lease_lost=None):
        assert task_id == task.id
        assert worker_id == "worker-1"
        return {"processed_count": 2, "prioritized_count": 1}

    monkeypatch.setattr(
        automation_worker,
        "process_screening_task",
        fake_process,
    )

    assert automation_worker.process_one_task("worker-1") is True

    db.refresh(task)
    db.refresh(run)

    assert task.status == "succeeded"
    assert task.result == {
        "processed_count": 2,
        "prioritized_count": 1,
    }
    assert task.locked_by is None
    assert run.status == "succeeded"
    assert run.finished_at is not None
    assert run.error_summary is None


def test_process_one_task_requeues_retryable_failure(db, monkeypatch):
    run, task, _, _ = prepare_queued_task(db, max_attempts=2)
    configure_worker_sessions(db, monkeypatch)

    def fake_process(db, task_id, *, worker_id, lease_lost=None):
        raise RuntimeError("Temporary screening failure")

    monkeypatch.setattr(
        automation_worker,
        "process_screening_task",
        fake_process,
    )

    assert automation_worker.process_one_task("worker-1") is True

    db.refresh(task)
    db.refresh(run)

    assert task.status == "queued"
    assert task.attempts == 1
    assert task.last_error is not None
    assert "Temporary screening failure" in task.last_error
    assert task.locked_by is None
    assert run.status == "queued"
    assert run.finished_at is None


def test_process_one_task_marks_exhausted_failure_and_run_failed(
    db,
    monkeypatch,
):
    run, task, _, _ = prepare_queued_task(db, max_attempts=1)
    configure_worker_sessions(db, monkeypatch)

    def fake_process(db, task_id, *, worker_id, lease_lost=None):
        raise RuntimeError("Permanent screening failure")

    monkeypatch.setattr(
        automation_worker,
        "process_screening_task",
        fake_process,
    )

    assert automation_worker.process_one_task("worker-1") is True

    db.refresh(task)
    db.refresh(run)

    assert task.status == "failed"
    assert task.attempts == 1
    assert "Permanent screening failure" in task.last_error
    assert task.locked_by is None
    assert run.status == "failed"
    assert run.finished_at is not None
    assert "Permanent screening failure" in run.error_summary


def test_process_one_task_returns_false_when_queue_is_empty(db, monkeypatch):
    configure_worker_sessions(db, monkeypatch)

    assert automation_worker.process_one_task("worker-1") is False

def test_himalayas_worker_enqueues_successor_for_incomplete_batch(
    db,
    monkeypatch,
):
    run, task, state = create_himalayas_task(db, max_pages=10)

    def fake_ingest(
        db,
        *,
        max_pages,
        automation_run_id,
        task_id,
    ):
        assert max_pages == 10
        assert automation_run_id == run.id
        assert task_id == task.id

        return {
            "pages_fetched": 10,
            "fetched": 200,
            "inserted": 180,
            "updated": 20,
            "expired": 0,
            "pages_this_batch": 10,
            "fetched_this_batch": 200,
            "completed": False,
        }

    monkeypatch.setattr(
        "app.services.job_ingestion.ingest_himalayas_batch",
        fake_ingest,
    )

    result = automation_worker.process_himalayas_ingestion_task(
        db,
        task.id,
        worker_id="worker-1",
    )

    assert result["completed"] is False
    assert result["successor_task_id"] is not None

    successor = db.get(AutomationTask, result["successor_task_id"])
    assert successor is not None
    assert successor.run_id == run.id
    assert successor.user_id is None
    assert successor.task_type == "ingest_himalayas_batch"
    assert successor.status == "queued"
    assert successor.idempotency_key == f"batch-after-{task.id}"
    assert successor.payload == {"max_pages": 10}

    db.refresh(run)
    assert run.status == "running"
    assert run.started_at is not None
    assert run.summary["pages_fetched"] == 10
    assert run.summary["fetched"] == 200
    assert run.summary["inserted"] == 180
    assert run.summary["updated"] == 20
    assert run.summary["completed"] is False

    db.refresh(state)
    assert state.automation_run_id == run.id


def test_himalayas_worker_does_not_enqueue_successor_when_complete(
    db,
    monkeypatch,
):
    run, task, _state = create_himalayas_task(db)

    def fake_ingest(
        db,
        *,
        max_pages,
        automation_run_id,
        task_id,
    ):
        assert automation_run_id == run.id
        assert task_id == task.id

        return {
            "pages_fetched": 3,
            "fetched": 47,
            "inserted": 40,
            "updated": 7,
            "expired": 0,
            "pages_this_batch": 3,
            "fetched_this_batch": 47,
            "completed": True,
        }

    monkeypatch.setattr(
        "app.services.job_ingestion.ingest_himalayas_batch",
        fake_ingest,
    )

    result = automation_worker.process_himalayas_ingestion_task(
        db,
        task.id,
        worker_id="worker-1",
    )

    assert result["completed"] is True
    assert result["successor_task_id"] is None

    tasks = db.scalars(
        select(AutomationTask).where(
            AutomationTask.run_id == run.id
        )
    ).all()

    assert len(tasks) == 1
    assert tasks[0].id == task.id

    db.refresh(run)
    assert run.status == "running"
    assert run.summary["pages_fetched"] == 3
    assert run.summary["fetched"] == 47
    assert run.summary["completed"] is True

def test_durable_screening_scores_jobs_in_id_order_and_respects_batch_size(db):
    run, task, resume, jobs = create_screening_task(db, job_count=3)

    context = {
        "max_job_id": max(job.id for job in jobs),
        "resume_features": prepare_resume_features("Python FastAPI"),
        "resume_section_features": {},
        "has_profile_evidence": False,
        "term_weights": {},
    }

    first_batch = score_durable_screening_batch(
        db,
        context=context,
        last_job_id=0,
        batch_size=2,
    )

    assert len(first_batch) == 2
    assert [item["id"] for item in first_batch] == [
        jobs[0].id,
        jobs[1].id,
    ]

    second_batch = score_durable_screening_batch(
        db,
        context=context,
        last_job_id=first_batch[-1]["id"],
        batch_size=2,
    )

    assert len(second_batch) == 1
    assert second_batch[0]["id"] == jobs[2].id
    assert second_batch[0]["match_score"] >= 0
    assert second_batch[0]["match_score"] <= 100

def test_durable_screening_includes_profile_evidence(db):
    run, task, resume, jobs = create_screening_task(
        db,
        job_count=1,
    )

    resume_features = prepare_resume_features("Python FastAPI")
    profile_features = prepare_resume_features("React")

    context = {
        "max_job_id": jobs[0].id,
        "resume_features": resume_features,
        "resume_section_features": {},
        "profile_section_features": {
            "skills": profile_features,
        },
        "profile_features": profile_features,
        "combined_features": resume_features | profile_features,
        "has_profile_evidence": True,
        "term_weights": {},
    }

    items = score_durable_screening_batch(
        db,
        context=context,
        batch_size=10,
    )

    assert len(items) == 1
    assert items[0]["profile_match_score"] is not None
    assert "profile_matched_terms" in items[0]
    assert "profile_only_matched_terms" in items[0]
    assert "profile_term_evidence" in items[0]

def test_durable_screening_prepares_resume_profile_and_corpus(
    db,
    monkeypatch,
):
    run, task, resume, jobs = create_screening_task(db, job_count=3)

    profile = CandidateProfile(
        user_id="user-1",
        headline="Backend Developer",
        professional_summary="Python backend developer",
        skills=["Python", "FastAPI"],
        experience=[],
        projects=[],
        education=[],
        certifications=[],
        target_roles=["Backend Developer"],
        work_preferences={"remote_only": True},
    )
    db.add(profile)
    db.commit()

    monkeypatch.setattr(
        "app.services.durable_job_screening.resumes_api._resolve_stored_path",
        lambda resume: Path("/tmp/resume.pdf"),
    )
    monkeypatch.setattr(
        "app.services.durable_job_screening.extract_resume_text",
        lambda path, filename: "Python FastAPI developer",
    )
    monkeypatch.setattr(
        "app.services.durable_job_screening.parse_resume_text",
        lambda text: {},
    )

    from app.services import durable_job_screening

    original_build = durable_job_screening.build_term_weights
    build_calls = 0

    def tracked_build(documents):
        nonlocal build_calls
        build_calls += 1
        return original_build(documents)

    monkeypatch.setattr(
        durable_job_screening,
        "build_term_weights",
        tracked_build,
    )

    context = prepare_durable_screening_context(
        db,
        user_id="user-1",
        resume_id=resume.id,
    )

    assert build_calls == 1

    # Same revision and job boundary should reuse the cached weights.
    cached_context = prepare_durable_screening_context(
        db,
        user_id="user-1",
        resume_id=resume.id,
    )
    assert build_calls == 1
    assert cached_context["term_weights"] == context["term_weights"]

    # Changing the corpus revision must force a rebuild.
    corpus_state = db.get(JobMatchingCorpusState, 1)
    corpus_state.revision += 1
    corpus_state.term_weights = None
    db.commit()

    refreshed_context = prepare_durable_screening_context(
        db,
        user_id="user-1",
        resume_id=resume.id,
    )
    assert build_calls == 2
    assert refreshed_context["term_weights"] == context["term_weights"]

    # An older run boundary must not overwrite the full-corpus cache.
    older_max_job_id = sorted(job.id for job in jobs)[-2]
    older_context = prepare_durable_screening_context(
        db,
        user_id="user-1",
        resume_id=resume.id,
        max_job_id=older_max_job_id,
    )
    assert older_context["expected_total"] == 2
    assert build_calls == 3

    # The full-corpus cache should still be available.
    final_context = prepare_durable_screening_context(
        db,
        user_id="user-1",
        resume_id=resume.id,
    )
    assert final_context["term_weights"] == context["term_weights"]
    assert build_calls == 3

    assert context["resume_id"] == resume.id
    assert context["max_job_id"] == max(job.id for job in jobs)
    assert context["expected_total"] == 3
    assert context["has_profile_evidence"] is True
    assert context["resume_features"]
    assert context["profile_features"]
    assert context["combined_features"] == (
        context["resume_features"] | context["profile_features"]
    )
    assert context["term_weights"]
    assert "target_roles" not in context["profile_data"]
    assert "work_preferences" not in context["profile_data"]

def test_durable_screening_rejects_resume_owned_by_another_user(db):
    run, task, resume, jobs = create_screening_task(db, job_count=1)

    with pytest.raises(
        ValueError,
        match="Resume not found or does not belong to this user.",
    ):
        prepare_durable_screening_context(
            db,
            user_id="another-user",
            resume_id=resume.id,
        )
