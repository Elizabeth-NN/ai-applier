import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_admin
from app.db.dependencies import get_db
from app.db.session import Base
from app.main import app
from app.models.job import Job


@pytest.fixture
def job_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: "user_admin"

    try:
        with TestClient(app) as client:
            client.testing_session = testing_session
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def valid_job():
    return {
        "title": "Junior Python Developer",
        "company": "Example Company",
        "location": "Remote",
        "description": "Build and maintain Python applications.",
        "source_url": "https://example.com/jobs/123",
        "employment_type": "Full-time",
    }


def test_authenticated_user_can_create_job(job_context):
    response = job_context.post("/api/jobs", json=valid_job())

    assert response.status_code == 201
    assert response.json()["title"] == "Junior Python Developer"
    assert response.json()["company"] == "Example Company"
    assert response.json()["source_url"] == (
        "https://example.com/jobs/123"
    )
    assert response.json()["id"] > 0


def test_job_creation_requires_authentication(job_context):
    def reject_user():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    app.dependency_overrides[require_admin] = reject_user

    response = job_context.post("/api/jobs", json=valid_job())

    assert response.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 256},
        {"company": ""},
        {"company": "x" * 256},
    ],
)
def test_invalid_job_fields_are_rejected(job_context, overrides):
    payload = valid_job()
    payload.update(overrides)

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_job_listing_is_public_and_supports_pagination(job_context):
    first = job_context.post("/api/jobs", json=valid_job())
    second_payload = valid_job()
    second_payload["title"] = "Junior React Developer"
    second = job_context.post("/api/jobs", json=second_payload)

    assert first.status_code == 201
    assert second.status_code == 201

    response = job_context.get("/api/jobs?skip=0&limit=1")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_invalid_pagination_is_rejected(job_context):
    assert job_context.get("/api/jobs?skip=-1").status_code == 422
    assert job_context.get("/api/jobs?limit=101").status_code == 422


def test_get_existing_job(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    response = job_context.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["id"] == job_id


def test_get_missing_job_returns_404(job_context):
    response = job_context.get("/api/jobs/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_non_admin_cannot_create_job(job_context):
    def reject_non_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    app.dependency_overrides[require_admin] = reject_non_admin

    response = job_context.post("/api/jobs", json=valid_job())

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_created_job_returns_all_fields_and_timestamp(job_context):
    payload = valid_job()

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 201
    data = response.json()

    for field in (
        "title",
        "company",
        "location",
        "description",
        "source_url",
        "employment_type",
    ):
        assert data[field] == payload[field]

    assert data["id"] > 0
    assert data["created_at"]


def test_job_creation_accepts_optional_fields_as_null(job_context):
    payload = {
        "title": "Junior Backend Developer",
        "company": "Example Company",
        "location": None,
        "description": None,
        "source_url": None,
        "employment_type": None,
    }

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 201

    data = response.json()
    assert data["location"] is None
    assert data["description"] is None
    assert data["source_url"] is None
    assert data["employment_type"] is None


@pytest.mark.parametrize("missing_field", ["title", "company"])
def test_job_creation_requires_title_and_company(
    job_context, missing_field
):
    payload = valid_job()
    del payload[missing_field]

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_empty_job_listing_returns_empty_list(job_context):
    response = job_context.get("/api/jobs")

    assert response.status_code == 200
    assert response.json() == []


def test_job_listing_skip_excludes_previously_returned_job(job_context):
    first_payload = valid_job()
    first_payload["title"] = "First Test Job"

    second_payload = valid_job()
    second_payload["title"] = "Second Test Job"

    first_response = job_context.post("/api/jobs", json=first_payload)
    second_response = job_context.post("/api/jobs", json=second_payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    all_jobs = job_context.get("/api/jobs?limit=2")
    skipped_jobs = job_context.get("/api/jobs?skip=1&limit=1")

    assert all_jobs.status_code == 200
    assert skipped_jobs.status_code == 200
    assert len(all_jobs.json()) == 2
    assert len(skipped_jobs.json()) == 1

    all_ids = {job["id"] for job in all_jobs.json()}
    skipped_id = skipped_jobs.json()[0]["id"]

    assert skipped_id in all_ids
    assert len(all_ids) == 2


def test_malformed_job_id_returns_validation_error(job_context):
    response = job_context.get("/api/jobs/not-a-number")

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("location", "x" * 256),
        ("source_url", "x" * 2049),
        ("employment_type", "x" * 101),
    ],
)
def test_optional_fields_enforce_maximum_lengths(
    job_context, field, value
):
    payload = valid_job()
    payload[field] = value

    response = job_context.post("/api/jobs", json=payload)

    assert response.status_code == 422


def test_jobicy_refresh_endpoint_returns_ingestion_summary(
    job_context, monkeypatch
):
    from app.api import jobs as jobs_api

    monkeypatch.setattr(
        jobs_api,
        "ingest_jobicy_jobs",
        lambda _db: {"fetched": 3, "inserted": 2, "updated": 1},
    )

    response = job_context.post("/api/jobs/ingest/jobicy")

    assert response.status_code == 200
    assert response.json() == {
        "fetched": 3,
        "inserted": 2,
        "updated": 1,
    }


def test_jobicy_refresh_endpoint_requires_admin(
    job_context, monkeypatch
):
    from app.api import jobs as jobs_api

    def reject_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    monkeypatch.setattr(
        jobs_api,
        "ingest_jobicy_jobs",
        lambda _db: pytest.fail("Ingestion must not run for a non-admin"),
    )
    app.dependency_overrides[require_admin] = reject_admin

    response = job_context.post("/api/jobs/ingest/jobicy")

    assert response.status_code == 403


def test_jobicy_refresh_endpoint_handles_source_failure(
    job_context, monkeypatch
):
    from app.api import jobs as jobs_api
    from app.services.jobicy_adapter import JobicyAPIError

    def fail_ingestion(_db):
        raise JobicyAPIError("Simulated upstream failure")

    monkeypatch.setattr(jobs_api, "ingest_jobicy_jobs", fail_ingestion)

    response = job_context.post("/api/jobs/ingest/jobicy")

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Jobicy could not provide a complete, valid feed."
    )


def test_jobicy_status_sync_endpoint_returns_summary(
    job_context, monkeypatch
):
    from app.api import jobs as jobs_api

    monkeypatch.setattr(
        jobs_api,
        "sync_jobicy_statuses",
        lambda _db: {
            "checked": 3,
            "active": 1,
            "closed": 1,
            "unknown": 1,
        },
    )

    response = job_context.post("/api/jobs/sync/jobicy-status")

    assert response.status_code == 200
    assert response.json() == {
        "checked": 3,
        "active": 1,
        "closed": 1,
        "unknown": 1,
    }


def test_jobicy_status_sync_endpoint_handles_source_failure(
    job_context, monkeypatch
):
    from app.api import jobs as jobs_api
    from app.services.jobicy_adapter import JobicyAPIError

    def fail(_db):
        raise JobicyAPIError("Simulated API failure")

    monkeypatch.setattr(jobs_api, "sync_jobicy_statuses", fail)

    response = job_context.post("/api/jobs/sync/jobicy-status")

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Jobicy listing statuses could not be verified."
    )


def test_job_search_matches_title_company_and_location(job_context):
    jobs = [
        {
            **valid_job(),
            "title": "Junior Python Developer",
            "company": "Acme",
            "location": "Remote",
        },
        {
            **valid_job(),
            "title": "Frontend Engineer",
            "company": "Python Works",
            "location": "Nairobi",
        },
        {
            **valid_job(),
            "title": "QA Engineer",
            "company": "Example Ltd",
            "location": "Kenya",
        },
    ]

    for payload in jobs:
        response = job_context.post("/api/jobs", json=payload)
        assert response.status_code == 201

    title_result = job_context.get(
        "/api/jobs/search", params={"q": "junior python"}
    )
    company_result = job_context.get(
        "/api/jobs/search", params={"q": "Python Works"}
    )
    location_result = job_context.get(
        "/api/jobs/search", params={"q": "Nairobi"}
    )

    assert title_result.status_code == 200
    assert title_result.json()["total"] == 1
    assert title_result.json()["items"][0]["title"] == (
        "Junior Python Developer"
    )

    assert company_result.json()["total"] == 1
    assert company_result.json()["items"][0]["company"] == "Python Works"

    assert location_result.json()["total"] == 1
    assert location_result.json()["items"][0]["location"] == "Nairobi"


def test_job_search_paginates_and_reports_total(job_context):
    for index in range(5):
        payload = {
            **valid_job(),
            "title": f"Python Developer {index}",
        }
        assert job_context.post("/api/jobs", json=payload).status_code == 201

    first_page = job_context.get(
        "/api/jobs/search",
        params={"q": "Python Developer", "skip": 0, "limit": 2},
    )
    second_page = job_context.get(
        "/api/jobs/search",
        params={"q": "Python Developer", "skip": 2, "limit": 2},
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 5
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["skip"] == 0
    assert first_page.json()["limit"] == 2

    assert second_page.json()["total"] == 5
    assert len(second_page.json()["items"]) == 2

    first_ids = {job["id"] for job in first_page.json()["items"]}
    second_ids = {job["id"] for job in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_job_search_without_query_returns_all_jobs(job_context):
    for index in range(3):
        payload = {
            **valid_job(),
            "title": f"Test Developer {index}",
        }
        assert job_context.post("/api/jobs", json=payload).status_code == 201

    response = job_context.get(
        "/api/jobs/search", params={"limit": 2}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert len(response.json()["items"]) == 2


def test_job_search_returns_relevance_without_changing_eligibility(
    job_context,
):
    payload = valid_job()
    payload["title"] = "Junior Python Backend Developer"
    payload["description"] = "Build APIs with FastAPI and PostgreSQL."

    created = job_context.post("/api/jobs", json=payload)
    assert created.status_code == 201
    job_id = created.json()["id"]

    # Relevance is separate from the evidence-based eligibility decision.
    with job_context.testing_session() as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.eligibility_status = "unknown"
        db.commit()

    response = job_context.get(
        "/api/jobs/search", params={"q": "Junior Python"}
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == job_id
    assert item["relevance_score"] >= 60
    assert "Python/backend" in item["matched_role_families"]
    assert item["relevance_reasons"]
    assert item["eligibility_status"] == "unknown"


def test_job_search_sorts_by_relevance_before_pagination(job_context):
    generic_id = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Office Coordinator",
            "description": "Coordinate office schedules.",
        },
    ).json()["id"]

    relevant_id = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Junior Python Backend Developer",
            "description": "Build APIs using Python and FastAPI.",
        },
    ).json()["id"]

    first_page = job_context.get(
        "/api/jobs/search",
        params={"sort_by": "relevance", "skip": 0, "limit": 1},
    )
    second_page = job_context.get(
        "/api/jobs/search",
        params={"sort_by": "relevance", "skip": 1, "limit": 1},
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert first_page.json()["items"][0]["id"] == relevant_id
    assert second_page.json()["items"][0]["id"] == generic_id
    assert (
        first_page.json()["items"][0]["relevance_score"]
        >= second_page.json()["items"][0]["relevance_score"]
    )


def test_job_search_rejects_invalid_sort_by(job_context):
    response = job_context.get(
        "/api/jobs/search",
        params={"sort_by": "random"},
    )
    assert response.status_code == 422


def test_job_search_rejects_invalid_pagination(job_context):
    assert job_context.get(
        "/api/jobs/search", params={"skip": -1}
    ).status_code == 422

    assert job_context.get(
        "/api/jobs/search", params={"limit": 101}
    ).status_code == 422


def create_job_with_metadata(
    job_context,
    title,
    remote_type,
    eligibility_status,
    listing_status,
):
    payload = valid_job()
    payload["title"] = title

    response = job_context.post("/api/jobs", json=payload)
    assert response.status_code == 201

    with job_context.testing_session() as db:
        job = db.get(Job, response.json()["id"])
        assert job is not None

        job.remote_type = remote_type
        job.eligibility_status = eligibility_status
        job.listing_status = listing_status
        db.commit()

    return response.json()["id"]


def test_job_search_filters_remote_type(job_context):
    create_job_with_metadata(
        job_context, "Remote Python Developer",
        "remote", "eligible", "active",
    )
    create_job_with_metadata(
        job_context, "Hybrid React Developer",
        "hybrid", "eligible", "active",
    )
    create_job_with_metadata(
        job_context, "Onsite Java Developer",
        "onsite", "ineligible", "closed",
    )

    response = job_context.get(
        "/api/jobs/search", params={"remote_type": "remote"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == (
        "Remote Python Developer"
    )


def test_job_search_filters_eligibility_status(job_context):
    create_job_with_metadata(
        job_context, "Eligible Developer",
        "remote", "eligible", "active",
    )
    create_job_with_metadata(
        job_context, "Ineligible Developer",
        "remote", "ineligible", "active",
    )
    create_job_with_metadata(
        job_context, "Unknown Eligibility Developer",
        "remote", "unknown", "active",
    )

    response = job_context.get(
        "/api/jobs/search",
        params={"eligibility_status": "ineligible"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == (
        "Ineligible Developer"
    )


def test_job_search_filters_listing_status(job_context):
    create_job_with_metadata(
        job_context, "Active Developer",
        "remote", "eligible", "active",
    )
    create_job_with_metadata(
        job_context, "Closed Developer",
        "remote", "eligible", "closed",
    )
    create_job_with_metadata(
        job_context, "Unknown Listing Developer",
        "remote", "eligible", "unknown",
    )

    response = job_context.get(
        "/api/jobs/search", params={"listing_status": "closed"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == (
        "Closed Developer"
    )


def test_job_search_combines_text_and_metadata_filters(job_context):
    create_job_with_metadata(
        job_context, "Python Backend Developer",
        "remote", "eligible", "active",
    )
    create_job_with_metadata(
        job_context, "Python Frontend Developer",
        "hybrid", "eligible", "active",
    )

    response = job_context.get(
        "/api/jobs/search",
        params={"q": "Python", "remote_type": "remote"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == (
        "Python Backend Developer"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"remote_type": "any"},
        {"eligibility_status": "maybe"},
        {"listing_status": "pending"},
    ],
)
def test_job_search_rejects_invalid_discovery_filters(
    job_context, params
):
    response = job_context.get("/api/jobs/search", params=params)

    assert response.status_code == 422


def test_job_search_treats_null_remote_type_as_unknown(job_context):
    job_id = create_job_with_metadata(
        job_context, "Unclassified Remote Developer",
        "remote", "unknown", "unknown",
    )

    with job_context.testing_session() as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.remote_type = None
        db.commit()

    response = job_context.get(
        "/api/jobs/search", params={"remote_type": "unknown"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == job_id


def test_admin_can_verify_job_eligibility_with_evidence(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    assert created.status_code == 201
    job_id = created.json()["id"]

    response = job_context.post(
        f"/api/jobs/{job_id}/eligibility",
        json={
            "eligibility_status": "eligible",
            "evidence_url": "https://example.com/careers",
            "evidence": "Employer confirms applications from Kenya are accepted.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["eligibility_status"] == "eligible"
    assert data["eligibility_evidence_url"] == (
        "https://example.com/careers"
    )
    assert data["eligibility_evidence"] == (
        "Employer confirms applications from Kenya are accepted."
    )
    assert data["eligibility_verified_at"]
    assert data["eligibility_verified_by"] == "user_admin"
    assert "Kenya" in data["eligible_countries"]


def test_admin_can_mark_job_ineligible_with_evidence(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    response = job_context.post(
        f"/api/jobs/{job_id}/eligibility",
        json={
            "eligibility_status": "ineligible",
            "evidence_url": "https://example.com/requirements",
            "evidence": "Employer explicitly excludes applicants based in Kenya.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["eligibility_status"] == "ineligible"
    assert data["eligibility_evidence_url"] == (
        "https://example.com/requirements"
    )
    assert data["eligibility_verified_by"] == "user_admin"
    assert data["eligibility_verified_at"]


@pytest.mark.parametrize(
    "payload",
    [
        {"eligibility_status": "eligible"},
        {
            "eligibility_status": "eligible",
            "evidence_url": "https://example.com/careers",
        },
        {
            "eligibility_status": "ineligible",
            "evidence_url": "https://example.com/requirements",
            "evidence": "   ",
        },
        {
            "eligibility_status": "eligible",
            "evidence_url": "javascript:alert(1)",
            "evidence": "Evidence text",
        },
        {
            "eligibility_status": "maybe",
            "evidence_url": "https://example.com/careers",
            "evidence": "Evidence text",
        },
    ],
)
def test_invalid_eligibility_verification_is_rejected(job_context, payload):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    response = job_context.post(
        f"/api/jobs/{job_id}/eligibility",
        json=payload,
    )

    assert response.status_code == 422


def test_verification_of_missing_job_returns_404(job_context):
    response = job_context.post(
        "/api/jobs/999999/eligibility",
        json={
            "eligibility_status": "eligible",
            "evidence_url": "https://example.com/careers",
            "evidence": "Employer confirms applicants from Kenya are accepted.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_eligibility_verification_requires_admin(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    def reject_non_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    app.dependency_overrides[require_admin] = reject_non_admin

    response = job_context.post(
        f"/api/jobs/{job_id}/eligibility",
        json={
            "eligibility_status": "eligible",
            "evidence_url": "https://example.com/careers",
            "evidence": "Employer confirms applicants from Kenya are accepted.",
        },
    )

    assert response.status_code == 403


def test_unknown_eligibility_clears_current_verification(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    verified = job_context.post(
        f"/api/jobs/{job_id}/eligibility",
        json={
            "eligibility_status": "eligible",
            "evidence_url": "https://example.com/careers",
            "evidence": "Employer confirms applicants from Kenya are accepted.",
        },
    )
    assert verified.status_code == 200

    reset = job_context.post(
        f"/api/jobs/{job_id}/eligibility",
        json={"eligibility_status": "unknown"},
    )

    assert reset.status_code == 200
    data = reset.json()
    assert data["eligibility_status"] == "unknown"
    assert data["eligibility_evidence_url"] is None
    assert data["eligibility_evidence"] is None
    assert data["eligibility_verified_at"] is None
    assert data["eligibility_verified_by"] is None
