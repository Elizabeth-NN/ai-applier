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
        "locationRestrictions": ["Kenya", "Uganda"],
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
        "https://himalayas.app/companies/example/jobs/python-dev"
    )
    assert result["application_url"] == (
        "https://himalayas.app/jobs/apply/python-dev"
    )
    assert result["title"] == "Remote Python Developer"
    assert result["company"] == "Example Company"
    assert result["location"] == "Kenya, Uganda"
    assert result["eligible_countries"] == ["Kenya", "Uganda"]
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


def test_fetch_himalayas_batch_returns_cursor_when_page_limit_reached():
    from app.services.himalayas_adapter import fetch_himalayas_batch

    requests = []

    def handler(request):
        requests.append(request)
        page = len(requests)
        return httpx.Response(
            200,
            json={
                "jobs": [
                    sample_job(
                        f"https://himalayas.app/companies/example/jobs/{page}"
                    )
                ],
                "nextCursor": f"cursor-{page + 1}",
            },
        )

    with make_client(handler) as client:
        result = fetch_himalayas_batch(max_pages=2, client=client)

    assert result["pages_fetched"] == 2
    assert len(result["jobs"]) == 2
    assert result["next_cursor"] == "cursor-3"
    assert result["complete"] is False
    assert requests[1].url.params["cursor"] == "cursor-2"


def test_fetch_himalayas_batch_resumes_from_given_cursor():
    from app.services.himalayas_adapter import fetch_himalayas_batch

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "jobs": [],
                "nextCursor": None,
            },
        )

    with make_client(handler) as client:
        result = fetch_himalayas_batch(
            cursor="saved-cursor",
            max_pages=1,
            client=client,
        )

    assert requests[0].url.params["cursor"] == "saved-cursor"
    assert result["complete"] is True
    assert result["next_cursor"] is None


@pytest.mark.parametrize("max_pages", [0, -1, 26])
def test_fetch_himalayas_batch_rejects_out_of_range_page_limit(max_pages):
    from app.services.himalayas_adapter import fetch_himalayas_batch

    with pytest.raises(ValueError):
        fetch_himalayas_batch(max_pages=max_pages)



def test_normalize_job_preserves_empty_restrictions_as_worldwide():
    raw = sample_job()
    raw["locationRestrictions"] = []

    result = normalize_job(raw)

    assert result["location"] is None
    assert result["eligible_countries"] == []


def test_normalize_job_keeps_missing_restrictions_unknown():
    raw = sample_job()
    raw.pop("locationRestrictions")

    result = normalize_job(raw)

    assert result["location"] is None
    assert result["eligible_countries"] is None


def test_normalize_job_supports_documented_restriction_objects():
    raw = sample_job()
    raw["locationRestrictions"] = [
        {"alpha2": "KE", "name": "Kenya", "slug": "kenya"},
        {"alpha2": "UG", "name": "Uganda", "slug": "uganda"},
    ]

    result = normalize_job(raw)

    assert result["location"] == "Kenya, Uganda"
    assert result["eligible_countries"] == ["Kenya", "Uganda"]
