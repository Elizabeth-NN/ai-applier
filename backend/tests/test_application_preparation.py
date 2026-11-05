from collections.abc import Generator

import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.application import Application
from app.models.application_batch import ApplicationBatch, ApplicationBatchItem
from app.models.application_campaign import ApplicationCampaign
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


def test_rejects_job_without_any_usable_url(preparation_context):
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
        job.application_url = url
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


def test_cannot_approve_execution_before_review(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        with pytest.raises(HTTPException) as exc:
            preparation.approve_application_execution(
                db,
                user_id="user_test_1",
                execution_id=execution.id,
            )

    assert exc.value.status_code == 409


def test_review_records_reviewed_at(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        reviewed = preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    assert reviewed.status == "prepared"
    assert reviewed.reviewed_at is not None
    assert reviewed.approved_at is None
    assert reviewed.submitted_at is None


def test_review_is_idempotent(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        first = preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )
        first_reviewed_at = first.reviewed_at

    with preparation_context["factory"]() as db:
        second = preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    assert second.reviewed_at == first_reviewed_at


def test_another_user_cannot_review_execution(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        with pytest.raises(HTTPException) as exc:
            preparation.review_application_execution(
                db,
                user_id="different_user",
                execution_id=execution.id,
            )

    assert exc.value.status_code == 404


def test_another_user_cannot_approve_execution(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    with preparation_context["factory"]() as db:
        with pytest.raises(HTTPException) as exc:
            preparation.approve_application_execution(
                db,
                user_id="different_user",
                execution_id=execution.id,
            )

    assert exc.value.status_code == 404


def test_approval_requires_review_and_records_approval(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    with preparation_context["factory"]() as db:
        approved = preparation.approve_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    assert approved.status == "approved"
    assert approved.reviewed_at is not None
    assert approved.approved_at is not None
    assert approved.submitted_at is None


def test_cannot_approve_execution_twice(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    with preparation_context["factory"]() as db:
        preparation.approve_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    with preparation_context["factory"]() as db:
        with pytest.raises(HTTPException) as exc:
            preparation.approve_application_execution(
                db,
                user_id="user_test_1",
                execution_id=execution.id,
            )

    assert exc.value.status_code == 409


def test_cannot_review_execution_after_approval(preparation_context):
    execution = prepare(preparation_context)

    with preparation_context["factory"]() as db:
        preparation.review_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )
        preparation.approve_application_execution(
            db,
            user_id="user_test_1",
            execution_id=execution.id,
        )

    with preparation_context["factory"]() as db:
        with pytest.raises(HTTPException) as exc:
            preparation.review_application_execution(
                db,
                user_id="user_test_1",
                execution_id=execution.id,
            )

    assert exc.value.status_code == 409

def test_uses_application_url_for_target_and_ats(preparation_context):
    with preparation_context["factory"]() as db:
        job = db.get(Job, preparation_context["job_id"])
        job.application_url = (
            "https://boards.greenhouse.io/example/jobs/123"
        )
        db.commit()

    execution = prepare(preparation_context)

    assert execution.target_url == (
        "https://boards.greenhouse.io/example/jobs/123"
    )
    assert execution.ats_platform == "greenhouse"
    assert execution.job_snapshot["source_url"] == (
        "https://example.com/jobs/123"
    )
    assert execution.job_snapshot["application_url"] == (
        "https://boards.greenhouse.io/example/jobs/123"
    )

def test_job_without_application_url_remains_reviewable(
    preparation_context,
):
    execution = prepare(preparation_context)

    assert execution.status == "prepared"
    assert execution.target_url == "https://example.com/jobs/123"
    assert execution.ats_platform == "unsupported"
    assert execution.job_snapshot["source_url"] == (
        "https://example.com/jobs/123"
    )
    assert execution.job_snapshot["application_url"] is None


def create_campaign(context, *, user_id="user_test_1", name="Test campaign"):
    with context["factory"]() as db:
        campaign = ApplicationCampaign(
            user_id=user_id,
            name=name,
            target_applications=500,
            starts_on=date.today(),
            deadline_on=date.today() + timedelta(days=56),
            status="active",
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign.id


def create_approved_batch_item(context, campaign_id):
    now = datetime.now(timezone.utc)

    with context["factory"]() as db:
        batch = ApplicationBatch(
            user_id="user_test_1",
            campaign_id=campaign_id,
            name="Approved test batch",
            status="approved",
            approved_at=now,
        )
        db.add(batch)
        db.flush()

        item = ApplicationBatchItem(
            batch_id=batch.id,
            job_id=context["job_id"],
            selected=True,
            approved_at=now,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id


def test_prepare_attaches_explicit_campaign(preparation_context):
    campaign_id = create_campaign(preparation_context)

    execution = prepare(
        preparation_context,
        campaign_id=campaign_id,
    )

    assert execution.campaign_id == campaign_id


def test_prepare_inherits_campaign_from_approved_batch(
    preparation_context,
):
    campaign_id = create_campaign(preparation_context)
    batch_item_id = create_approved_batch_item(
        preparation_context,
        campaign_id,
    )

    execution = prepare(
        preparation_context,
        batch_item_id=batch_item_id,
    )

    assert execution.batch_item_id == batch_item_id
    assert execution.campaign_id == campaign_id


def test_prepare_rejects_campaign_that_does_not_match_batch(
    preparation_context,
):
    batch_campaign_id = create_campaign(
        preparation_context,
        name="Batch campaign",
    )
    other_campaign_id = create_campaign(
        preparation_context,
        name="Other campaign",
    )
    batch_item_id = create_approved_batch_item(
        preparation_context,
        batch_campaign_id,
    )

    with pytest.raises(HTTPException) as exc:
        prepare(
            preparation_context,
            batch_item_id=batch_item_id,
            campaign_id=other_campaign_id,
        )

    assert exc.value.status_code == 422
    assert "match" in exc.value.detail


def test_prepare_rejects_campaign_owned_by_another_user(
    preparation_context,
):
    foreign_campaign_id = create_campaign(
        preparation_context,
        user_id="another_user",
        name="Foreign campaign",
    )

    with pytest.raises(HTTPException) as exc:
        prepare(
            preparation_context,
            campaign_id=foreign_campaign_id,
        )

    assert exc.value.status_code == 404


def test_idempotency_key_rejects_different_campaign(
    preparation_context,
):
    first_campaign_id = create_campaign(
        preparation_context,
        name="First campaign",
    )
    second_campaign_id = create_campaign(
        preparation_context,
        name="Second campaign",
    )

    prepare(
        preparation_context,
        campaign_id=first_campaign_id,
    )

    with pytest.raises(HTTPException) as exc:
        prepare(
            preparation_context,
            campaign_id=second_campaign_id,
        )

    assert exc.value.status_code == 409
