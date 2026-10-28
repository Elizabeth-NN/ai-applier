import httpx
import pytest

from app.services.himalayas_adapter import (
    HIMALAYAS_API_URL,
    HimalayasAPIError,
    fetch_himalayas_jobs,
    normalize_job,
)


def sample_job(job_id="https://himalayas.app/companies/example/jobs/python-dev"):
    return {
        "guid": job_id,
        "title": "Remote Python Developer",
        "companyName": "Example Company",
        "applicationLink": "https://himalayas.app/jobs/apply/python-dev",
        "employmentType": "Full-time",
        "locationRestrictions": ["Worldwide", "Africa"],
        "description": "<p>Build backend services.</p>",
        "excerpt": "Build backend services.",
        "pubDate": 1792497600,
    }


def make_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def test_normalize_job_maps_himalayas_fields():
    result = normalize_job(sample_job())

    assert result["source_name"] == "himalayas"
    assert result["source_job_id"] == (
        "https://himalayas.app/companies/example/jobs/python-dev"
    )
    assert result["source_url"] == (
        "https://himalayas.app/jobs/apply/python-dev"
    )
    assert result["title"] == "Remote Python Developer"
    assert result["company"] == "Example Company"
    assert result["location"] == "Worldwide, Africa"
    assert result["employment_type"] == "Full-time"
    assert result["remote_type"] == "remote"
    assert result["eligibility_status"] == "unknown"
    assert result["listing_status"] == "unknown"
    assert result["published_at"] is not None




def test_normalize_job_parses_iso_timestamps_and_expiry():
    raw = sample_job()
    raw["pubDate"] = "2026-10-28T07:15:46+00:00"
    raw["expiryDate"] = "2026-12-27T07:15:45+00:00"

    result = normalize_job(raw)

    assert result["published_at"].isoformat() == "2026-10-28T07:15:46+00:00"
    assert result["expires_at"].isoformat() == "2026-12-27T07:15:45+00:00"


def test_normalize_job_parses_unix_timestamps():
    raw = sample_job()
    raw["pubDate"] = 1793171746
    raw["expiryDate"] = 1798442145

    result = normalize_job(raw)

    assert result["published_at"] is not None
    assert result["expires_at"] is not None


def test_normalize_job_rejects_invalid_expiry_timestamp():
    raw = sample_job()
    raw["expiryDate"] = "not-a-date"

    with pytest.raises(HimalayasAPIError):
        normalize_job(raw)

@pytest.mark.parametrize(
    "overrides",
    [
        {"guid": ""},
        {"title": ""},
        {"companyName": None},
        {"applicationLink": "/apply"},
        {"pubDate": "not-a-timestamp"},
        {"locationRestrictions": "Worldwide"},
    ],
)
def test_normalize_job_rejects_invalid_fields(overrides):
    raw = sample_job()
    raw.update(overrides)

    with pytest.raises(HimalayasAPIError):
        normalize_job(raw)


def test_fetch_himalayas_jobs_follows_cursor_pagination():
    requests = []

    def handler(request):
        requests.append(request)

        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "jobs": [sample_job("https://himalayas.app/jobs/one")],
                    "nextCursor": "cursor-two",
                    "limit": 20,
                    "totalCount": 2,
                },
            )

        return httpx.Response(
            200,
            json={
                "jobs": [sample_job("https://himalayas.app/jobs/two")],
                "limit": 20,
                "totalCount": 2,
            },
        )

    with make_client(handler) as client:
        results = fetch_himalayas_jobs(client=client)

    assert len(results) == 2
    assert [job["source_job_id"] for job in results] == [
        "https://himalayas.app/jobs/one",
        "https://himalayas.app/jobs/two",
    ]
    assert str(requests[0].url).split("?")[0] == HIMALAYAS_API_URL
    assert requests[0].url.params["limit"] == "20"
    assert requests[0].url.params["limit"] == "20"
    assert requests[1].url.params["cursor"] == "cursor-two"


def test_fetch_himalayas_jobs_rejects_invalid_response():
    def handler(_request):
        return httpx.Response(200, json={"jobs": "not-a-list"})

    with make_client(handler) as client:
        with pytest.raises(HimalayasAPIError):
            fetch_himalayas_jobs(client=client)


def test_fetch_himalayas_jobs_rejects_http_failure():
    def handler(_request):
        return httpx.Response(503, json={"error": "unavailable"})

    with make_client(handler) as client:
        with pytest.raises(HimalayasAPIError):
            fetch_himalayas_jobs(client=client)


def test_fetch_himalayas_jobs_rejects_repeated_cursor():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "jobs": [],
                "nextCursor": "same-cursor",
            },
        )

    with make_client(handler) as client:
        with pytest.raises(HimalayasAPIError, match="repeated cursor"):
            fetch_himalayas_jobs(client=client)


def test_fetch_himalayas_jobs_rejects_page_limit():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "jobs": [],
                "nextCursor": "cursor-one",
            },
        )

    with make_client(handler) as client:
        with pytest.raises(HimalayasAPIError, match="safety limit"):
            fetch_himalayas_jobs(max_pages=1, client=client)


def test_fetch_himalayas_jobs_rejects_invalid_max_pages():
    with pytest.raises(ValueError):
        fetch_himalayas_jobs(max_pages=0)


def test_adapter_uses_documented_public_endpoint():
    assert HIMALAYAS_API_URL == "https://himalayas.app/jobs/api"
