import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.job import Job
from app.services import job_ingestion
from app.services.jobicy_adapter import JobicyAPIError


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def incoming_job(title="Remote Python Developer", source_id="123"):
    return {
        "title": title,
        "company": "Example Company",
        "location": "Worldwide",
        "description": "Build backend services.",
        "source_url": f"https://jobicy.com/jobs/{source_id}",
        "employment_type": "Full-time",
        "source_name": "jobicy",
        "source_job_id": source_id,
        "remote_type": "remote",
        "eligible_countries": None,
        "eligibility_status": "unknown",
        "listing_status": "unknown",
        "published_at": None,
    }


def test_ingestion_inserts_new_job(db_session, monkeypatch):
    monkeypatch.setattr(
        job_ingestion,
        "fetch_jobicy_jobs",
        lambda: [incoming_job()],
    )

    result = job_ingestion.ingest_jobicy_jobs(db_session)

    assert result == {"fetched": 1, "inserted": 1, "updated": 0}

    job = db_session.scalar(select(Job))
    assert job is not None
    assert job.source_name == "jobicy"
    assert job.source_job_id == "123"
    assert job.last_seen_at is not None


def test_ingestion_updates_existing_job_without_duplicate(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        job_ingestion,
        "fetch_jobicy_jobs",
        lambda: [incoming_job()],
    )
    first_result = job_ingestion.ingest_jobicy_jobs(db_session)

    monkeypatch.setattr(
        job_ingestion,
        "fetch_jobicy_jobs",
        lambda: [incoming_job(title="Updated Python Developer")],
    )
    second_result = job_ingestion.ingest_jobicy_jobs(db_session)

    count = db_session.scalar(select(func.count()).select_from(Job))
    job = db_session.scalar(select(Job))

    assert first_result["inserted"] == 1
    assert second_result == {"fetched": 1, "inserted": 0, "updated": 1}
    assert count == 1
    assert job.title == "Updated Python Developer"


def test_ingestion_failure_does_not_change_existing_jobs(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        job_ingestion,
        "fetch_jobicy_jobs",
        lambda: [incoming_job()],
    )
    job_ingestion.ingest_jobicy_jobs(db_session)

    original_job = db_session.scalar(select(Job))
    original_seen_at = original_job.last_seen_at

    def failed_fetch():
        raise JobicyAPIError("Simulated upstream failure")

    monkeypatch.setattr(job_ingestion, "fetch_jobicy_jobs", failed_fetch)

    with pytest.raises(JobicyAPIError):
        job_ingestion.ingest_jobicy_jobs(db_session)

    db_session.expire_all()
    unchanged_job = db_session.scalar(select(Job))

    assert unchanged_job.title == "Remote Python Developer"
    assert unchanged_job.last_seen_at == original_seen_at
    assert unchanged_job.listing_status == "unknown"


def test_manual_jobs_remain_separate_from_imported_jobs(
    db_session, monkeypatch
):
    manual = Job(
        title="Manually Added Developer",
        company="Manual Company",
        source_name=None,
        source_job_id=None,
    )
    db_session.add(manual)
    db_session.commit()

    monkeypatch.setattr(
        job_ingestion,
        "fetch_jobicy_jobs",
        lambda: [incoming_job()],
    )
    result = job_ingestion.ingest_jobicy_jobs(db_session)

    count = db_session.scalar(select(func.count()).select_from(Job))

    assert result["inserted"] == 1
    assert count == 2
