from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_user
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app
from app.models.application import Application
from app.models.application_batch import ApplicationBatch, ApplicationBatchItem
from app.models.application_execution import ApplicationExecution
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


def save_job(client: TestClient, job_id: int) -> None:
    response = client.post(
        "/api/applications",
        json={"job_id": job_id},
    )
    assert response.status_code in (200, 201)


def create_saved_job(test_context: dict) -> int:
    job_id = create_job(test_context["db_factory"])
    save_job(test_context["client"], job_id)
    return job_id


def create_batch(
    client: TestClient,
    job_ids: list[int],
    campaign_id: int | None = None,
):
    return client.post(
        "/api/application-batches",
        json={
            "name": "Review batch",
            "job_ids": job_ids,
            "campaign_id": campaign_id,
        },
    )


def test_create_batch_contains_saved_jobs_unselected_by_default(test_context):
    client = test_context["client"]
    first_job = create_saved_job(test_context)
    second_job = create_saved_job(test_context)

    response = create_batch(client, [first_job, second_job])

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Review batch"
    assert body["status"] == "draft"
    assert {item["job_id"] for item in body["items"]} == {
        first_job,
        second_job,
    }
    assert all(item["selected"] is False for item in body["items"])
    assert all(item["approved_at"] is None for item in body["items"])


def test_batch_rejects_duplicate_job_ids(test_context):
    job_id = create_saved_job(test_context)

    response = create_batch(test_context["client"], [job_id, job_id])

    assert response.status_code == 422


def test_batch_rejects_jobs_not_saved_by_current_user(test_context):
    client = test_context["client"]
    saved_job_id = create_saved_job(test_context)
    unsaved_job_id = create_job(test_context["db_factory"])

    response = create_batch(client, [saved_job_id, unsaved_job_id])

    assert response.status_code == 422
    assert response.json()["detail"]["job_ids"] == [unsaved_job_id]


def test_batch_rejects_blank_name(test_context):
    job_id = create_saved_job(test_context)

    response = test_context["client"].post(
        "/api/application-batches",
        json={"name": "   ", "job_ids": [job_id]},
    )

    assert response.status_code == 422


def test_cannot_approve_batch_without_selected_jobs(test_context):
    job_id = create_saved_job(test_context)
    created = create_batch(test_context["client"], [job_id])
    batch_id = created.json()["id"]

    response = test_context["client"].post(
        f"/api/application-batches/{batch_id}/approve"
    )

    assert response.status_code == 422
    assert "Select at least one job" in response.json()["detail"]


def test_select_and_deselect_batch_item(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    created = create_batch(client, [job_id])
    batch = created.json()
    item_id = batch["items"][0]["id"]

    selected = client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": True},
    )
    assert selected.status_code == 200
    assert selected.json()["items"][0]["selected"] is True

    deselected = client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": False},
    )
    assert deselected.status_code == 200
    assert deselected.json()["items"][0]["selected"] is False


def test_approval_records_selection_without_submitting_applications(
    test_context,
):
    client = test_context["client"]
    db_factory = test_context["db_factory"]

    selected_job_id = create_saved_job(test_context)
    unselected_job_id = create_saved_job(test_context)
    created = create_batch(
        client,
        [selected_job_id, unselected_job_id],
    )
    batch = created.json()

    selected_item = next(
        item for item in batch["items"]
        if item["job_id"] == selected_job_id
    )
    select_response = client.patch(
        f"/api/application-batches/{batch['id']}/items/"
        f"{selected_item['id']}",
        json={"selected": True},
    )
    assert select_response.status_code == 200

    approved = client.post(
        f"/api/application-batches/{batch['id']}/approve"
    )

    assert approved.status_code == 200
    result = approved.json()
    assert result["status"] == "approved"
    assert result["approved_at"] is not None

    items_by_job = {item["job_id"]: item for item in result["items"]}
    assert items_by_job[selected_job_id]["approved_at"] is not None
    assert items_by_job[unselected_job_id]["approved_at"] is None

    with db_factory() as db:
        applications = db.scalars(
            select(Application).where(
                Application.job_id.in_(
                    [selected_job_id, unselected_job_id]
                ),
                Application.user_id == "user_test_1",
            )
        ).all()

        assert len(applications) == 2
        assert all(application.status == "saved" for application in applications)
        assert all(application.applied_at is None for application in applications)


def test_approved_batch_cannot_be_modified_or_approved_again(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    created = create_batch(client, [job_id])
    batch = created.json()
    item_id = batch["items"][0]["id"]

    selected = client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": True},
    )
    assert selected.status_code == 200

    approved = client.post(
        f"/api/application-batches/{batch['id']}/approve"
    )
    assert approved.status_code == 200

    update_after_approval = client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": False},
    )
    approve_again = client.post(
        f"/api/application-batches/{batch['id']}/approve"
    )

    assert update_after_approval.status_code == 409
    assert approve_again.status_code == 409


def test_user_cannot_read_or_modify_another_users_batch(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    job_id = create_saved_job(test_context)
    created = create_batch(client, [job_id])
    batch = created.json()
    item_id = batch["items"][0]["id"]

    current_user["id"] = "user_test_2"

    assert client.get(
        f"/api/application-batches/{batch['id']}"
    ).status_code == 404

    assert client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": True},
    ).status_code == 404

    assert client.post(
        f"/api/application-batches/{batch['id']}/approve"
    ).status_code == 404


def test_batch_list_only_returns_current_users_batches(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]

    first_job = create_saved_job(test_context)
    first_batch = create_batch(client, [first_job])
    assert first_batch.status_code == 201

    current_user["id"] = "user_test_2"
    second_job = create_saved_job(test_context)
    second_batch = create_batch(client, [second_job])
    assert second_batch.status_code == 201

    response = client.get("/api/application-batches")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == second_batch.json()["id"]


def test_batch_item_must_belong_to_requested_batch(test_context):
    client = test_context["client"]
    first_job = create_saved_job(test_context)
    second_job = create_saved_job(test_context)

    first_batch = create_batch(client, [first_job]).json()
    second_batch = create_batch(client, [second_job]).json()
    first_item_id = first_batch["items"][0]["id"]

    response = client.patch(
        f"/api/application-batches/{second_batch['id']}/items/"
        f"{first_item_id}",
        json={"selected": True},
    )

    assert response.status_code == 404

def test_batch_can_be_attached_to_users_campaign(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)

    campaign_response = client.post(
        "/api/application-campaigns",
        json={"name": "Backend developer search"},
    )
    assert campaign_response.status_code == 201
    campaign_id = campaign_response.json()["id"]

    response = create_batch(
        client,
        [job_id],
        campaign_id=campaign_id,
    )

    assert response.status_code == 201
    assert response.json()["campaign_id"] == campaign_id


def test_batch_without_campaign_has_null_campaign_id(test_context):
    job_id = create_saved_job(test_context)

    response = create_batch(test_context["client"], [job_id])

    assert response.status_code == 201
    assert response.json()["campaign_id"] is None


def test_batch_rejects_another_users_campaign(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]

    campaign_response = client.post(
        "/api/application-campaigns",
        json={"name": "Private campaign"},
    )
    assert campaign_response.status_code == 201
    campaign_id = campaign_response.json()["id"]

    current_user["id"] = "user_test_2"
    job_id = create_saved_job(test_context)

    response = create_batch(
        client,
        [job_id],
        campaign_id=campaign_id,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Application campaign not found"


def test_draft_batch_can_be_renamed(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    response = client.patch(
        f"/api/application-batches/{batch['id']}",
        json={"name": "Monday application session"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Monday application session"


def test_batch_rejects_empty_rename_request(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    response = client.patch(
        f"/api/application-batches/{batch['id']}",
        json={},
    )

    assert response.status_code == 422


def test_approved_batch_cannot_be_renamed(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    item_id = batch["items"][0]["id"]
    assert client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": True},
    ).status_code == 200

    assert client.post(
        f"/api/application-batches/{batch['id']}/approve"
    ).status_code == 200

    response = client.patch(
        f"/api/application-batches/{batch['id']}",
        json={"name": "Renamed"},
    )

    assert response.status_code == 409


def test_user_cannot_rename_another_users_batch(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    current_user["id"] = "user_test_2"

    response = client.patch(
        f"/api/application-batches/{batch['id']}",
        json={"name": "Unauthorized rename"},
    )

    assert response.status_code == 404


def test_draft_batch_can_add_saved_jobs(test_context):
    client = test_context["client"]
    first_job = create_saved_job(test_context)
    second_job = create_saved_job(test_context)
    batch = create_batch(client, [first_job]).json()

    response = client.post(
        f"/api/application-batches/{batch['id']}/items",
        json={"job_ids": [second_job]},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["job_id"] for item in items} == {first_job, second_job}
    assert all(item["selected"] is False for item in items)


def test_batch_cannot_add_a_job_that_is_already_in_the_session(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    response = client.post(
        f"/api/application-batches/{batch['id']}/items",
        json={"job_ids": [job_id]},
    )

    assert response.status_code == 409


def test_batch_cannot_add_jobs_not_saved_by_current_user(test_context):
    client = test_context["client"]
    job_id = create_job(test_context["db_factory"])
    batch = create_batch(client, [create_saved_job(test_context)]).json()

    response = client.post(
        f"/api/application-batches/{batch['id']}/items",
        json={"job_ids": [job_id]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["job_ids"] == [job_id]


def test_approved_batch_cannot_add_jobs(test_context):
    client = test_context["client"]
    first_job = create_saved_job(test_context)
    second_job = create_saved_job(test_context)
    batch = create_batch(client, [first_job]).json()

    item_id = batch["items"][0]["id"]
    client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": True},
    )
    client.post(f"/api/application-batches/{batch['id']}/approve")

    response = client.post(
        f"/api/application-batches/{batch['id']}/items",
        json={"job_ids": [second_job]},
    )

    assert response.status_code == 409


def test_draft_batch_can_remove_item_without_execution_history(test_context):
    client = test_context["client"]
    first_job = create_saved_job(test_context)
    second_job = create_saved_job(test_context)
    batch = create_batch(client, [first_job, second_job]).json()
    item_to_remove = next(
        item for item in batch["items"]
        if item["job_id"] == first_job
    )

    response = client.delete(
        f"/api/application-batches/{batch['id']}/items/"
        f"{item_to_remove['id']}"
    )

    assert response.status_code == 200
    assert [item["job_id"] for item in response.json()["items"]] == [
        second_job
    ]


def test_batch_item_with_execution_history_cannot_be_removed(test_context):
    client = test_context["client"]
    db_factory = test_context["db_factory"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()
    item_id = batch["items"][0]["id"]

    with db_factory() as db:
        application = db.scalar(
            select(Application).where(
                Application.user_id == "user_test_1",
                Application.job_id == job_id,
            )
        )
        assert application is not None

        execution = ApplicationExecution(
            user_id="user_test_1",
            application_id=application.id,
            batch_item_id=item_id,
            resume_filename_snapshot="resume.pdf",
            resume_sha256="a" * 64,
            cover_letter_snapshot=None,
            job_snapshot={"title": "Junior Python Developer"},
            application_payload={},
            target_url="https://example.com/apply",
            idempotency_key="test-batch-item-history",
        )
        db.add(execution)
        db.commit()

    response = client.delete(
        f"/api/application-batches/{batch['id']}/items/{item_id}"
    )

    assert response.status_code == 409
    assert "execution history" in response.json()["detail"]

    with db_factory() as db:
        item = db.get(ApplicationBatchItem, item_id)
        execution = db.scalar(
            select(ApplicationExecution).where(
                ApplicationExecution.batch_item_id == item_id
            )
        )
        assert item is not None
        assert execution is not None


def test_draft_batch_can_be_archived_only_after_approval(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    response = client.post(
        f"/api/application-batches/{batch['id']}/archive"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only approved sessions can be archived"
    )


def test_approved_batch_can_be_archived_without_losing_items(test_context):
    client = test_context["client"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()
    item_id = batch["items"][0]["id"]

    selected = client.patch(
        f"/api/application-batches/{batch['id']}/items/{item_id}",
        json={"selected": True},
    )
    assert selected.status_code == 200

    approved = client.post(
        f"/api/application-batches/{batch['id']}/approve"
    )
    assert approved.status_code == 200

    archived = client.post(
        f"/api/application-batches/{batch['id']}/archive"
    )

    assert archived.status_code == 200
    result = archived.json()
    assert result["status"] == "archived"
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == item_id
    assert result["items"][0]["approved_at"] is not None


def test_user_cannot_archive_another_users_batch(test_context):
    client = test_context["client"]
    current_user = test_context["current_user"]
    job_id = create_saved_job(test_context)
    batch = create_batch(client, [job_id]).json()

    current_user["id"] = "user_test_2"

    response = client.post(
        f"/api/application-batches/{batch['id']}/archive"
    )

    assert response.status_code == 404
