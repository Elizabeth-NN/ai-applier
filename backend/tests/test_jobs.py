import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_user
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
    app.dependency_overrides[require_user] = lambda: "user_test_1"

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

    app.dependency_overrides[require_user] = reject_user

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
