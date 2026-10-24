import httpx
import pytest

from app.services.jobicy_adapter import (
    JOBICY_API_URL,
    JobicyAPIError,
    fetch_jobicy_jobs,
    normalize_job,
)


def sample_job(job_id=123):
    return {
        "id": job_id,
        "url": f"https://jobicy.com/jobs/{job_id}",
        "jobTitle": "Remote Python Developer",
        "companyName": "Example Company",
        "jobGeo": "Worldwide",
        "jobType": ["Full-time", "Contract"],
        "jobExcerpt": "Build backend services.",
        "pubDate": "2026-10-20T12:00:00Z",
    }


def make_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://jobicy.com",
    )


def test_normalize_job_preserves_source_and_unknown_eligibility():
    result = normalize_job(sample_job())

    assert result["source_name"] == "jobicy"
    assert result["source_job_id"] == "123"
    assert result["source_url"] == "https://jobicy.com/jobs/123"
    assert result["title"] == "Remote Python Developer"
    assert result["employment_type"] == "Full-time, Contract"
    assert result["remote_type"] == "remote"
    assert result["eligible_countries"] is None
    assert result["eligibility_status"] == "unknown"
    assert result["listing_status"] == "unknown"
    assert result["published_at"] is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": None},
        {"jobTitle": ""},
        {"companyName": None},
        {"url": "/jobs/123"},
    ],
)
def test_normalize_job_rejects_missing_required_fields(overrides):
    raw = sample_job()
    raw.update(overrides)

    with pytest.raises(JobicyAPIError):
        normalize_job(raw)


def test_fetch_jobicy_jobs_follows_cursor_pagination():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "jobs": [sample_job(1)],
                    "hasMore": True,
                    "nextCursor": "cursor-two",
                },
            )

        return httpx.Response(
            200,
            json={
                "success": True,
                "jobs": [sample_job(2)],
                "hasMore": False,
                "nextCursor": None,
            },
        )

    with make_client(handler) as client:
        results = fetch_jobicy_jobs(count=10, client=client)

    assert len(results) == 2
    assert [job["source_job_id"] for job in results] == ["1", "2"]
    assert requests[0].url.path == "/api/jobs"
    assert requests[0].url.params["count"] == "10"
    assert requests[1].url.params["cursor"] == "cursor-two"


def test_fetch_jobicy_jobs_rejects_unsuccessful_response():
    def handler(_request):
        return httpx.Response(
            200,
            json={"success": False, "jobs": [], "hasMore": False},
        )

    with make_client(handler) as client:
        with pytest.raises(JobicyAPIError):
            fetch_jobicy_jobs(client=client)


def test_fetch_jobicy_jobs_rejects_invalid_pagination():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "jobs": [sample_job()],
                "hasMore": True,
                "nextCursor": None,
            },
        )

    with make_client(handler) as client:
        with pytest.raises(JobicyAPIError, match="no cursor"):
            fetch_jobicy_jobs(client=client)


def test_fetch_jobicy_jobs_rejects_http_failure():
    def handler(_request):
        return httpx.Response(503, json={"success": False})

    with make_client(handler) as client:
        with pytest.raises(JobicyAPIError):
            fetch_jobicy_jobs(client=client)


def test_fetch_jobicy_jobs_enforces_page_size():
    with pytest.raises(ValueError):
        fetch_jobicy_jobs(count=201)


def test_adapter_uses_documented_public_endpoint():
    assert JOBICY_API_URL == "https://jobicy.com/api/jobs"
