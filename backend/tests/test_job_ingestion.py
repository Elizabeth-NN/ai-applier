from datetime import datetime, timezone

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



def test_ingestion_preserves_verified_metadata_when_feed_is_unknown(
    db_session, monkeypatch
):
    existing = Job(
        title="Original Python Developer",
        company="Example Company",
        location="Kenya",
        description="Existing detailed description.",
        source_url="https://jobicy.com/jobs/123",
        employment_type="Full-time",
        source_name="jobicy",
        source_job_id="123",
        remote_type="remote",
        eligible_countries=["Kenya"],
        eligibility_status="eligible",
        listing_status="active",
    )
    db_session.add(existing)
    db_session.commit()

    fields = incoming_job(title="Updated Python Developer")
    fields["location"] = None
    fields["description"] = None
    fields["employment_type"] = None

    monkeypatch.setattr(
        job_ingestion,
        "fetch_jobicy_jobs",
        lambda: [fields],
    )

    result = job_ingestion.ingest_jobicy_jobs(db_session)

    db_session.refresh(existing)

    assert result == {"fetched": 1, "inserted": 0, "updated": 1}
    assert existing.title == "Updated Python Developer"
    assert existing.eligible_countries == ["Kenya"]
    assert existing.eligibility_status == "eligible"
    assert existing.listing_status == "active"
    assert existing.location == "Kenya"
    assert existing.description == "Existing detailed description."
    assert existing.employment_type == "Full-time"
    assert existing.last_seen_at is not None

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


def incoming_himalayas_job(title="Remote Python Developer", expires_at=None):
    from datetime import datetime, timedelta, timezone

    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    return {
        "title": title,
        "company": "Example Company",
        "location": "Kenya",
        "description": "Build backend services.",
        "source_url": (
            "https://himalayas.app/companies/example/jobs/python-developer"
            "?utm_source=api"
        ),
        "application_url": (
            "https://himalayas.app/jobs/apply/python-developer"
        ),
        "employment_type": "Full-time",
        "source_name": "himalayas",
        "source_job_id": (
            "https://himalayas.app/companies/example/jobs/python-developer"
        ),
        "remote_type": "remote",
        "eligible_countries": None,
        "eligibility_status": "unknown",
        "listing_status": "unknown",
        "published_at": None,
        "expires_at": expires_at,
    }


def test_himalayas_ingestion_inserts_active_job(db_session, monkeypatch):
    fields = incoming_himalayas_job()
    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_jobs", lambda: [fields]
    )

    result = job_ingestion.ingest_himalayas_jobs(db_session)
    job = db_session.scalar(
        select(Job).where(Job.source_name == "himalayas")
    )

    assert result == {
        "fetched": 1, "inserted": 1, "updated": 0, "expired": 0
    }
    assert job is not None
    assert job.source_url == fields["source_url"]
    assert job.source_job_id == fields["source_job_id"]
    assert job.expires_at is not None


def test_himalayas_ingestion_updates_without_duplicate(
    db_session, monkeypatch
):
    fields = incoming_himalayas_job()
    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_jobs", lambda: [fields]
    )
    job_ingestion.ingest_himalayas_jobs(db_session)

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_jobs",
        lambda: [incoming_himalayas_job(title="Updated Developer")],
    )
    result = job_ingestion.ingest_himalayas_jobs(db_session)

    assert result["inserted"] == 0
    assert result["updated"] == 1
    assert db_session.scalar(select(func.count()).select_from(Job)) == 1
    job = db_session.scalar(
        select(Job).where(Job.source_name == "himalayas")
    )
    assert job.title == "Updated Developer"


def test_himalayas_ingestion_preserves_verified_metadata(
    db_session, monkeypatch
):
    verified_at = datetime.now(timezone.utc)
    fields = incoming_himalayas_job()
    fields.update(
        eligible_countries=["Kenya"],
        eligibility_status="eligible",
        listing_status="active",
        eligibility_evidence_url="https://example.com/kenya-eligibility",
        eligibility_evidence="Reviewed evidence",
        eligibility_verified_at=verified_at,
        eligibility_verified_by="admin-1",
    )
    existing = Job(**fields)
    db_session.add(existing)
    db_session.commit()

    incoming = incoming_himalayas_job(title="Refreshed Developer")
    incoming["eligible_countries"] = ["United States"]
    incoming["eligibility_status"] = "unknown"

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_jobs",
        lambda: [incoming],
    )
    job_ingestion.ingest_himalayas_jobs(db_session)
    db_session.refresh(existing)

    assert existing.title == "Refreshed Developer"
    assert existing.eligible_countries == ["Kenya"]
    assert existing.eligibility_status == "eligible"
    assert existing.listing_status == "active"
    assert existing.eligibility_evidence_url == (
        "https://example.com/kenya-eligibility"
    )
    assert existing.eligibility_evidence == "Reviewed evidence"
    assert existing.eligibility_verified_at == verified_at.replace(tzinfo=None)
    assert existing.eligibility_verified_by == "admin-1"


def test_himalayas_ingestion_preserves_existing_application_url(
    db_session, monkeypatch
):
    fields = incoming_himalayas_job()
    existing = Job(**fields)
    existing.application_url = (
        "https://boards.greenhouse.io/example/jobs/123"
    )
    db_session.add(existing)
    db_session.commit()

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_jobs",
        lambda: [incoming_himalayas_job()],
    )

    job_ingestion.ingest_himalayas_jobs(db_session)
    db_session.refresh(existing)

    assert existing.application_url == (
        "https://boards.greenhouse.io/example/jobs/123"
    )
    assert existing.source_url == fields["source_url"]

def test_himalayas_ingestion_skips_new_expired_job(
    db_session, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    fields = incoming_himalayas_job(
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_jobs", lambda: [fields]
    )

    result = job_ingestion.ingest_himalayas_jobs(db_session)

    assert result == {
        "fetched": 1, "inserted": 0, "updated": 0, "expired": 1
    }
    assert db_session.scalar(select(func.count()).select_from(Job)) == 0


def test_himalayas_ingestion_closes_previously_imported_expired_job(
    db_session, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    fields = incoming_himalayas_job()
    fields["listing_status"] = "active"
    existing = Job(**fields)
    db_session.add(existing)
    db_session.commit()

    existing.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_jobs", lambda: []
    )

    job_ingestion.ingest_himalayas_jobs(db_session)
    db_session.refresh(existing)

    assert existing.listing_status == "closed"


def test_himalayas_ingestion_failure_does_not_change_existing_jobs(
    db_session, monkeypatch
):
    from app.services.himalayas_adapter import HimalayasAPIError

    fields = incoming_himalayas_job()
    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_jobs", lambda: [fields]
    )
    job_ingestion.ingest_himalayas_jobs(db_session)

    existing = db_session.scalar(
        select(Job).where(Job.source_name == "himalayas")
    )
    original_seen_at = existing.last_seen_at

    def failed_fetch():
        raise HimalayasAPIError("Simulated upstream failure")

    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_jobs", failed_fetch
    )
    with pytest.raises(HimalayasAPIError):
        job_ingestion.ingest_himalayas_jobs(db_session)

    db_session.expire_all()
    unchanged = db_session.scalar(
        select(Job).where(Job.source_name == "himalayas")
    )
    assert unchanged.last_seen_at == original_seen_at
    assert unchanged.listing_status == "unknown"


def test_himalayas_batch_persists_cursor_and_resumes(
    db_session, monkeypatch
):
    from app.models.himalayas_ingestion_state import (
        HimalayasIngestionState,
    )

    first = incoming_himalayas_job()
    second = incoming_himalayas_job()
    second["source_job_id"] = (
        "https://himalayas.app/companies/example/jobs/second"
    )

    batches = iter([
        {
            "jobs": [first],
            "next_cursor": "cursor-two",
            "pages_fetched": 1,
            "complete": False,
        },
        {
            "jobs": [second],
            "next_cursor": None,
            "pages_fetched": 1,
            "complete": True,
        },
    ])
    received_cursors = []

    def fake_fetch(*, cursor=None, max_pages=5):
        received_cursors.append(cursor)
        return next(batches)

    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_batch", fake_fetch,
        raising=False,
    )

    first_result = job_ingestion.ingest_himalayas_batch(db_session)
    second_result = job_ingestion.ingest_himalayas_batch(db_session)

    state = db_session.get(HimalayasIngestionState, 1)

    assert received_cursors == [None, "cursor-two"]
    assert first_result["status"] == "running"
    assert first_result["completed"] is False
    assert second_result["status"] == "completed"
    assert second_result["completed"] is True
    assert second_result["fetched"] == 2
    assert second_result["inserted"] == 2
    assert state.cursor is None
    assert state.pages_fetched == 2


def test_himalayas_batch_failure_does_not_advance_saved_cursor(
    db_session, monkeypatch
):
    from app.models.himalayas_ingestion_state import (
        HimalayasIngestionState,
    )
    from app.services.himalayas_adapter import HimalayasAPIError

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_batch",
        lambda **_kwargs: {
            "jobs": [],
            "next_cursor": "saved-cursor",
            "pages_fetched": 1,
            "complete": False,
        },
        raising=False,
    )
    job_ingestion.ingest_himalayas_batch(db_session)

    before = db_session.get(HimalayasIngestionState, 1)
    assert before.cursor == "saved-cursor"
    assert before.pages_fetched == 1

    def fail_fetch(**_kwargs):
        raise HimalayasAPIError("Simulated upstream failure")

    monkeypatch.setattr(
        job_ingestion, "fetch_himalayas_batch", fail_fetch,
        raising=False,
    )

    with pytest.raises(HimalayasAPIError):
        job_ingestion.ingest_himalayas_batch(db_session)

    db_session.expire_all()
    after = db_session.get(HimalayasIngestionState, 1)

    assert after.cursor == "saved-cursor"
    assert after.pages_fetched == 1


def test_partial_himalayas_batch_does_not_close_absent_jobs(
    db_session, monkeypatch
):
    existing_fields = incoming_himalayas_job()
    existing_fields["listing_status"] = "active"
    existing = Job(**existing_fields)
    db_session.add(existing)
    db_session.commit()

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_batch",
        lambda **_kwargs: {
            "jobs": [],
            "next_cursor": "next-page",
            "pages_fetched": 1,
            "complete": False,
        },
        raising=False,
    )

    result = job_ingestion.ingest_himalayas_batch(db_session)
    db_session.refresh(existing)

    assert result["status"] == "running"
    assert existing.listing_status == "active"

def test_himalayas_batch_replay_is_safe_after_later_tasks(
    db_session, monkeypatch
):
    from app.models.himalayas_ingestion_state import (
        HimalayasIngestionState,
    )
    from app.services.automation_queue import create_automation_run

    run, created = create_automation_run(
        db_session,
        user_id=None,
        pipeline_type="himalayas_ingestion",
        trigger_type="manual",
    )
    assert created is True

    db_session.add(
        HimalayasIngestionState(
            id=1,
            automation_run_id=run.id,
            status="running",
            processed_batches={},
        )
    )
    db_session.commit()

    batches = iter([
        {
            "jobs": [],
            "next_cursor": "cursor-after-task-101",
            "pages_fetched": 1,
            "complete": False,
        },
        {
            "jobs": [],
            "next_cursor": None,
            "pages_fetched": 1,
            "complete": True,
        },
    ])
    received_cursors = []

    def fake_fetch(*, cursor=None, max_pages=5):
        received_cursors.append(cursor)
        return next(batches)

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_batch",
        fake_fetch,
        raising=False,
    )

    first_result = job_ingestion.ingest_himalayas_batch(
        db_session,
        max_pages=1,
        automation_run_id=run.id,
        task_id=101,
    )
    second_result = job_ingestion.ingest_himalayas_batch(
        db_session,
        max_pages=1,
        automation_run_id=run.id,
        task_id=102,
    )

    # Retry the older task after the newer task has completed the scan.
    replay_result = job_ingestion.ingest_himalayas_batch(
        db_session,
        max_pages=1,
        automation_run_id=run.id,
        task_id=101,
    )

    db_session.expire_all()
    state = db_session.get(HimalayasIngestionState, 1)

    assert first_result["completed"] is False
    assert second_result["completed"] is True
    assert replay_result == first_result
    assert received_cursors == [None, "cursor-after-task-101"]
    assert state.status == "completed"
    assert state.pages_fetched == 2
    assert set(state.processed_batches) == {"101", "102"}


def test_manual_himalayas_batch_rejects_automation_owned_cursor(
    db_session, monkeypatch
):
    from app.models.himalayas_ingestion_state import (
        HimalayasIngestionState,
    )
    from app.services.automation_queue import create_automation_run

    run, created = create_automation_run(
        db_session,
        user_id=None,
        pipeline_type="himalayas_ingestion",
        trigger_type="manual",
    )
    assert created is True

    db_session.add(
        HimalayasIngestionState(
            id=1,
            automation_run_id=run.id,
            status="running",
            processed_batches={},
        )
    )
    db_session.commit()

    def unexpected_fetch(**_kwargs):
        raise AssertionError("Fetch must not run while automation owns the cursor")

    monkeypatch.setattr(
        job_ingestion,
        "fetch_himalayas_batch",
        unexpected_fetch,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="owned by an automation run"):
        job_ingestion.ingest_himalayas_batch(db_session)

    db_session.expire_all()
    state = db_session.get(HimalayasIngestionState, 1)

    assert state.automation_run_id == run.id
    assert state.status == "running"
    assert state.pages_fetched == 0
