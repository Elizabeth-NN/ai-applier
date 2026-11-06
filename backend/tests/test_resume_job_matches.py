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
from app.models.candidate_profile import CandidateProfile
from app.models.job import Job
from app.models.resume import Resume


@pytest.fixture
def match_context(tmp_path, monkeypatch) -> Generator[dict, None, None]:
    # The application cache is process-wide; isolate each test's cache state.
    with jobs_api._match_result_lock:
        jobs_api._match_result_cache.clear()

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



def create_candidate_profile(
    context,
    *,
    user_id="user_test_1",
    **values,
):
    profile = CandidateProfile(user_id=user_id, **values)

    with context["factory"]() as db:
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile.id


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



def test_matches_separate_required_and_preferred_evidence(match_context):
    resume_id = create_resume(match_context)
    create_job(
        match_context,
        title="Python FastAPI Developer",
        description=(
            "Required qualifications:\n"
            "- Python\n"
            "- FastAPI\n"
            "- Kubernetes\n\n"
            "Preferred qualifications:\n"
            "- Docker\n"
            "- AWS\n"
            "- Terraform"
        ),
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]

    assert item["required_terms_found"] == ["fastapi", "python"]
    assert item["required_terms_not_found"] == ["kubernetes"]
    assert item["preferred_terms_found"] == ["docker"]
    assert item["preferred_terms_not_found"] == ["aws", "terraform"]


def test_profile_evidence_adds_terms_to_combined_match(match_context):
    resume_id = create_resume(match_context)
    create_candidate_profile(match_context, skills=["Kubernetes"])
    create_job(
        match_context,
        title="Kubernetes Backend Engineer",
        description=(
            "Required qualifications:\\n"
            "- Kubernetes\\n"
            "- Python\\n"
            "- FastAPI"
        ),
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]

    assert item["profile_match_score"] > item["match_score"]
    assert "kubernetes" in item["required_terms_not_found"]
    assert "kubernetes" in item["profile_only_matched_terms"]
    assert "kubernetes" in item["required_terms_found_in_profile"]
    assert "kubernetes" in item["required_terms_found_in_resume_or_profile"]
    assert "kubernetes" not in item["required_terms_not_found_in_resume_or_profile"]
    assert "kubernetes" not in item["terms_not_found_in_resume_or_profile"]
    assert item["profile_term_evidence"]["kubernetes"] == ["skills"]


def test_matching_does_not_use_another_users_profile(match_context):
    resume_id = create_resume(match_context)
    create_candidate_profile(
        match_context,
        user_id="different_user",
        skills=["Kubernetes"],
    )
    create_job(
        match_context,
        title="Kubernetes Backend Engineer",
        description=(
            "Required qualifications:\\n"
            "- Kubernetes\\n"
            "- Python"
        ),
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]

    assert item["profile_match_score"] is None
    assert item["profile_only_matched_terms"] == []
    assert item["required_terms_not_found"] == ["kubernetes"]
    assert item["required_terms_found_in_resume_or_profile"] == []
    assert item["required_terms_not_found_in_resume_or_profile"] == []
    assert item["profile_term_evidence"] == {}


def test_duplicate_resume_and_profile_terms_do_not_inflate_score(match_context):
    resume_id = create_resume(match_context)
    create_candidate_profile(match_context, skills=["Python"])
    create_job(
        match_context,
        title="Python Backend Developer",
        description="Build APIs with Python and FastAPI for web applications.",
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]

    assert item["profile_match_score"] == item["match_score"]
    assert "python" in item["profile_matched_terms"]
    assert "python" not in item["profile_only_matched_terms"]


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


def test_matches_include_resume_section_evidence(match_context, monkeypatch):
    resume_id = create_resume(match_context)

    resume_text = """PROFESSIONAL SUMMARY
Python backend developer.

TECHNICAL SKILLS
Python, FastAPI

PROFESSIONAL EXPERIENCE
Built APIs using Python.

PROJECTS
Created a FastAPI service with Docker.

EDUCATION
Bachelor of Science in Software Engineering.
"""

    monkeypatch.setattr(
        jobs_api,
        "extract_resume_text",
        lambda _path, _filename: resume_text,
    )

    create_job(
        match_context,
        title="Python Backend Developer",
        description=(
            "Required qualifications:\n"
            "- Python\n"
            "- FastAPI\n"
            "- Kubernetes\n\n"
            "Preferred qualifications:\n"
            "- Docker\n"
            "- AWS"
        ),
    )

    response = match_context["client"].get(
        f"/api/jobs/matches?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    evidence = item["term_evidence"]

    assert evidence["python"] == ["skills", "experience", "summary"]
    assert evidence["fastapi"] == ["skills", "projects"]
    assert evidence["kubernetes"] == []
    assert evidence["docker"] == ["projects"]
    assert evidence["aws"] == []


def test_screen_prioritizes_eligible_active_junior_remote_role(match_context):
    resume_id = create_resume(match_context)
    create_candidate_profile(
        match_context,
        target_roles=["Python"],
        work_preferences={
            "remote": True,
            "employment_type": ["full-time"],
        },
    )
    job_id = create_job(
        match_context,
        title="Junior Python Developer",
        description=(
            "Entry-level Python developer building APIs with "
            "FastAPI, PostgreSQL and Docker."
        ),
        eligibility_status="eligible",
        listing_status="active",
    )

    response = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1

    item = body["items"][0]
    assert item["id"] == job_id
    assert item["recommendation"] == "prioritize"
    assert item["role_alignment"] == "aligned"
    assert item["experience_fit"] == "aligned"
    assert item["remote_fit"] == "aligned"
    assert item["employment_fit"] == "aligned"
    assert item["kenya_eligibility"] == "eligible"
    assert item["listing_status"] == "active"

    # The screening response retains the existing match evidence.
    assert isinstance(item["match_score"], int)
    assert item["matched_terms"]
    assert "storage_key" not in item


def test_screen_reviews_unknown_kenya_eligibility(match_context):
    resume_id = create_resume(match_context)
    create_candidate_profile(
        match_context,
        target_roles=["Python"],
        work_preferences={"remote": True},
    )
    create_job(
        match_context,
        title="Junior Python Developer",
        description="Build Python APIs with FastAPI and PostgreSQL.",
        eligibility_status="unknown",
        listing_status="active",
    )

    response = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["recommendation"] == "review"
    assert item["kenya_eligibility"] == "unknown"
    assert any("Kenya" in reason for reason in item["reasons"])


@pytest.mark.parametrize(
    ("eligibility_status", "listing_status"),
    [
        ("ineligible", "active"),
        ("eligible", "closed"),
    ],
)
def test_screen_excludes_confirmed_disqualifiers(
    match_context,
    eligibility_status,
    listing_status,
):
    resume_id = create_resume(match_context)
    create_candidate_profile(
        match_context,
        target_roles=["Python"],
        work_preferences={"remote": True},
    )
    create_job(
        match_context,
        title="Junior Python Developer",
        description="Build Python APIs with FastAPI and PostgreSQL.",
        eligibility_status=eligibility_status,
        listing_status=listing_status,
    )

    response = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["recommendation"] == "exclude"

    if eligibility_status == "ineligible":
        assert item["kenya_eligibility"] == "ineligible"
    if listing_status == "closed":
        assert item["listing_status"] == "closed"


def test_screen_uses_only_authenticated_users_profile(match_context):
    resume_id = create_resume(match_context)
    create_candidate_profile(
        match_context,
        user_id="different_user",
        target_roles=["Python"],
        work_preferences={
            "remote": True,
            "employment_type": ["full-time"],
        },
    )
    create_job(
        match_context,
        title="Junior Python Developer",
        description="Build Python APIs with FastAPI and PostgreSQL.",
        eligibility_status="eligible",
        listing_status="active",
    )

    response = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}"
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]

    # The other user's preferences must not leak into this screening result.
    assert item["remote_fit"] == "not_specified"
    assert item["employment_fit"] == "not_specified"


def test_screen_rejects_another_users_resume(match_context):
    resume_id = create_resume(match_context)
    match_context["user"]["id"] = "different_user"

    response = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found"


def test_screen_preserves_pagination(match_context):
    resume_id = create_resume(match_context)
    first_id = create_job(
        match_context,
        title="Junior Python Developer",
        description="Build Python APIs with FastAPI and PostgreSQL.",
        eligibility_status="eligible",
    )
    second_id = create_job(
        match_context,
        title="Garden Maintenance Specialist",
        description="Prune hedges and maintain ornamental gardens outdoors.",
        eligibility_status="unknown",
    )

    first_page = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}&skip=0&limit=1"
    )
    second_page = match_context["client"].get(
        f"/api/jobs/screen?resume_id={resume_id}&skip=1&limit=1"
    )

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text

    assert first_page.json()["total"] == 2
    assert first_page.json()["skip"] == 0
    assert first_page.json()["limit"] == 1
    assert len(first_page.json()["items"]) == 1
    assert len(second_page.json()["items"]) == 1

    assert first_page.json()["items"][0]["id"] == first_id
    assert second_page.json()["items"][0]["id"] == second_id


def test_matching_reuses_cached_scores_but_returns_fresh_job_metadata(
    match_context,
    monkeypatch,
):
    resume_id = create_resume(match_context)
    job_id = create_job(
        match_context,
        title="Python FastAPI Developer",
        description="Build APIs with Python and FastAPI.",
        eligibility_status="eligible",
    )

    extraction_calls = 0
    scoring_calls = 0

    original_extract = jobs_api.extract_resume_text
    original_score = jobs_api.score_resume_job_match

    def counted_extract(*args, **kwargs):
        nonlocal extraction_calls
        extraction_calls += 1
        return original_extract(*args, **kwargs)

    def counted_score(*args, **kwargs):
        nonlocal scoring_calls
        scoring_calls += 1
        return original_score(*args, **kwargs)

    monkeypatch.setattr(jobs_api, "extract_resume_text", counted_extract)
    monkeypatch.setattr(jobs_api, "score_resume_job_match", counted_score)

    url = f"/api/jobs/matches?resume_id={resume_id}"

    first_response = match_context["client"].get(url)
    assert first_response.status_code == 200, first_response.text

    first_item = first_response.json()["items"][0]
    first_score = first_item["match_score"]

    assert extraction_calls == 1
    assert scoring_calls == 1

    # These fields are not part of the matching fingerprint. They must
    # nevertheless be loaded fresh when a cached score is reused.
    with match_context["factory"]() as db:
        job = db.get(Job, job_id)
        job.listing_status = "closed"
        job.eligibility_status = "ineligible"
        db.commit()

    second_response = match_context["client"].get(url)
    assert second_response.status_code == 200, second_response.text

    second_item = second_response.json()["items"][0]

    assert second_item["match_score"] == first_score
    assert second_item["listing_status"] == "closed"
    assert second_item["eligibility_status"] == "ineligible"

    # The second request reused the expensive scoring result.
    assert extraction_calls == 1
    assert scoring_calls == 1


def test_job_description_change_invalidates_cached_match_results(
    match_context,
    monkeypatch,
):
    resume_id = create_resume(match_context)
    job_id = create_job(
        match_context,
        title="Python Developer",
        description="Build APIs with Python.",
    )

    scoring_calls = 0
    original_score = jobs_api.score_resume_job_match

    def counted_score(*args, **kwargs):
        nonlocal scoring_calls
        scoring_calls += 1
        return original_score(*args, **kwargs)

    monkeypatch.setattr(jobs_api, "score_resume_job_match", counted_score)

    url = f"/api/jobs/matches?resume_id={resume_id}"

    first_response = match_context["client"].get(url)
    assert first_response.status_code == 200, first_response.text
    assert scoring_calls == 1

    with match_context["factory"]() as db:
        job = db.get(Job, job_id)
        job.description = (
            "Build APIs with Python, FastAPI, PostgreSQL and Docker."
        )
        db.commit()

    second_response = match_context["client"].get(url)
    assert second_response.status_code == 200, second_response.text

    # A changed matching-relevant job field produces a new corpus fingerprint.
    assert scoring_calls == 2


def test_resume_file_change_invalidates_cached_match_results(
    match_context,
    monkeypatch,
):
    resume_id = create_resume(match_context)

    create_job(
        match_context,
        title="Python Developer",
        description="Build APIs with Python and FastAPI.",
    )

    scoring_calls = 0
    original_score = jobs_api.score_resume_job_match

    def counted_score(*args, **kwargs):
        nonlocal scoring_calls
        scoring_calls += 1
        return original_score(*args, **kwargs)

    monkeypatch.setattr(jobs_api, "score_resume_job_match", counted_score)

    url = f"/api/jobs/matches?resume_id={resume_id}"

    first_response = match_context["client"].get(url)
    assert first_response.status_code == 200, first_response.text
    assert scoring_calls == 1

    resume_path = match_context["storage"] / "resume-user_test_1.pdf"
    resume_path.write_bytes(b"updated resume contents")

    second_response = match_context["client"].get(url)
    assert second_response.status_code == 200, second_response.text

    # The file hash changes even though the resume database ID is unchanged.
    assert scoring_calls == 2
