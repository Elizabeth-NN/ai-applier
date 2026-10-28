from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import jobs as jobs_api
from app.api import resumes as resumes_api
from app.core.auth import require_user
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app
from app.models.job import Job
from app.models.resume import Resume


@pytest.fixture
def match_context(tmp_path, monkeypatch) -> Generator[dict, None, None]:
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

    storage = (tmp_path / "private_uploads").resolve()
    storage.mkdir(parents=True)
    monkeypatch.setattr(resumes_api, "STORAGE_DIR", storage)
    monkeypatch.setattr(
        jobs_api,
        "extract_resume_text",
        lambda _path, _filename: (
            "Python FastAPI PostgreSQL Docker "
            "built APIs and web applications"
        ),
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

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "factory": factory,
                "user": current_user,
                "storage": storage,
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_resume(context, *, user_id="user_test_1", create_file=True):
    resume = Resume(
        user_id=user_id,
        original_filename="resume.pdf",
        storage_key=f"resume-{user_id}.pdf",
        content_type="application/pdf",
        size_bytes=100,
    )

    with context["factory"]() as db:
        db.add(resume)
        db.commit()
        db.refresh(resume)
        resume_id = resume.id
        storage_key = resume.storage_key

    if create_file:
        (context["storage"] / storage_key).write_bytes(b"test resume")

    return resume_id


def create_job(
    context,
    *,
    title,
    description,
    eligibility_status="unknown",
    listing_status="active",
):
    with context["factory"]() as db:
        job = Job(
            title=title,
            company="Example Company",
            description=description,
            employment_type="Full-time",
            remote_type="remote",
            eligibility_status=eligibility_status,
            listing_status=listing_status,
            eligible_countries=["Kenya"]
            if eligibility_status == "eligible"
            else None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def test_matches_return_explanations_and_preserve_eligibility(match_context):
    resume_id = create_resume(match_context)
    job_id = create_job(
        match_context,
        title="Python FastAPI Developer",
        description="Build APIs with Python, FastAPI, PostgreSQL and Docker.",
        eligibility_status="eligible",
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resume_id"] == resume_id
    assert body["resume_filename"] == "resume.pdf"
    assert body["total"] == 1

    item = body["items"][0]
    assert item["id"] == job_id
    assert 0 <= item["match_score"] <= 100
    assert "python" in item["matched_terms"]
    assert item["match_reasons"]
    assert item["eligibility_status"] == "eligible"
    assert item["eligible_countries"] == ["Kenya"]
    assert item["listing_status"] == "active"
    assert "storage_key" not in body
    assert "storage_key" not in item


def test_user_cannot_match_against_another_users_resume(match_context):
    resume_id = create_resume(match_context)
    match_context["user"]["id"] = "different_user"

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found"


def test_missing_resume_file_returns_404(match_context):
    resume_id = create_resume(match_context, create_file=False)

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume file not found"


def test_matches_are_ranked_before_pagination(match_context):
    resume_id = create_resume(match_context)

    matching_id = create_job(
        match_context,
        title="Python FastAPI Developer",
        description="Python FastAPI PostgreSQL Docker APIs web applications",
    )
    unrelated_id = create_job(
        match_context,
        title="Garden Maintenance Specialist",
        description="Prune hedges and maintain ornamental gardens outdoors.",
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}&skip=0&limit=1"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["skip"] == 0
    assert body["limit"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == matching_id
    assert body["items"][0]["id"] != unrelated_id


def test_match_pagination_returns_the_next_result(match_context):
    resume_id = create_resume(match_context)

    first_id = create_job(
        match_context,
        title="Python FastAPI Developer",
        description="Python FastAPI PostgreSQL Docker APIs web applications",
    )
    second_id = create_job(
        match_context,
        title="Garden Maintenance Specialist",
        description="Prune hedges and maintain ornamental gardens outdoors.",
    )

    first_page = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}&skip=0&limit=1"
    )
    second_page = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}&skip=1&limit=1"
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_page.json()["items"][0]["id"] == first_id
    assert second_page.json()["items"][0]["id"] == second_id


def test_invalid_resume_id_and_pagination_are_rejected(match_context):
    client = match_context["client"]

    assert client.get("/api/jobs/matches").status_code == 422
    assert client.get(
        "/api/jobs/matches?resume_id=0"
    ).status_code == 422
    assert client.get(
        "/api/jobs/matches?resume_id=1&skip=-1"
    ).status_code == 422
    assert client.get(
        "/api/jobs/matches?resume_id=1&limit=101"
    ).status_code == 422


def test_empty_job_database_returns_empty_matches(match_context):
    resume_id = create_resume(match_context)

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_resume_extraction_errors_are_returned_safely(match_context, monkeypatch):
    def reject_resume(_path, _filename):
        raise HTTPException(status_code=422, detail="Resume text unavailable")

    monkeypatch.setattr(jobs_api, "extract_resume_text", reject_resume)
    resume_id = create_resume(match_context)

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Resume text unavailable"
