import threading

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import (
    AutomationScreeningResult,
    AutomationTask,
    Job,
    Resume,
)
from app.schemas.job import JobRead
from app.services.automation_queue import (
    create_automation_run,
    enqueue_automation_task,
)
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
    matcher_calls = []

    def fake_matcher(*, user_id, resume_id, skip, limit, db):
        matcher_calls.append({
            "user_id": user_id,
            "resume_id": resume_id,
            "skip": skip,
            "limit": limit,
        })

        return {
            "items": items[skip:skip + limit],
            "total": len(items),
        }

    monkeypatch.setattr(
        "app.api.jobs.match_jobs_to_resume",
        fake_matcher,
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

    assert len(matcher_calls) == 1
    assert matcher_calls[0]["skip"] == 0
    assert matcher_calls[0]["limit"] == 100

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


def test_screening_worker_does_not_save_page_after_lease_is_lost(
    db,
    monkeypatch,
):
    run, task, resume, jobs = create_screening_task(db, job_count=1)
    lease_lost = threading.Event()

    def fake_matcher(*, user_id, resume_id, skip, limit, db):
        lease_lost.set()

        return {
            "items": [make_match_item(jobs[0])],
            "total": 1,
        }

    monkeypatch.setattr(
        "app.api.jobs.match_jobs_to_resume",
        fake_matcher,
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
