"""Fetch and normalize jobs from the public Himalayas jobs API."""

from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx


HIMALAYAS_API_URL = "https://himalayas.app/jobs/api"
HIMALAYAS_SOURCE_NAME = "himalayas"
PAGE_SIZE = 20
MAX_PAGES = 500
REQUEST_TIMEOUT_SECONDS = 30.0


class HimalayasAPIError(RuntimeError):
    """Raised when the Himalayas API returns an invalid or incomplete feed."""


def _required_text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HimalayasAPIError(f"Job is missing required field: {key}")
    return value.strip()


def _required_http_url(raw: dict, key: str) -> str:
    value = _required_text(raw, key)
    parsed = urlparse(value)

    if parsed.scheme != "https" or not parsed.netloc:
        raise HimalayasAPIError(f"Job has an invalid URL in field: {key}")

    return value


def _optional_text(raw: dict, key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HimalayasAPIError(f"Job has an invalid field: {key}")

    value = value.strip()
    return value or None


def _published_at(raw: dict) -> datetime | None:
    value = raw.get("pubDate")
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HimalayasAPIError("Job has an invalid pubDate timestamp")

    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise HimalayasAPIError("Job has an invalid pubDate timestamp") from exc


def normalize_job(raw: dict) -> dict:
    """Convert one Himalayas API listing into the shared Job model fields."""
    if not isinstance(raw, dict):
        raise HimalayasAPIError("Job entry must be an object")

    guid = _required_http_url(raw, "guid")
    application_url = _required_http_url(raw, "applicationLink")

    company = _required_text(raw, "companyName")
    title = _required_text(raw, "title")

    location_restrictions = raw.get("locationRestrictions")
    if location_restrictions is not None:
        if not isinstance(location_restrictions, list) or not all(
            isinstance(item, str) for item in location_restrictions
        ):
            raise HimalayasAPIError(
                "Job has invalid locationRestrictions"
            )
        location = ", ".join(
            item.strip() for item in location_restrictions if item.strip()
        ) or None
    else:
        location = None

    employment_type = _optional_text(raw, "employmentType")
    description = _optional_text(raw, "description")
    excerpt = _optional_text(raw, "excerpt")

    if description is None:
        description = excerpt

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "source_url": application_url,
        "employment_type": employment_type,
        "source_name": HIMALAYAS_SOURCE_NAME,
        "source_job_id": guid,
        "remote_type": "remote",
        "eligible_countries": None,
        "eligibility_status": "unknown",
        "listing_status": "unknown",
        "published_at": _published_at(raw),
    }


def fetch_himalayas_jobs(
    *,
    max_pages: int = MAX_PAGES,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch the complete Himalayas feed using cursor pagination."""
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    jobs: list[dict] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None

    try:
        for page_number in range(max_pages):
            params = {"limit": PAGE_SIZE}
            if cursor is not None:
                params["cursor"] = cursor

            try:
                response = client.get(HIMALAYAS_API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise HimalayasAPIError(
                    "Could not retrieve a valid Himalayas API response"
                ) from exc

            if not isinstance(payload, dict):
                raise HimalayasAPIError("Himalayas response must be an object")

            page_jobs = payload.get("jobs")
            if not isinstance(page_jobs, list):
                raise HimalayasAPIError(
                    "Himalayas response is missing a valid jobs list"
                )

            normalized_page = [normalize_job(job) for job in page_jobs]
            jobs.extend(normalized_page)

            next_cursor = payload.get("nextCursor")
            if next_cursor is None or next_cursor == "":
                return jobs

            if not isinstance(next_cursor, str):
                raise HimalayasAPIError(
                    "Himalayas response contains an invalid nextCursor"
                )

            if next_cursor in seen_cursors:
                raise HimalayasAPIError(
                    "Himalayas pagination returned a repeated cursor"
                )

            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise HimalayasAPIError(
            f"Himalayas feed exceeded the {max_pages}-page safety limit"
        )
    finally:
        if owns_client:
            client.close()
