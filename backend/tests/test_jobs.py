import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_admin, require_user
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


def set_job_employment_type(job_context, job_id, employment_type):
    with job_context.testing_session() as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.employment_type = employment_type
        db.commit()


def test_job_search_filters_employment_type_case_insensitively(job_context):
    full_time_id = job_context.post(
        "/api/jobs",
        json={**valid_job(), "title": "Full-time Developer"},
    ).json()["id"]
    contract_id = job_context.post(
        "/api/jobs",
        json={**valid_job(), "title": "Contract Developer"},
    ).json()["id"]
    internship_id = job_context.post(
        "/api/jobs",
        json={**valid_job(), "title": "Internship Developer"},
    ).json()["id"]

    set_job_employment_type(job_context, full_time_id, "Full-time")
    set_job_employment_type(job_context, contract_id, "CONTRACT")
    set_job_employment_type(
        job_context, internship_id, "Internship"
    )

    response = job_context.get(
        "/api/jobs/search", params={"employment_type": "contract"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == contract_id


def test_job_search_matches_multiple_employment_types(job_context):
    multi_type_id = job_context.post(
        "/api/jobs",
        json={**valid_job(), "title": "Flexible Developer"},
    ).json()["id"]

    set_job_employment_type(
        job_context, multi_type_id, "Full-time, Contract"
    )

    full_time = job_context.get(
        "/api/jobs/search", params={"employment_type": "full-time"}
    )
    contract = job_context.get(
        "/api/jobs/search", params={"employment_type": "contract"}
    )

    assert full_time.status_code == 200
    assert contract.status_code == 200
    assert full_time.json()["items"][0]["id"] == multi_type_id
    assert contract.json()["items"][0]["id"] == multi_type_id


def test_job_search_filters_unknown_employment_type(job_context):
    known_id = job_context.post(
        "/api/jobs",
        json={**valid_job(), "title": "Known Type Developer"},
    ).json()["id"]
    unknown_id = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Unknown Type Developer",
            "employment_type": None,
        },
    ).json()["id"]

    set_job_employment_type(job_context, known_id, "Full-time")

    response = job_context.get(
        "/api/jobs/search", params={"employment_type": "unknown"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == unknown_id


def test_job_search_combines_employment_type_with_other_filters(
    job_context,
):
    matching_id = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Remote Contract Developer",
        },
    ).json()["id"]
    job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Hybrid Contract Developer",
        },
    )

    set_job_employment_type(
        job_context, matching_id, "Contract"
    )

    with job_context.testing_session() as db:
        job = db.get(Job, matching_id)
        assert job is not None
        job.remote_type = "remote"
        db.commit()

        other_jobs = db.query(Job).filter(
            Job.title == "Hybrid Contract Developer"
        ).all()
        for other_job in other_jobs:
            other_job.employment_type = "Contract"
            other_job.remote_type = "hybrid"
        db.commit()

    response = job_context.get(
        "/api/jobs/search",
        params={
            "employment_type": "contract",
            "remote_type": "remote",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == matching_id


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
        {"employment_type": "temporary"},
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

def test_admin_can_set_job_application_url(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    response = job_context.patch(
        f"/api/jobs/{job_id}/application-url",
        json={
            "application_url": (
                "https://boards.greenhouse.io/example/jobs/123"
            )
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["application_url"] == (
        "https://boards.greenhouse.io/example/jobs/123"
    )
    assert data["source_url"] == "https://example.com/jobs/123"


def test_admin_can_replace_job_application_url(job_context):
    created = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "application_url": "https://example.com/apply/old",
        },
    )
    job_id = created.json()["id"]

    response = job_context.patch(
        f"/api/jobs/{job_id}/application-url",
        json={"application_url": "https://jobs.lever.co/example/123"},
    )

    assert response.status_code == 200
    assert response.json()["application_url"] == (
        "https://jobs.lever.co/example/123"
    )


def test_admin_can_clear_job_application_url(job_context):
    created = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "application_url": "https://example.com/apply",
        },
    )
    job_id = created.json()["id"]

    response = job_context.patch(
        f"/api/jobs/{job_id}/application-url",
        json={"application_url": None},
    )

    assert response.status_code == 200
    assert response.json()["application_url"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"application_url": "http://example.com/apply"},
        {"application_url": "javascript:alert(1)"},
        {"application_url": "https://user:password@example.com/apply"},
        {},
    ],
)
def test_invalid_application_url_updates_are_rejected(
    job_context, payload
):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    response = job_context.patch(
        f"/api/jobs/{job_id}/application-url",
        json=payload,
    )

    assert response.status_code == 422


def test_application_url_update_for_missing_job_returns_404(job_context):
    response = job_context.patch(
        "/api/jobs/999999/application-url",
        json={"application_url": "https://example.com/apply"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_application_url_update_requires_admin(job_context):
    created = job_context.post("/api/jobs", json=valid_job())
    job_id = created.json()["id"]

    def reject_non_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    app.dependency_overrides[require_admin] = reject_non_admin

    response = job_context.patch(
        f"/api/jobs/{job_id}/application-url",
        json={"application_url": "https://example.com/apply"},
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


def test_himalayas_batch_endpoint_returns_batch_result(
    job_context, monkeypatch
):
    from app.services import job_ingestion

    expected = {
        "status": "running",
        "pages_this_batch": 2,
        "fetched_this_batch": 40,
        "inserted_this_batch": 40,
        "updated_this_batch": 0,
        "expired_this_batch": 0,
        "pages_fetched": 2,
        "fetched": 40,
        "inserted": 40,
        "updated": 0,
        "expired": 0,
        "completed": False,
    }
    calls = {}

    def fake_ingest(db, *, max_pages=5):
        calls["max_pages"] = max_pages
        return expected

    monkeypatch.setattr(
        job_ingestion, "ingest_himalayas_batch", fake_ingest
    )

    response = job_context.post(
        "/api/jobs/ingest/himalayas/batch?max_pages=2"
    )

    assert response.status_code == 200
    assert response.json() == expected
    assert calls["max_pages"] == 2


def test_himalayas_batch_endpoint_maps_upstream_error_to_502(
    job_context, monkeypatch
):
    from app.services import job_ingestion
    from app.services.himalayas_adapter import HimalayasAPIError

    def fail_ingestion(db, *, max_pages=5):
        raise HimalayasAPIError("Upstream feed unavailable")

    monkeypatch.setattr(
        job_ingestion, "ingest_himalayas_batch", fail_ingestion
    )

    response = job_context.post("/api/jobs/ingest/himalayas/batch")

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Himalayas could not provide a valid batch."
    )


@pytest.mark.parametrize("max_pages", [0, 26, -1])
def test_himalayas_batch_endpoint_rejects_invalid_page_limits(
    job_context, max_pages
):
    response = job_context.post(
        "/api/jobs/ingest/himalayas/batch",
        params={"max_pages": max_pages},
    )

    assert response.status_code == 422


def test_himalayas_batch_endpoint_requires_admin(
    job_context, monkeypatch
):
    from app.services import job_ingestion

    def fail_if_called(*args, **kwargs):
        pytest.fail("Batch ingestion must not run for a non-admin")

    monkeypatch.setattr(
        job_ingestion, "ingest_himalayas_batch", fail_if_called
    )

    def reject_admin():
        raise HTTPException(
            status_code=403, detail="Admin access required"
        )

    from app.core.auth import require_admin

    app.dependency_overrides[require_admin] = reject_admin

    response = job_context.post("/api/jobs/ingest/himalayas/batch")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"

@pytest.mark.parametrize(
    "endpoint,ingestion_name,changed_result,unchanged_result",
    [
        (
            "/api/jobs/ingest/jobicy",
            "ingest_jobicy_jobs",
            {"fetched": 1, "inserted": 1, "updated": 0},
            {"fetched": 1, "inserted": 0, "updated": 0},
        ),
        (
            "/api/jobs/ingest/himalayas",
            "ingest_himalayas_jobs",
            {"fetched": 1, "inserted": 0, "updated": 1},
            {"fetched": 1, "inserted": 0, "updated": 0},
        ),
        (
            "/api/jobs/ingest/himalayas/batch",
            "ingest_himalayas_batch",
            {
                "status": "running",
                "pages_this_batch": 1,
                "fetched_this_batch": 1,
                "inserted_this_batch": 1,
                "updated_this_batch": 0,
                "expired_this_batch": 0,
                "pages_fetched": 3,
                "fetched": 100,
                "inserted": 50,
                "updated": 40,
                "expired": 10,
                "completed": False,
            },
            {
                "status": "running",
                "pages_this_batch": 1,
                "fetched_this_batch": 1,
                "inserted_this_batch": 0,
                "updated_this_batch": 0,
                "expired_this_batch": 1,
                "pages_fetched": 3,
                "fetched": 100,
                "inserted": 50,
                "updated": 40,
                "expired": 10,
                "completed": False,
            },
        ),
    ],
)
@pytest.mark.parametrize(
    "result_name",
    ["changed_result", "unchanged_result"],
)
def test_ingestion_invalidates_matching_cache_only_when_jobs_change(
    job_context,
    monkeypatch,
    endpoint,
    ingestion_name,
    changed_result,
    unchanged_result,
    result_name,
):
    from app.api import jobs as jobs_api
    from app.services import job_ingestion

    result = (
        changed_result
        if result_name == "changed_result"
        else unchanged_result
    )

    invalidations = []

    monkeypatch.setattr(
        jobs_api,
        "_invalidate_corpus_term_weights",
        lambda: invalidations.append(True),
    )

    ingestion_function = (
        job_ingestion
        if ingestion_name == "ingest_himalayas_batch"
        else jobs_api
    )

    def fake_ingestion(*args, **kwargs):
        return result

    monkeypatch.setattr(
        ingestion_function,
        ingestion_name,
        fake_ingestion,
    )

    response = job_context.post(endpoint)

    assert response.status_code == 200
    assert len(invalidations) == (
        1 if result_name == "changed_result" else 0
    )


@pytest.mark.parametrize(
    ("title", "expected_level"),
    [
        ("Graduate Python Developer", "entry-level"),
        ("Junior Python Developer", "junior"),
        ("Mid-Level Backend Engineer", "mid-level"),
        ("Senior Python Engineer", "senior"),
        ("Software Engineering Intern", "internship"),
        ("Software Developer", "unknown"),
    ],
)
def test_job_search_returns_experience_level(
    job_context, title, expected_level
):
    created = job_context.post(
        "/api/jobs",
        json={**valid_job(), "title": title},
    )
    assert created.status_code == 201

    response = job_context.get("/api/jobs/search")

    assert response.status_code == 200
    matching = next(
        item for item in response.json()["items"]
        if item["id"] == created.json()["id"]
    )
    assert matching["experience_level"] == expected_level


def test_job_search_filters_experience_level_with_accurate_pagination(
    job_context,
):
    junior_ids = []
    for index in range(3):
        response = job_context.post(
            "/api/jobs",
            json={
                **valid_job(),
                "title": f"Junior Python Developer {index}",
            },
        )
        junior_ids.append(response.json()["id"])

    job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Senior Python Engineer",
        },
    )

    first_page = job_context.get(
        "/api/jobs/search",
        params={
            "experience_level": "junior",
            "skip": 0,
            "limit": 2,
        },
    )
    second_page = job_context.get(
        "/api/jobs/search",
        params={
            "experience_level": "junior",
            "skip": 2,
            "limit": 2,
        },
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2

    assert second_page.status_code == 200
    assert second_page.json()["total"] == 3
    assert len(second_page.json()["items"]) == 1

    first_ids = {
        item["id"] for item in first_page.json()["items"]
    }
    second_ids = {
        item["id"] for item in second_page.json()["items"]
    }

    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == set(junior_ids)


def test_job_search_combines_experience_level_with_text_filter(
    job_context,
):
    junior_id = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Junior Python Developer",
        },
    ).json()["id"]

    job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Senior Python Developer",
        },
    )

    job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Junior React Developer",
        },
    )

    response = job_context.get(
        "/api/jobs/search",
        params={
            "q": "Python",
            "experience_level": "junior",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == junior_id


def test_job_search_experience_filter_does_not_change_eligibility(
    job_context,
):
    created = job_context.post(
        "/api/jobs",
        json={
            **valid_job(),
            "title": "Junior Python Developer",
        },
    )
    job_id = created.json()["id"]

    response = job_context.get(
        "/api/jobs/search",
        params={"experience_level": "junior"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]

    assert item["id"] == job_id
    assert item["experience_level"] == "junior"
    assert item["eligibility_status"] == "unknown"


def test_job_search_rejects_invalid_experience_level(job_context):
    response = job_context.get(
        "/api/jobs/search",
        params={"experience_level": "expert"},
    )

    assert response.status_code == 422

def test_himalayas_ingestion_start_creates_durable_run(job_context):
    from app.models import (
        AutomationRun,
        AutomationTask,
        HimalayasIngestionState,
    )

    response = job_context.post("/api/jobs/ingest/himalayas/start")

    assert response.status_code == 202
    data = response.json()
    assert data["pipeline_type"] == "himalayas_ingestion"
    assert data["status"] == "queued"
    assert data["task_status"] == "queued"
    assert data["max_pages"] == 25

    db = job_context.testing_session()
    try:
        run = db.get(AutomationRun, data["run_id"])
        task = db.get(AutomationTask, data["task_id"])
        state = db.get(HimalayasIngestionState, 1)

        assert run is not None
        assert run.user_id is None
        assert run.pipeline_type == "himalayas_ingestion"
        assert run.status == "queued"

        assert task is not None
        assert task.run_id == run.id
        assert task.user_id is None
        assert task.task_type == "ingest_himalayas_batch"
        assert task.status == "queued"
        assert task.idempotency_key == "initial-batch"
        assert task.payload == {"max_pages": 25}

        assert state is not None
        assert state.automation_run_id == run.id
        assert state.status == "running"
        assert state.cursor is None
        assert state.processed_batches == {}
        assert state.pages_fetched == 0
        assert state.fetched == 0
        assert state.inserted == 0
        assert state.updated == 0
        assert state.expired == 0
        assert state.completed_at is None
    finally:
        db.close()


def test_himalayas_ingestion_start_resets_legacy_scan(job_context):
    from app.models import HimalayasIngestionState

    db = job_context.testing_session()
    try:
        db.add(HimalayasIngestionState(
            id=1,
            cursor="legacy-cursor",
            status="running",
            pages_fetched=65,
            fetched=1300,
            inserted=1300,
            updated=0,
            expired=0,
            processed_batches={},
        ))
        db.commit()
    finally:
        db.close()

    response = job_context.post("/api/jobs/ingest/himalayas/start")

    assert response.status_code == 202

    db = job_context.testing_session()
    try:
        state = db.get(HimalayasIngestionState, 1)
        assert state is not None
        assert state.automation_run_id == response.json()["run_id"]
        assert state.cursor is None
        assert state.status == "running"
        assert state.pages_fetched == 0
        assert state.fetched == 0
        assert state.inserted == 0
        assert state.updated == 0
        assert state.expired == 0
        assert state.processed_batches == {}
        assert state.completed_at is None
    finally:
        db.close()


def test_himalayas_ingestion_start_rejects_existing_active_run(job_context):
    from app.models import AutomationRun, HimalayasIngestionState

    db = job_context.testing_session()
    try:
        run = AutomationRun(
            user_id=None,
            pipeline_type="himalayas_ingestion",
            trigger_type="manual",
            status="queued",
            summary={},
        )
        db.add(run)
        db.flush()

        db.add(HimalayasIngestionState(
            id=1,
            cursor="existing-cursor",
            automation_run_id=run.id,
            status="running",
            processed_batches={},
        ))
        db.commit()
        original_run_id = run.id
    finally:
        db.close()

    response = job_context.post("/api/jobs/ingest/himalayas/start")

    assert response.status_code == 409
    assert "already active" in response.json()["detail"]

    db = job_context.testing_session()
    try:
        runs = db.query(AutomationRun).all()
        state = db.get(HimalayasIngestionState, 1)

        assert len(runs) == 1
        assert runs[0].id == original_run_id
        assert state.automation_run_id == original_run_id
        assert state.cursor == "existing-cursor"
    finally:
        db.close()


def test_himalayas_ingestion_start_requires_admin(job_context):
    from app.models import AutomationRun, HimalayasIngestionState

    def reject_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    from app.core.auth import require_admin
    app.dependency_overrides[require_admin] = reject_admin

    response = job_context.post("/api/jobs/ingest/himalayas/start")

    assert response.status_code == 403

    db = job_context.testing_session()
    try:
        assert db.query(AutomationRun).count() == 0
        assert db.get(HimalayasIngestionState, 1) is None
    finally:
        db.close()

def test_screening_start_creates_durable_run_and_task(job_context):
    from app.models import AutomationRun, AutomationTask, Resume

    app.dependency_overrides[require_user] = lambda: "user_screening"

    db = job_context.testing_session()
    resume = Resume(
        user_id="user_screening",
        original_filename="resume.pdf",
        storage_key="user_screening/resume.pdf",
        content_type="application/pdf",
        size_bytes=1024,
    )
    db.add(resume)
    db.commit()
    resume_id = resume.id
    db.close()

    response = job_context.post(
        "/api/jobs/screen/start",
        json={"resume_id": resume_id},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["pipeline_type"] == "job_screening"
    assert data["status"] == "queued"
    assert data["task_status"] == "queued"
    assert data["resume_id"] == resume_id

    db = job_context.testing_session()
    try:
        run = db.get(AutomationRun, data["run_id"])
        task = db.get(AutomationTask, data["task_id"])

        assert run.user_id == "user_screening"
        assert run.pipeline_type == "job_screening"
        assert run.status == "queued"
        assert run.summary["resume_id"] == resume_id

        assert task.run_id == run.id
        assert task.user_id == "user_screening"
        assert task.task_type == "screen_jobs"
        assert task.status == "queued"
        assert task.payload == {"resume_id": resume_id}
        assert task.max_attempts == 3
    finally:
        db.close()


def test_screening_start_rejects_resume_owned_by_another_user(
    job_context,
):
    from app.models import AutomationRun, Resume

    app.dependency_overrides[require_user] = lambda: "user_screening"

    db = job_context.testing_session()
    db.add(Resume(
        user_id="another_user",
        original_filename="resume.pdf",
        storage_key="another_user/resume.pdf",
        content_type="application/pdf",
        size_bytes=1024,
    ))
    db.commit()
    db.close()

    response = job_context.post(
        "/api/jobs/screen/start",
        json={"resume_id": 1},
    )

    assert response.status_code == 404

    db = job_context.testing_session()
    try:
        assert db.query(AutomationRun).count() == 0
    finally:
        db.close()


def test_screening_start_rejects_second_active_run(job_context):
    from app.models import AutomationRun, Resume

    app.dependency_overrides[require_user] = lambda: "user_screening"

    db = job_context.testing_session()
    resume = Resume(
        user_id="user_screening",
        original_filename="resume.pdf",
        storage_key="user_screening/resume.pdf",
        content_type="application/pdf",
        size_bytes=1024,
    )
    db.add(resume)
    db.flush()

    db.add(AutomationRun(
        user_id="user_screening",
        pipeline_type="job_screening",
        trigger_type="manual",
        status="running",
        summary={},
    ))
    db.commit()
    resume_id = resume.id
    db.close()

    response = job_context.post(
        "/api/jobs/screen/start",
        json={"resume_id": resume_id},
    )

    assert response.status_code == 409
    assert "already active" in response.json()["detail"]
