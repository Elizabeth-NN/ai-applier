from collections.abc import Generator

import hashlib
from datetime import datetime, timezone
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
from app.models.application_execution import ApplicationExecution
from app.models.job import Job
from app.models.resume import Resume
import app.services.application_preparation as preparation


@pytest.fixture
def execution_context(tmp_path, monkeypatch) -> Generator[dict, None, None]:
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

    storage = tmp_path / "private_uploads"
    storage.mkdir()

    resume_bytes = b"test resume contents"
    (storage / "resume-test.pdf").write_bytes(resume_bytes)

    monkeypatch.setattr(
        preparation,
        "_resume_storage_dir",
        lambda: storage,
    )
    monkeypatch.setattr(
        preparation,
        "extract_resume_text",
        lambda path, filename: "A sufficiently long extracted resume text.",
    )

    current_user = {"id": "user_test_1"}

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_user] = lambda: current_user["id"]

    with factory() as db:
        job = Job(
            title="Junior Python Developer",
            company="Example Company",
            location="Remote",
            description="Build and maintain Python applications.",
            source_url="https://example.com/jobs/123",
            employment_type="Full-time",
            eligibility_status="unknown",
        )
        db.add(job)
        db.flush()

        application = Application(
            job_id=job.id,
            user_id="user_test_1",
            status="saved",
        )
        db.add(application)

        resume = Resume(
            user_id="user_test_1",
            original_filename="resume-test.pdf",
            storage_key="resume-test.pdf",
            content_type="application/pdf",
            size_bytes=len(resume_bytes),
        )
        db.add(resume)
        db.commit()
        db.refresh(application)
        db.refresh(resume)

        application_id = application.id
        resume_id = resume.id

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "db_factory": factory,
                "current_user": current_user,
                "application_id": application_id,
                "resume_id": resume_id,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def prepare_execution(context):
    return context["client"].post(
        "/api/application-executions/prepare",
        headers={"Idempotency-Key": "api-test-preparation-001"},
        json={
            "application_id": context["application_id"],
            "resume_id": context["resume_id"],
        },
    )


def test_prepare_endpoint_creates_execution(execution_context):
    response = prepare_execution(execution_context)

    assert response.status_code == 201

    body = response.json()
    assert body["status"] == "prepared"
    assert body["application_id"] == execution_context["application_id"]
    assert body["resume_id"] == execution_context["resume_id"]
    assert body["reviewed_at"] is None
    assert body["approved_at"] is None
    assert body["submitted_at"] is None


def test_prepare_endpoint_is_idempotent(execution_context):
    first = prepare_execution(execution_context)
    second = prepare_execution(execution_context)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    with execution_context["db_factory"]() as db:
        executions = db.scalars(select(ApplicationExecution)).all()
        assert len(executions) == 1


def test_review_and_approve_http_workflow(execution_context):
    client = execution_context["client"]
    prepared = prepare_execution(execution_context)
    assert prepared.status_code == 201

    execution_id = prepared.json()["id"]

    # Approval must not be possible before review.
    premature_approval = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )
    assert premature_approval.status_code == 409

    reviewed = client.post(
        f"/api/application-executions/{execution_id}/review"
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "prepared"
    assert reviewed.json()["reviewed_at"] is not None
    assert reviewed.json()["approved_at"] is None

    approved = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )
    assert approved.status_code == 200

    body = approved.json()
    assert body["status"] == "approved"
    assert body["reviewed_at"] is not None
    assert body["approved_at"] is not None
    assert body["submitted_at"] is None


def test_another_user_cannot_review_or_approve_execution(execution_context):
    client = execution_context["client"]
    prepared = prepare_execution(execution_context)
    assert prepared.status_code == 201

    execution_id = prepared.json()["id"]

    execution_context["current_user"]["id"] = "user_test_2"

    reviewed = client.post(
        f"/api/application-executions/{execution_id}/review"
    )
    approved = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )

    assert reviewed.status_code == 404
    assert approved.status_code == 404


def test_approved_execution_cannot_be_approved_again(execution_context):
    client = execution_context["client"]
    prepared = prepare_execution(execution_context)
    execution_id = prepared.json()["id"]

    reviewed = client.post(
        f"/api/application-executions/{execution_id}/review"
    )
    assert reviewed.status_code == 200

    first_approval = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )
    second_approval = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )

    assert first_approval.status_code == 200
    assert second_approval.status_code == 409


def test_execution_approval_does_not_submit_application(execution_context):
    client = execution_context["client"]
    prepared = prepare_execution(execution_context)
    execution_id = prepared.json()["id"]

    client.post(
        f"/api/application-executions/{execution_id}/review"
    )
    approved = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["submitted_at"] is None

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        assert application.status == "saved"
        assert application.applied_at is None


def approve_execution_for_test(context):
    """Prepare, review, and approve an execution for lifecycle tests."""
    client = context["client"]

    prepared = prepare_execution(context)
    assert prepared.status_code == 201

    execution_id = prepared.json()["id"]

    reviewed = client.post(
        f"/api/application-executions/{execution_id}/review"
    )
    assert reviewed.status_code == 200

    approved = client.post(
        f"/api/application-executions/{execution_id}/approve"
    )
    assert approved.status_code == 200

    return execution_id


def test_start_submission_requires_approval(execution_context):
    client = execution_context["client"]
    prepared = prepare_execution(execution_context)
    execution_id = prepared.json()["id"]

    response = client.post(
        f"/api/application-executions/{execution_id}/start"
    )

    assert response.status_code == 409


def test_start_submission_records_one_attempt(execution_context):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/start"
    )

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "submitting"
    assert body["submission_attempt_id"] is not None
    assert len(body["submission_attempt_id"]) == 36
    assert body["submission_started_at"] is not None
    assert body["submitted_at"] is None
    assert body["submission_reference"] is None
    assert body["submission_result"] is None


def test_start_submission_cannot_be_started_twice(execution_context):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    first = client.post(
        f"/api/application-executions/{execution_id}/start"
    )
    second = client.post(
        f"/api/application-executions/{execution_id}/start"
    )

    assert first.status_code == 200
    assert second.status_code == 409

    with execution_context["db_factory"]() as db:
        execution = db.get(ApplicationExecution, execution_id)
        assert execution.status == "submitting"
        assert execution.submission_attempt_id == (
            first.json()["submission_attempt_id"]
        )


def test_another_user_cannot_start_submission(execution_context):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    execution_context["current_user"]["id"] = "user_test_2"

    response = client.post(
        f"/api/application-executions/{execution_id}/start"
    )

    assert response.status_code == 404


def test_starting_submission_does_not_mark_application_as_applied(
    execution_context,
):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/start"
    )

    assert response.status_code == 200

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        assert application.status == "saved"
        assert application.applied_at is None


def start_execution_for_test(context):
    """Prepare, review, approve, and start an execution."""
    client = context["client"]
    execution_id = approve_execution_for_test(context)

    response = client.post(
        f"/api/application-executions/{execution_id}/start"
    )
    assert response.status_code == 200

    return execution_id


def test_complete_submission_records_confirmed_success(execution_context):
    client = execution_context["client"]
    execution_id = start_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/complete",
        json={"submission_reference": "APP-2026-001"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None
    assert body["submission_reference"] == "APP-2026-001"
    assert body["submission_attempt_id"] is not None

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        assert application.status == "applied"
        assert application.applied_at is not None


def test_complete_submission_allows_missing_reference(execution_context):
    client = execution_context["client"]
    execution_id = start_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/complete",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["submission_reference"] is None


def test_complete_submission_cannot_be_completed_twice(execution_context):
    client = execution_context["client"]
    execution_id = start_execution_for_test(execution_context)
    url = f"/api/application-executions/{execution_id}/complete"

    first = client.post(url, json={})
    second = client.post(url, json={})

    assert first.status_code == 200
    assert second.status_code == 409

    with execution_context["db_factory"]() as db:
        execution = db.get(ApplicationExecution, execution_id)
        assert execution.status == "submitted"


def test_another_user_cannot_complete_submission(execution_context):
    client = execution_context["client"]
    execution_id = start_execution_for_test(execution_context)

    execution_context["current_user"]["id"] = "user_test_2"

    response = client.post(
        f"/api/application-executions/{execution_id}/complete",
        json={},
    )

    assert response.status_code == 404


def test_cannot_complete_submission_before_start(execution_context):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/complete",
        json={},
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "existing_status",
    ["applied", "interview", "offer", "rejected"],
)
def test_completion_preserves_existing_application_status(
    execution_context,
    existing_status,
):
    client = execution_context["client"]
    execution_id = start_execution_for_test(execution_context)

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        application.status = existing_status
        db.commit()

    response = client.post(
        f"/api/application-executions/{execution_id}/complete",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        assert application.status == existing_status


def test_fail_submission_records_failure(execution_context):
    client = execution_context["client"]
    execution_id = start_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/fail",
        json={"failure_reason": "Employer website returned an error."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failure_reason"] == "Employer website returned an error."
    assert body["submission_attempt_id"] is not None
    assert body["submitted_at"] is None

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        assert application.status == "saved"
        assert application.applied_at is None


def test_fail_submission_rejects_blank_reason(execution_context):
    execution_id = start_execution_for_test(execution_context)

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/fail",
        json={"failure_reason": "   "},
    )

    assert response.status_code == 422


def test_fail_submission_cannot_be_completed_twice(execution_context):
    execution_id = start_execution_for_test(execution_context)
    url = f"/api/application-executions/{execution_id}/fail"

    first = execution_context["client"].post(
        url,
        json={"failure_reason": "Submission failed."},
    )
    second = execution_context["client"].post(
        url,
        json={"failure_reason": "Another failure."},
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_another_user_cannot_fail_submission(execution_context):
    execution_id = start_execution_for_test(execution_context)
    execution_context["current_user"]["id"] = "user_test_2"

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/fail",
        json={"failure_reason": "Submission failed."},
    )

    assert response.status_code == 404


def test_cannot_fail_submission_before_start(execution_context):
    execution_id = approve_execution_for_test(execution_context)

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/fail",
        json={"failure_reason": "Submission failed."},
    )

    assert response.status_code == 409


def test_uncertain_submission_requires_attention(execution_context):
    execution_id = start_execution_for_test(execution_context)

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={
            "reason": "The confirmation page did not load after submission."
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_attention"
    assert body["failure_reason"] == (
        "The confirmation page did not load after submission."
    )
    assert body["submission_attempt_id"] is not None
    assert body["submitted_at"] is None

    with execution_context["db_factory"]() as db:
        application = db.get(
            Application,
            execution_context["application_id"],
        )
        assert application.status == "saved"
        assert application.applied_at is None


def test_attention_reason_cannot_be_blank(execution_context):
    execution_id = start_execution_for_test(execution_context)

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={"reason": "   "},
    )

    assert response.status_code == 422


def test_attention_cannot_be_recorded_twice(execution_context):
    execution_id = start_execution_for_test(execution_context)
    url = (
        f"/api/application-executions/{execution_id}/needs-attention"
    )

    first = execution_context["client"].post(
        url,
        json={"reason": "Confirmation is uncertain."},
    )
    second = execution_context["client"].post(
        url,
        json={"reason": "Still uncertain."},
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_another_user_cannot_flag_submission_for_attention(
    execution_context,
):
    execution_id = start_execution_for_test(execution_context)
    execution_context["current_user"]["id"] = "user_test_2"

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={"reason": "Confirmation is uncertain."},
    )

    assert response.status_code == 404


def test_attention_cannot_be_recorded_before_submission_starts(
    execution_context,
):
    execution_id = approve_execution_for_test(execution_context)

    response = execution_context["client"].post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={"reason": "Confirmation is uncertain."},
    )

    assert response.status_code == 409


def test_attention_execution_cannot_be_restarted(execution_context):
    execution_id = start_execution_for_test(execution_context)
    client = execution_context["client"]

    attention = client.post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={"reason": "Confirmation is uncertain."},
    )
    restart = client.post(
        f"/api/application-executions/{execution_id}/start"
    )

    assert attention.status_code == 200
    assert restart.status_code == 409


def test_attention_execution_cannot_be_completed(execution_context):
    execution_id = start_execution_for_test(execution_context)
    client = execution_context["client"]

    client.post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={"reason": "Confirmation is uncertain."},
    )

    response = client.post(
        f"/api/application-executions/{execution_id}/complete",
        json={},
    )

    assert response.status_code == 409


def test_attention_execution_cannot_be_marked_failed(execution_context):
    execution_id = start_execution_for_test(execution_context)
    client = execution_context["client"]

    client.post(
        f"/api/application-executions/{execution_id}/needs-attention",
        json={"reason": "Confirmation is uncertain."},
    )

    response = client.post(
        f"/api/application-executions/{execution_id}/fail",
        json={"failure_reason": "Submission failed."},
    )

    assert response.status_code == 409


def test_list_executions_returns_only_authenticated_users_records(
    execution_context,
):
    client = execution_context["client"]

    prepared = prepare_execution(execution_context)
    assert prepared.status_code == 201

    execution_context["current_user"]["id"] = "user_test_2"

    response = client.get("/api/application-executions")

    assert response.status_code == 200
    assert response.json() == []


def test_list_executions_supports_newest_first_pagination(
    execution_context,
):
    client = execution_context["client"]

    execution_ids = []

    for index in range(3):
        response = client.post(
            "/api/application-executions/prepare",
            headers={"Idempotency-Key": f"pagination-test-{index}"},
            json={
                "application_id": execution_context["application_id"],
                "resume_id": execution_context["resume_id"],
            },
        )

        assert response.status_code == 201
        execution_ids.append(response.json()["id"])

    first_page = client.get(
        "/api/application-executions?skip=0&limit=2"
    )
    second_page = client.get(
        "/api/application-executions?skip=2&limit=2"
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_page_ids = [item["id"] for item in first_page.json()]
    second_page_ids = [item["id"] for item in second_page.json()]

    assert first_page_ids == list(reversed(execution_ids[-2:]))
    assert second_page_ids == [execution_ids[0]]
    assert set(first_page_ids).isdisjoint(second_page_ids)


def test_list_executions_rejects_invalid_pagination(execution_context):
    client = execution_context["client"]

    invalid_limit = client.get(
        "/api/application-executions?limit=101"
    )
    negative_skip = client.get(
        "/api/application-executions?skip=-1"
    )

    assert invalid_limit.status_code == 422
    assert negative_skip.status_code == 422


def test_extension_handoff_requires_approved_execution(execution_context):
    client = execution_context["client"]
    prepared = prepare_execution(execution_context)
    execution_id = prepared.json()["id"]

    response = client.post(
        f"/api/application-executions/{execution_id}/extension-handoff"
    )

    assert response.status_code == 409


def test_another_user_cannot_issue_extension_handoff(execution_context):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    execution_context["current_user"]["id"] = "user_test_2"

    response = client.post(
        f"/api/application-executions/{execution_id}/extension-handoff"
    )

    assert response.status_code == 404


def test_extension_handoff_stores_only_token_hash(execution_context):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    response = client.post(
        f"/api/application-executions/{execution_id}/extension-handoff"
    )

    assert response.status_code == 200

    body = response.json()
    token = body["token"]
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.fromisoformat(body["expires_at"])

    assert len(token) > 30
    assert expires_at > datetime.now(timezone.utc)

    with execution_context["db_factory"]() as db:
        execution = db.get(ApplicationExecution, execution_id)

        assert execution.extension_handoff_token_hash == expected_hash
        assert execution.extension_handoff_token_hash != token
        assert execution.extension_handoff_expires_at is not None
        assert execution.extension_handoff_redeemed_at is None

        # Issuing a handoff must not start or submit an application.
        assert execution.status == "approved"
        assert execution.submission_attempt_id is None
        assert execution.submission_started_at is None
        assert execution.submitted_at is None


def test_reissuing_extension_handoff_invalidates_previous_token(
    execution_context,
):
    client = execution_context["client"]
    execution_id = approve_execution_for_test(execution_context)

    url = (
        f"/api/application-executions/"
        f"{execution_id}/extension-handoff"
    )

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == 200
    assert second.status_code == 200

    first_token = first.json()["token"]
    second_token = second.json()["token"]

    assert first_token != second_token

    first_hash = hashlib.sha256(first_token.encode("utf-8")).hexdigest()
    second_hash = hashlib.sha256(second_token.encode("utf-8")).hexdigest()

    with execution_context["db_factory"]() as db:
        execution = db.get(ApplicationExecution, execution_id)

        assert execution.extension_handoff_token_hash == second_hash
        assert execution.extension_handoff_token_hash != first_hash
        assert execution.extension_handoff_redeemed_at is None
        assert execution.status == "approved"
