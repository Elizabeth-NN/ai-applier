import pytest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import (
    AutomationRun,
    AutomationScreeningResult,
    Job,
    Resume,
)
from app.services.automation_queue import create_automation_run


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


def create_records(db):
    resume = Resume(
        user_id="user-1",
        original_filename="resume.pdf",
        storage_key="user-1/resume.pdf",
        content_type="application/pdf",
        size_bytes=1024,
    )

    job = Job(
        title="Junior Python Developer",
        company="Example Company",
        description="Python and FastAPI development.",
    )

    db.add_all([resume, job])
    db.flush()

    run, created = create_automation_run(
        db,
        user_id="user-1",
        pipeline_type="job_screening",
        idempotency_key="screening-run-1",
    )

    assert created is True

    return run, resume, job


def test_screening_result_persists_complete_json_snapshot(db):
    run, resume, job = create_records(db)

    snapshot = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "match_score": 82.5,
        "recommendation": "prioritize",
        "kenya_eligibility": "unknown",
        "listing_status": "active",
        "reasons": ["Strong Python experience match."],
    }

    result = AutomationScreeningResult(
        run_id=run.id,
        user_id="user-1",
        resume_id=resume.id,
        job_id=job.id,
        result=snapshot,
    )

    db.add(result)
    db.commit()

    stored = (
        db.query(AutomationScreeningResult)
        .filter_by(run_id=run.id, job_id=job.id)
        .one()
    )

    assert stored.user_id == "user-1"
    assert stored.resume_id == resume.id
    assert stored.result == snapshot


def test_screening_result_rejects_duplicate_job_in_same_run(db):
    run, resume, job = create_records(db)

    first = AutomationScreeningResult(
        run_id=run.id,
        user_id="user-1",
        resume_id=resume.id,
        job_id=job.id,
        result={"recommendation": "prioritize"},
    )

    second = AutomationScreeningResult(
        run_id=run.id,
        user_id="user-1",
        resume_id=resume.id,
        job_id=job.id,
        result={"recommendation": "review"},
    )

    db.add(first)
    db.commit()

    db.add(second)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()

    assert (
        db.query(AutomationScreeningResult)
        .filter_by(run_id=run.id, job_id=job.id)
        .count()
        == 1
    )


def test_same_job_can_have_result_in_a_later_run(db):
    first_run, resume, job = create_records(db)

    second_run, created = create_automation_run(
        db,
        user_id="user-1",
        pipeline_type="job_screening",
        idempotency_key="screening-run-2",
    )

    assert created is True

    db.add_all([
        AutomationScreeningResult(
            run_id=first_run.id,
            user_id="user-1",
            resume_id=resume.id,
            job_id=job.id,
            result={"recommendation": "review"},
        ),
        AutomationScreeningResult(
            run_id=second_run.id,
            user_id="user-1",
            resume_id=resume.id,
            job_id=job.id,
            result={"recommendation": "prioritize"},
        ),
    ])
    db.commit()

    assert db.query(AutomationScreeningResult).count() == 2
    assert (
        db.query(AutomationScreeningResult)
        .filter_by(run_id=first_run.id)
        .one()
        .result["recommendation"]
        == "review"
    )
    assert (
        db.query(AutomationScreeningResult)
        .filter_by(run_id=second_run.id)
        .one()
        .result["recommendation"]
        == "prioritize"
    )
