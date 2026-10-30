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
