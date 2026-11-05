from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_user
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app
from app.models.application import Application
from app.models.application_campaign import ApplicationCampaign
from app.models.application_execution import ApplicationExecution
from app.models.job import Job


@pytest.fixture
def campaign_context() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    current_user = {"id": "user_test_1"}

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_user] = lambda: current_user["id"]

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "db_factory": factory,
                "current_user": current_user,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_campaign(client: TestClient, **overrides):
    payload = {
        "name": "500 Applications in 8 Weeks",
        **overrides,
    }
    return client.post("/api/application-campaigns", json=payload)


def create_execution(
    db,
    *,
    user_id: str,
    campaign_id: int,
    application_id: int,
    status: str,
    submitted_at: datetime | None,
    idempotency_key: str,
):
    execution = ApplicationExecution(
        user_id=user_id,
        application_id=application_id,
        campaign_id=campaign_id,
        resume_id=None,
        resume_filename_snapshot="resume.pdf",
        resume_sha256="a" * 64,
        cover_letter_snapshot=None,
        job_snapshot={"title": "Junior Python Developer"},
        application_payload={},
        target_url="https://example.com/jobs/123",
        ats_platform="unsupported",
        status=status,
        idempotency_key=idempotency_key,
        submitted_at=submitted_at,
    )
    db.add(execution)


def test_create_campaign_uses_500_target_and_56_day_default(
    campaign_context,
):
    response = create_campaign(campaign_context["client"])

    assert response.status_code == 201
    body = response.json()

    assert body["name"] == "500 Applications in 8 Weeks"
    assert body["target_applications"] == 500
    assert body["status"] == "draft"

    starts_on = date.fromisoformat(body["starts_on"])
    deadline_on = date.fromisoformat(body["deadline_on"])

    assert deadline_on == starts_on + timedelta(days=56)


def test_create_campaign_accepts_custom_target_and_dates(campaign_context):
    response = create_campaign(
        campaign_context["client"],
        name="Backend Developer Search",
        target_applications=100,
        starts_on="2026-11-01",
        deadline_on="2026-12-31",
    )

    assert response.status_code == 201
    body = response.json()

    assert body["target_applications"] == 100
    assert body["starts_on"] == "2026-11-01"
    assert body["deadline_on"] == "2026-12-31"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"name": "Invalid target", "target_applications": 0},
        {
            "name": "Invalid dates",
            "starts_on": "2026-11-10",
            "deadline_on": "2026-11-10",
        },
        {
            "name": "Invalid dates",
            "starts_on": "2026-11-11",
            "deadline_on": "2026-11-10",
        },
    ],
)
def test_create_campaign_rejects_invalid_data(campaign_context, payload):
    response = create_campaign(campaign_context["client"], **payload)

    assert response.status_code == 422


def test_list_campaigns_only_returns_current_users_campaigns(
    campaign_context,
):
    client = campaign_context["client"]

    first = create_campaign(client, name="First campaign")
    assert first.status_code == 201

    campaign_context["current_user"]["id"] = "user_test_2"

    second = create_campaign(client, name="Second campaign")
    assert second.status_code == 201

    response = client.get("/api/application-campaigns")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == second.json()["id"]


def test_user_cannot_get_or_update_another_users_campaign(
    campaign_context,
):
    client = campaign_context["client"]

    created = create_campaign(client)
    campaign_id = created.json()["id"]

    campaign_context["current_user"]["id"] = "user_test_2"

    assert client.get(
        f"/api/application-campaigns/{campaign_id}"
    ).status_code == 404

    assert client.patch(
        f"/api/application-campaigns/{campaign_id}",
        json={"name": "Unauthorized change"},
    ).status_code == 404

    assert client.get(
        f"/api/application-campaigns/{campaign_id}/progress"
    ).status_code == 404


def test_update_campaign_changes_settings_and_status(campaign_context):
    client = campaign_context["client"]

    created = create_campaign(client)
    campaign_id = created.json()["id"]

    response = client.patch(
        f"/api/application-campaigns/{campaign_id}",
        json={
            "name": "Updated campaign",
            "target_applications": 250,
            "status": "active",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["name"] == "Updated campaign"
    assert body["target_applications"] == 250
    assert body["status"] == "active"


def test_update_campaign_rejects_invalid_deadline(campaign_context):
    client = campaign_context["client"]

    created = create_campaign(
        client,
        starts_on="2026-11-10",
        deadline_on="2026-12-10",
    )
    campaign_id = created.json()["id"]

    response = client.patch(
        f"/api/application-campaigns/{campaign_id}",
        json={"deadline_on": "2026-11-01"},
    )

    assert response.status_code == 422


def test_campaign_progress_counts_only_confirmed_submissions(
    campaign_context,
):
    client = campaign_context["client"]

    created = create_campaign(
        client,
        target_applications=10,
        starts_on=date.today().isoformat(),
        deadline_on=(date.today() + timedelta(days=7)).isoformat(),
    )
    assert created.status_code == 201
    campaign_id = created.json()["id"]

    with campaign_context["db_factory"]() as db:
        job = Job(
            title="Junior Python Developer",
            company="Example Company",
            location="Remote",
        )
        db.add(job)
        db.flush()

        application = Application(
            job_id=job.id,
            user_id="user_test_1",
            status="saved",
        )
        db.add(application)
        db.flush()

        now = datetime.now(timezone.utc)

        # This one counts: submitted and has a timestamp.
        create_execution(
            db,
            user_id="user_test_1",
            campaign_id=campaign_id,
            application_id=application.id,
            status="submitted",
            submitted_at=now,
            idempotency_key="confirmed-submission",
        )

        # This does not count: submitted without a timestamp.
        create_execution(
            db,
            user_id="user_test_1",
            campaign_id=campaign_id,
            application_id=application.id,
            status="submitted",
            submitted_at=None,
            idempotency_key="missing-timestamp",
        )

        # This does not count: approved but not submitted.
        create_execution(
            db,
            user_id="user_test_1",
            campaign_id=campaign_id,
            application_id=application.id,
            status="approved",
            submitted_at=None,
            idempotency_key="approved-only",
        )

        # This does not count: prepared.
        create_execution(
            db,
            user_id="user_test_1",
            campaign_id=campaign_id,
            application_id=application.id,
            status="prepared",
            submitted_at=None,
            idempotency_key="prepared-only",
        )

        db.commit()

    response = client.get(
        f"/api/application-campaigns/{campaign_id}/progress"
    )

    assert response.status_code == 200
    body = response.json()

    assert body["target_applications"] == 10
    assert body["submitted"] == 1
    assert body["remaining"] == 9
    assert body["percentage"] == 10.0
    assert body["days_remaining"] == 7
    assert body["required_per_week"] == 9.0


def test_campaign_progress_does_not_count_other_users_executions(
    campaign_context,
):
    client = campaign_context["client"]

    created = create_campaign(client, target_applications=10)
    campaign_id = created.json()["id"]

    with campaign_context["db_factory"]() as db:
        job = Job(
            title="Junior Python Developer",
            company="Example Company",
            location="Remote",
        )
        db.add(job)
        db.flush()

        application = Application(
            job_id=job.id,
            user_id="user_test_1",
            status="saved",
        )
        db.add(application)
        db.flush()

        create_execution(
            db,
            user_id="user_test_2",
            campaign_id=campaign_id,
            application_id=application.id,
            status="submitted",
            submitted_at=datetime.now(timezone.utc),
            idempotency_key="other-user-submission",
        )
        db.commit()

    response = client.get(
        f"/api/application-campaigns/{campaign_id}/progress"
    )

    assert response.status_code == 200
    assert response.json()["submitted"] == 0
    assert response.json()["remaining"] == 10


def test_update_campaign_rejects_null_status(campaign_context):
    client = campaign_context["client"]
    created = create_campaign(client)
    campaign_id = created.json()["id"]

    response = client.patch(
        f"/api/application-campaigns/{campaign_id}",
        json={"status": None},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Campaign status cannot be null"

    unchanged = client.get(f"/api/application-campaigns/{campaign_id}")
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "draft"
