from collections.abc import Generator

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.application import Application
from app.models.application_execution import ApplicationExecution
from app.models.job import Job
from app.models.resume import Resume
import app.services.application_preparation as preparation


@pytest.fixture
def preparation_context(tmp_path, monkeypatch) -> Generator[dict, None, None]:
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

    monkeypatch.setattr(preparation, "_resume_storage_dir", lambda: storage)
    monkeypatch.setattr(
        preparation,
        "extract_resume_text",
        lambda path, filename: "A sufficiently long extracted resume text.",
    )

    resume_bytes = b"test resume contents"
    (storage / "resume-test.pdf").write_bytes(resume_bytes)

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
        job_id = job.id

    try:
        yield {
            "factory": factory,
            "storage": storage,
            "application_id": application_id,
            "resume_id": resume_id,
            "job_id": job_id,
            "resume_bytes": resume_bytes,
        }
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def prepare(context, **overrides):
    values = {
        "user_id": "user_test_1",
        "application_id": context["application_id"],
        "resume_id": context["resume_id"],
        "idempotency_key": "preparation-test-001",
    }
    values.update(overrides)

    with context["factory"]() as db:
        return preparation.prepare_application_execution(db, **values)


def test_prepare_creates_reviewable_execution(preparation_context):
    context = preparation_context

    execution = prepare(context)

    assert execution.status == "prepared"
    assert execution.application_id == context["application_id"]
    assert execution.resume_id == context["resume_id"]
    assert execution.resume_filename_snapshot == "resume-test.pdf"
    assert execution.resume_sha256
    assert len(execution.resume_sha256) == 64
    assert execution.target_url == "https://example.com/jobs/123"
    assert execution.ats_platform == "unsupported"
    assert execution.job_snapshot["title"] == "Junior Python Developer"
    assert execution.application_payload["resume"]["filename"] == "resume-test.pdf"

    # Preparation must not approve or submit the application.
    assert execution.reviewed_at is None
    assert execution.approved_at is None
    assert execution.submitted_at is None


def test_same_idempotency_key_returns_existing_execution(preparation_context):
    first = prepare(preparation_context)
    second = prepare(preparation_context)

    assert first.id == second.id

    with preparation_context["factory"]() as db:
        executions = db.query(ApplicationExecution).all()
        assert len(executions) == 1


def test_reusing_idempotency_key_for_different_request_returns_conflict(
    preparation_context,
):
    prepare(preparation_context)

    with pytest.raises(HTTPException) as exc:
        prepare(
            preparation_context,
            resume_id=999,
        )

    assert exc.value.status_code == 409


def test_cannot_prepare_another_users_application(preparation_context):
    with pytest.raises(HTTPException) as exc:
        prepare(preparation_context, user_id="different_user")

    assert exc.value.status_code == 404


def test_rejects_job_without_application_url(preparation_context):
    with preparation_context["factory"]() as db:
        job = db.get(Job, preparation_context["job_id"])
        job.source_url = None
        db.commit()

    with pytest.raises(HTTPException) as exc:
        prepare(preparation_context)

    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "ftp://example.com/job",
        "/jobs/123",
        "https://",
        "https://user:password@example.com/job",
        "not a URL",
    ],
)
def test_rejects_invalid_application_urls(preparation_context, url):
    with preparation_context["factory"]() as db:
        job = db.get(Job, preparation_context["job_id"])
        job.source_url = url
        db.commit()

    with pytest.raises(HTTPException) as exc:
        prepare(preparation_context)

    assert exc.value.status_code == 422


def test_rejects_missing_resume_file(preparation_context):
    (preparation_context["storage"] / "resume-test.pdf").unlink()

    with pytest.raises(HTTPException) as exc:
        prepare(preparation_context)

    assert exc.value.status_code == 404


def test_rejects_resume_with_mismatched_recorded_size(preparation_context):
    with preparation_context["factory"]() as db:
        resume = db.get(Resume, preparation_context["resume_id"])
        resume.size_bytes += 1
        db.commit()

    with pytest.raises(HTTPException) as exc:
        prepare(preparation_context)

    assert exc.value.status_code == 422
