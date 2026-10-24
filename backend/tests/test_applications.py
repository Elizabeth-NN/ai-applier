from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_user
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app
from app.models.application import Application
from app.models.job import Job


@pytest.fixture
def test_context() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)

    current_user = {"id": "user_test_1"}

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_user] = lambda: current_user["id"]

    with TestClient(app) as client:
        yield {
            "client": client,
            "db_factory": TestingSessionLocal,
            "current_user": current_user,
        }

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_job(db_factory: sessionmaker[Session]) -> int:
    with db_factory() as db:
        job = Job(
            title="Junior Python Developer",
            company="Example Company",
            location="Remote",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def test_create_application_assigns_authenticated_owner(test_context):
    client = test_context["client"]
    job_id = create_job(test_context["db_factory"])

    response = client.post(
        "/api/applications",
        json={"job_id": job_id, "notes": None},
    )

    assert response.status_code == 201
    assert response.json()["job_id"] == job_id
    assert response.json()["status"] == "saved"


def test_list_applications_only_returns_current_users_records(test_context):
    client = test_context["client"]
    db_factory = test_context["db_factory"]
    current_user = test_context["current_user"]
    job_id = create_job(db_factory)

    client.post("/api/applications", json={"job_id": job_id})

    current_user["id"] = "user_test_2"
    second_job_id = create_job(db_factory)
    client.post("/api/applications", json={"job_id": second_job_id})

    response = client.get("/api/applications")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["job_id"] == second_job_id


def test_user_cannot_update_another_users_application(test_context):
    client = test_context["client"]
    db_factory = test_context["db_factory"]
    current_user = test_context["current_user"]
    job_id = create_job(db_factory)

    created = client.post(
        "/api/applications",
        json={"job_id": job_id},
    )
    application_id = created.json()["id"]

    current_user["id"] = "different_user"

    response = client.patch(
        f"/api/applications/{application_id}",
        json={"status": "applied"},
    )

    assert response.status_code == 404


def test_duplicate_application_returns_existing_record(test_context):
    client = test_context["client"]
    job_id = create_job(test_context["db_factory"])
    payload = {"job_id": job_id, "notes": None}

    first = client.post("/api/applications", json=payload)
    second = client.post("/api/applications", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    with test_context["db_factory"]() as db:
        count = (
            db.query(Application)
            .filter_by(user_id="user_test_1", job_id=job_id)
            .count()
        )

    assert count == 1


def test_different_users_can_save_the_same_job(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    job_id = create_job(test_context["db_factory"])

    first = client.post(
        "/api/applications",
        json={"job_id": job_id, "notes": "First user's notes"},
    )

    current_user["id"] = "user_test_2"
    second = client.post(
        "/api/applications",
        json={"job_id": job_id, "notes": "Second user's notes"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    with test_context["db_factory"]() as db:
        count = db.query(Application).filter_by(job_id=job_id).count()

    assert count == 2


def test_duplicate_save_preserves_existing_application(test_context):
    client = test_context["client"]
    job_id = create_job(test_context["db_factory"])

    first = client.post(
        "/api/applications",
        json={"job_id": job_id, "notes": "Original notes"},
    )
    assert first.status_code == 201

    application_id = first.json()["id"]

    updated = client.patch(
        f"/api/applications/{application_id}",
        json={"status": "applied"},
    )
    assert updated.status_code == 200

    duplicate = client.post(
        "/api/applications",
        json={"job_id": job_id, "notes": "Replacement notes"},
    )

    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == application_id
    assert duplicate.json()["status"] == "applied"
    assert duplicate.json()["notes"] == "Original notes"


def test_application_routes_require_authentication(test_context):
    client = test_context["client"]
    db_factory = test_context["db_factory"]
    job_id = create_job(db_factory)

    # Create a record while the test user is authenticated.
    created = client.post(
        "/api/applications",
        json={"job_id": job_id},
    )
    assert created.status_code == 201
    application_id = created.json()["id"]

    # Simulate a request without an authenticated user.
    def reject_user():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    app.dependency_overrides[require_user] = reject_user

    responses = [
        client.get("/api/applications"),
        client.post(
            "/api/applications",
            json={"job_id": job_id},
        ),
        client.patch(
            f"/api/applications/{application_id}",
            json={"status": "applied"},
        ),
    ]

    assert [response.status_code for response in responses] == [
        401,
        401,
        401,
    ]


def test_cannot_save_nonexistent_job(test_context):
    response = test_context["client"].post(
        "/api/applications",
        json={"job_id": 999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_invalid_application_status_is_rejected(test_context):
    client = test_context["client"]
    job_id = create_job(test_context["db_factory"])

    created = client.post(
        "/api/applications",
        json={"job_id": job_id},
    )
    assert created.status_code == 201

    application_id = created.json()["id"]

    response = client.patch(
        f"/api/applications/{application_id}",
        json={"status": "in_progress"},
    )

    assert response.status_code == 422


def test_updating_nonexistent_application_returns_404(test_context):
    response = test_context["client"].patch(
        "/api/applications/999999",
        json={"status": "applied"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"
