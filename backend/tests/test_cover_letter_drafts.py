from collections.abc import Generator

import pytest
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
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    current_user = {"id": "user_test_1"}

    def override_get_db():
        db = testing_session_local()
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
                "db_factory": testing_session_local,
                "current_user": current_user,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_saved_application(
    db_factory: sessionmaker[Session],
    user_id: str = "user_test_1",
) -> int:
    with db_factory() as db:
        job = Job(
            title="Junior Python Developer",
            company="Example Company",
            location="Remote",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        application = Application(
            job_id=job.id,
            user_id=user_id,
            status="saved",
        )
        db.add(application)
        db.commit()
        db.refresh(application)
        return application.id


def create_draft(
    client: TestClient,
    application_id: int,
    content: str = "",
    title: str | None = None,
):
    payload = {"application_id": application_id, "content": content}
    if title is not None:
        payload["title"] = title

    return client.post("/api/cover-letter-drafts", json=payload)


def test_create_draft_for_owned_application(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])

    response = create_draft(
        client,
        application_id,
        "Dear Hiring Manager, I am interested in this role.",
    )

    assert response.status_code == 201
    assert response.json()["application_id"] == application_id
    assert response.json()["content"].startswith("Dear Hiring Manager")
    assert response.json()["id"] > 0


def test_draft_creation_does_not_mark_application_as_applied(test_context):
    client = test_context["client"]
    db_factory = test_context["db_factory"]
    application_id = create_saved_application(db_factory)

    response = create_draft(client, application_id, "Draft text")

    assert response.status_code == 201

    with db_factory() as db:
        application = db.get(Application, application_id)
        assert application.status == "saved"
        assert application.applied_at is None


def test_cannot_create_draft_for_another_users_application(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    application_id = create_saved_application(test_context["db_factory"])

    current_user["id"] = "user_test_2"
    response = create_draft(client, application_id, "Private draft")

    assert response.status_code == 404


def test_list_only_returns_current_users_drafts(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    first_id = create_saved_application(test_context["db_factory"])
    first = create_draft(client, first_id, "First draft")
    assert first.status_code == 201

    current_user["id"] = "user_test_2"
    second_id = create_saved_application(
        test_context["db_factory"],
        user_id=current_user["id"],
    )
    second = create_draft(client, second_id, "Second draft")
    assert second.status_code == 201

    response = client.get("/api/cover-letter-drafts")

    assert response.status_code == 200
    assert [draft["id"] for draft in response.json()] == [second.json()["id"]]


def test_owner_can_read_and_update_draft(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])
    created = create_draft(client, application_id, "Original")
    draft_id = created.json()["id"]

    read_response = client.get(f"/api/cover-letter-drafts/{draft_id}")
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "Original"

    update_response = client.patch(
        f"/api/cover-letter-drafts/{draft_id}",
        json={"content": "Revised cover letter"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "Revised cover letter"


def test_user_cannot_read_or_update_another_users_draft(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    application_id = create_saved_application(test_context["db_factory"])
    created = create_draft(client, application_id, "Private draft")
    draft_id = created.json()["id"]

    current_user["id"] = "user_test_2"

    assert client.get(
        f"/api/cover-letter-drafts/{draft_id}"
    ).status_code == 404

    assert client.patch(
        f"/api/cover-letter-drafts/{draft_id}",
        json={"content": "Attempted edit"},
    ).status_code == 404


def test_draft_requires_a_valid_application_id(test_context):
    response = create_draft(test_context["client"], 999999, "Draft text")
    assert response.status_code == 404


def test_update_rejects_empty_content(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])
    created = create_draft(client, application_id, "Original")

    response = client.patch(
        f"/api/cover-letter-drafts/{created.json()['id']}",
        json={"content": ""},
    )

    assert response.status_code == 422



def test_create_draft_generates_title_from_job_and_company(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])

    response = create_draft(client, application_id, "Cover letter content")

    assert response.status_code == 201
    assert response.json()["title"] == (
        "Junior Python Developer — Example Company"
    )


def test_create_draft_accepts_and_trims_custom_title(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])

    response = create_draft(
        client,
        application_id,
        "Cover letter content",
        title="  Python Developer  —  Example Company  ",
    )

    assert response.status_code == 201
    assert response.json()["title"] == (
        "Python Developer — Example Company"
    )


def test_owner_can_update_title_without_changing_content(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])
    created = create_draft(client, application_id, "Original content")
    draft_id = created.json()["id"]

    response = client.patch(
        f"/api/cover-letter-drafts/{draft_id}",
        json={"title": "Backend Engineer — Example Company"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == (
        "Backend Engineer — Example Company"
    )
    assert response.json()["content"] == "Original content"


def test_update_rejects_blank_title(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])
    created = create_draft(client, application_id, "Original content")

    response = client.patch(
        f"/api/cover-letter-drafts/{created.json()['id']}",
        json={"title": "   "},
    )

    assert response.status_code == 422


def test_update_rejects_empty_payload(test_context):
    client = test_context["client"]
    application_id = create_saved_application(test_context["db_factory"])
    created = create_draft(client, application_id, "Original content")

    response = client.patch(
        f"/api/cover-letter-drafts/{created.json()['id']}",
        json={},
    )

    assert response.status_code == 422
