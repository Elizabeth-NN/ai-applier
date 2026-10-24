import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_admin
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app


@pytest.fixture
def job_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: "user_admin"

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def valid_job():
    return {
        "title": "Junior Python Developer",
        "company": "Example Company",
        "location": "Remote",
        "description": "Build and maintain Python applications.",
        "source_url": "https://example.com/jobs/123",
        "employment_type": "Full-time",
    }


def test_authenticated_user_can_create_job(job_context):
    response = job_context.post("/api/jobs", json=valid_job())

    assert response.status_code == 201
    assert response.json()["title"] == "Junior Python Developer"
    assert response.json()["company"] == "Example Company"
    assert response.json()["source_url"] == (
        "https://example.com/jobs/123"
    )
    assert response.json()["id"] > 0


def test_job_creation_requires_authentication(job_context):
    def reject_user():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    app.dependency_overrides[require_admin] = reject_user

    response = job_context.post("/api/jobs", json=valid_job())

    assert response.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 256},
        {"company": ""},
        {"company": "x" * 256},
    ],
)
def test_invalid_job_fields_are_rejected(job_context, overrides):
    payload = valid_job()
    payload.update(overrides)

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_job_listing_is_public_and_supports_pagination(job_context):
    first = job_context.post("/api/jobs", json=valid_job())
    second_payload = valid_job()
    second_payload["title"] = "Junior React Developer"
    second = job_context.post("/api/jobs", json=second_payload)

    assert first.status_code == 201
    assert second.status_code == 201

    response = job_context.get("/api/jobs?skip=0&limit=1")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_invalid_pagination_is_rejected(job_context):
    assert job_context.get("/api/jobs?skip=-1").status_code == 422
    assert job_context.get("/api/jobs?limit=101").status_code == 422


def test_get_existing_job(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    response = job_context.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["id"] == job_id


def test_get_missing_job_returns_404(job_context):
    response = job_context.get("/api/jobs/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_non_admin_cannot_create_job(job_context):
    def reject_non_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    app.dependency_overrides[require_admin] = reject_non_admin

    response = job_context.post("/api/jobs", json=valid_job())

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_created_job_returns_all_fields_and_timestamp(job_context):
    payload = valid_job()

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 201
    data = response.json()

    for field in (
        "title",
        "company",
        "location",
        "description",
        "source_url",
        "employment_type",
    ):
        assert data[field] == payload[field]

    assert data["id"] > 0
    assert data["created_at"]


def test_job_creation_accepts_optional_fields_as_null(job_context):
    payload = {
        "title": "Junior Backend Developer",
        "company": "Example Company",
        "location": None,
        "description": None,
        "source_url": None,
        "employment_type": None,
    }

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 201

    data = response.json()
    assert data["location"] is None
    assert data["description"] is None
    assert data["source_url"] is None
    assert data["employment_type"] is None


@pytest.mark.parametrize("missing_field", ["title", "company"])
def test_job_creation_requires_title_and_company(
    job_context, missing_field
):
    payload = valid_job()
    del payload[missing_field]

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_empty_job_listing_returns_empty_list(job_context):
    response = job_context.get("/api/jobs")

    assert response.status_code == 200
    assert response.json() == []


def test_job_listing_skip_excludes_previously_returned_job(job_context):
    first_payload = valid_job()
    first_payload["title"] = "First Test Job"

    second_payload = valid_job()
    second_payload["title"] = "Second Test Job"

    first_response = job_context.post("/api/jobs", json=first_payload)
    second_response = job_context.post("/api/jobs", json=second_payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    all_jobs = job_context.get("/api/jobs?limit=2")
    skipped_jobs = job_context.get("/api/jobs?skip=1&limit=1")

    assert all_jobs.status_code == 200
    assert skipped_jobs.status_code == 200
    assert len(all_jobs.json()) == 2
    assert len(skipped_jobs.json()) == 1

    all_ids = {job["id"] for job in all_jobs.json()}
    skipped_id = skipped_jobs.json()[0]["id"]

    assert skipped_id in all_ids
    assert len(all_ids) == 2


def test_malformed_job_id_returns_validation_error(job_context):
    response = job_context.get("/api/jobs/not-a-number")

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("location", "x" * 256),
        ("source_url", "x" * 2049),
        ("employment_type", "x" * 101),
    ],
)
def test_optional_fields_enforce_maximum_lengths(
    job_context, field, value
):
    payload = valid_job()
    payload[field] = value

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 422
