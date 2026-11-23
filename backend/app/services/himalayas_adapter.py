"""Fetch and normalize jobs from the public Himalayas jobs API."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
from urllib.parse import urlparse

import httpx


HIMALAYAS_API_URL = "https://himalayas.app/jobs/api"
HIMALAYAS_SOURCE_NAME = "himalayas"
PAGE_SIZE = 20
MAX_PAGES = 500
REQUEST_TIMEOUT_SECONDS = 30.0


class HimalayasAPIError(RuntimeError):
    """Raised when the Himalayas API returns an invalid or incomplete feed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def _retry_after_seconds(value: str | None) -> int | None:
    """Parse Retry-After as seconds or an HTTP date."""
    if not value:
        return None

    try:
        return max(0, math.ceil(float(value)))
    except (ValueError, OverflowError):
        pass

    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(
            0,
            math.ceil((retry_at - datetime.now(timezone.utc)).total_seconds()),
        )
    except (TypeError, ValueError, OverflowError):
        return None


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


def _parse_timestamp(value, field_name: str) -> datetime | None:
    """Parse an API timestamp as Unix seconds or an ISO-8601 string."""
    if value is None:
        return None

    try:
        if isinstance(value, bool):
            raise ValueError("Boolean is not a timestamp")

        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        elif isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        else:
            raise ValueError("Unsupported timestamp format")

        return parsed
    except (OverflowError, OSError, TypeError, ValueError) as exc:
        raise HimalayasAPIError(
            f"Job has an invalid {field_name} timestamp"
        ) from exc


def _published_at(raw: dict) -> datetime | None:
    return _parse_timestamp(raw.get("pubDate"), "pubDate")


def _expires_at(raw: dict) -> datetime | None:
    return _parse_timestamp(raw.get("expiryDate"), "expiryDate")


def normalize_job(raw: dict) -> dict:
    """Convert one Himalayas API listing into the shared Job model fields."""
    if not isinstance(raw, dict):
        raise HimalayasAPIError("Job entry must be an object")

    guid = _required_http_url(raw, "guid")
    application_url = _required_http_url(raw, "applicationLink")

    company = _required_text(raw, "companyName")
    title = _required_text(raw, "title")

    location_restrictions = raw.get("locationRestrictions")
    eligible_countries = None

    if location_restrictions is not None:
        if not isinstance(location_restrictions, list):
            raise HimalayasAPIError(
                "Job has invalid locationRestrictions"
            )

        eligible_countries = []
        for item in location_restrictions:
            if isinstance(item, str):
                country = item.strip()
            elif isinstance(item, dict):
                # Support the documented object shape as well as the
                # string format currently returned by the live feed.
                country = item.get("name") or item.get("alpha2")
                if not isinstance(country, str):
                    raise HimalayasAPIError(
                        "Job has invalid locationRestrictions"
                    )
                country = country.strip()
            else:
                raise HimalayasAPIError(
                    "Job has invalid locationRestrictions"
                )

            if country and country not in eligible_countries:
                eligible_countries.append(country)

        location = ", ".join(eligible_countries) or None
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
        "source_url": guid,
        "application_url": application_url,
        "employment_type": employment_type,
        "source_name": HIMALAYAS_SOURCE_NAME,
        "source_job_id": guid,
        "remote_type": "remote",
        "eligible_countries": eligible_countries,
        "eligibility_status": "unknown",
        "listing_status": "unknown",
        "published_at": _published_at(raw),
        "expires_at": _expires_at(raw),
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


def fetch_himalayas_batch(
    *,
    cursor: str | None = None,
    max_pages: int = 5,
    client: httpx.Client | None = None,
) -> dict:
    """Fetch a bounded batch and return its resumable pagination cursor."""
    if not 1 <= max_pages <= 25:
        raise ValueError("max_pages must be between 1 and 25")

    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    jobs: list[dict] = []
    seen_cursors: set[str] = set()
    current_cursor = cursor
    pages_fetched = 0

    try:
        for _ in range(max_pages):
            params = {"limit": PAGE_SIZE}
            if current_cursor is not None:
                params["cursor"] = current_cursor

            try:
                response = client.get(HIMALAYAS_API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                response = exc.response
                raise HimalayasAPIError(
                    f"Himalayas API returned HTTP {response.status_code}",
                    status_code=response.status_code,
                    retry_after_seconds=_retry_after_seconds(
                        response.headers.get("Retry-After")
                    ),
                ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise HimalayasAPIError(
                    "Could not retrieve a valid Himalayas API response"
                ) from exc

            if not isinstance(payload, dict):
                raise HimalayasAPIError(
                    "Himalayas response must be an object"
                )

            page_jobs = payload.get("jobs")
            if not isinstance(page_jobs, list):
                raise HimalayasAPIError(
                    "Himalayas response is missing a valid jobs list"
                )

            normalized_page = [normalize_job(job) for job in page_jobs]
            jobs.extend(normalized_page)
            pages_fetched += 1

            next_cursor = payload.get("nextCursor")
            if next_cursor is None or next_cursor == "":
                return {
                    "jobs": jobs,
                    "next_cursor": None,
                    "pages_fetched": pages_fetched,
                    "complete": True,
                }

            if not isinstance(next_cursor, str):
                raise HimalayasAPIError(
                    "Himalayas response contains an invalid nextCursor"
                )

            if next_cursor == current_cursor or next_cursor in seen_cursors:
                raise HimalayasAPIError(
                    "Himalayas pagination returned a repeated cursor"
                )

            seen_cursors.add(next_cursor)
            current_cursor = next_cursor

        return {
            "jobs": jobs,
            "next_cursor": current_cursor,
            "pages_fetched": pages_fetched,
            "complete": False,
        }
    finally:
        if owns_client:
            client.close()
