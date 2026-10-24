import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.job import Job
from app.services import job_status_sync
from app.services.jobicy_adapter import (
    JOBICY_STATUS_API_URL,
    JobicyAPIError,
    fetch_jobicy_statuses,
)


def make_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://jobicy.com",
    )


def test_status_adapter_parses_active_closed_and_unknown():
    def handler(request):
        assert request.url.path == "/api/jobs/status"
        assert request.url.params["ids"] == "1,2,3"
        return httpx.Response(
            200,
            json={
                "success": True,
                "jobs": [
                    {"id": 1, "status": "active"},
                    {"id": 2, "status": "closed"},
                    {"id": 3, "status": "unknown"},
                ],
            },
        )

    with make_client(handler) as client:
        result = fetch_jobicy_statuses(["1", "2", "3"], client=client)

    assert result == {
        "1": "active",
        "2": "closed",
        "3": "unknown",
    }


def test_status_adapter_batches_more_than_100_ids():
    requests = []

    def handler(request):
        requests.append(request)
        ids = request.url.params["ids"].split(",")
        return httpx.Response(
            200,
            json={
                "success": True,
                "jobs": [
                    {"id": int(source_id), "status": "active"}
                    for source_id in ids
                ],
            },
        )

    source_ids = [str(number) for number in range(1, 103)]

    with make_client(handler) as client:
        result = fetch_jobicy_statuses(source_ids, client=client)

    assert len(requests) == 2
    assert len(requests[0].url.params["ids"].split(",")) == 100
    assert len(requests[1].url.params["ids"].split(",")) == 2
    assert len(result) == 102


def test_status_adapter_rejects_missing_statuses():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "jobs": [{"id": 1, "status": "active"}],
            },
        )

    with make_client(handler) as client:
        with pytest.raises(JobicyAPIError, match="omitted"):
            fetch_jobicy_statuses(["1", "2"], client=client)


def test_status_adapter_rejects_http_failure():
    def handler(_request):
        return httpx.Response(503, json={"success": False})

    with make_client(handler) as client:
        with pytest.raises(JobicyAPIError):
            fetch_jobicy_statuses(["1"], client=client)


def test_status_adapter_rejects_invalid_ids():
    with pytest.raises(ValueError):
        fetch_jobicy_statuses(["not-an-id"])


def test_status_adapter_empty_ids_make_no_requests():
    assert fetch_jobicy_statuses([]) == {}


def test_status_endpoint_constant():
    assert JOBICY_STATUS_API_URL == "https://jobicy.com/api/jobs/status"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def add_job(db, source_id, listing_status="unknown"):
    job = Job(
        title=f"Developer {source_id}",
        company="Example Company",
        source_name="jobicy",
        source_job_id=source_id,
        source_url=f"https://jobicy.com/jobs/{source_id}",
        listing_status=listing_status,
    )
    db.add(job)
    db.commit()
    return job


def test_sync_updates_statuses_from_source(db_session, monkeypatch):
    add_job(db_session, "1")
    add_job(db_session, "2")
    add_job(db_session, "3")

    monkeypatch.setattr(
        job_status_sync,
        "fetch_jobicy_statuses",
        lambda ids: {
            "1": "active",
            "2": "closed",
            "3": "unknown",
        },
    )

    result = job_status_sync.sync_jobicy_statuses(db_session)

    jobs = db_session.scalars(select(Job).order_by(Job.source_job_id)).all()

    assert result == {
        "checked": 3,
        "active": 1,
        "closed": 1,
        "unknown": 1,
    }
    assert [job.listing_status for job in jobs] == [
        "active",
        "closed",
        "unknown",
    ]


def test_sync_failure_preserves_existing_statuses(db_session, monkeypatch):
    add_job(db_session, "1", listing_status="active")
    add_job(db_session, "2", listing_status="closed")

    def fail(_ids):
        raise JobicyAPIError("Simulated API failure")

    monkeypatch.setattr(job_status_sync, "fetch_jobicy_statuses", fail)

    with pytest.raises(JobicyAPIError):
        job_status_sync.sync_jobicy_statuses(db_session)

    db_session.expire_all()
    jobs = db_session.scalars(select(Job).order_by(Job.source_job_id)).all()

    assert [job.listing_status for job in jobs] == ["active", "closed"]


def test_sync_ignores_manual_jobs(db_session, monkeypatch):
    db_session.add(
        Job(title="Manual role", company="Manual Company", listing_status="unknown")
    )
    db_session.commit()

    monkeypatch.setattr(
        job_status_sync,
        "fetch_jobicy_statuses",
        lambda _ids: pytest.fail("No Jobicy IDs should be checked"),
    )

    result = job_status_sync.sync_jobicy_statuses(db_session)

    assert result == {"checked": 0, "active": 0, "closed": 0, "unknown": 0}
