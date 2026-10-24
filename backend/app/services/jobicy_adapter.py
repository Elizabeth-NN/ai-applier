"""Fetch and normalize public job listings from Jobicy."""

import re
from datetime import datetime
from html import unescape
from typing import Any

import httpx


JOBICY_API_URL = "https://jobicy.com/api/jobs"
SOURCE_NAME = "jobicy"


class JobicyAPIError(Exception):
    """Raised when Jobicy cannot provide a valid response."""


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = unescape(re.sub(r"<[^>]*>", " ", value))
    cleaned = " ".join(cleaned.split())
    return cleaned or None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None

    # Keep timestamps timezone-aware when the source supplies a timezone.
    return parsed


def normalize_job(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert one Jobicy listing into fields accepted by the Job model."""
    job_id = raw.get("id")
    title = _clean_text(raw.get("jobTitle"))
    company = _clean_text(raw.get("companyName"))
    source_url = raw.get("url")

    if job_id is None or isinstance(job_id, bool):
        raise JobicyAPIError("Jobicy listing is missing a valid ID.")

    if not title or not company:
        raise JobicyAPIError("Jobicy listing is missing its title or company.")

    if not isinstance(source_url, str):
        raise JobicyAPIError("Jobicy listing is missing its canonical URL.")

    source_url = source_url.strip()
    if not source_url.startswith(("https://", "http://")):
        raise JobicyAPIError("Jobicy listing has an invalid URL.")

    job_types = raw.get("jobType")
    if isinstance(job_types, list):
        employment_type = ", ".join(
            item.strip()
            for item in job_types
            if isinstance(item, str) and item.strip()
        ) or None
    elif isinstance(job_types, str):
        employment_type = _clean_text(job_types)
    else:
        employment_type = None

    description = (
        _clean_text(raw.get("jobDescription"))
        or _clean_text(raw.get("jobExcerpt"))
    )

    # The public Jobicy feed contains remote roles, but does not reliably
    # establish that every role accepts applicants residing in Kenya.
    return {
        "title": title[:255],
        "company": company[:255],
        "location": _clean_text(raw.get("jobGeo")),
        "description": description,
        "source_url": source_url,
        "employment_type": employment_type[:100] if employment_type else None,
        "source_name": SOURCE_NAME,
        "source_job_id": str(job_id),
        "remote_type": "remote",
        "eligible_countries": None,
        "eligibility_status": "unknown",
        # Presence in the recent feed alone is not a status-endpoint check.
        "listing_status": "unknown",
        "published_at": _parse_datetime(raw.get("pubDate")),
    }


def fetch_jobicy_jobs(
    *,
    count: int = 200,
    max_pages: int = 100,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Fetch all available cursor pages and normalize their listings.

    Filters are intentionally not changed between pages. A page or response
    error aborts the fetch so callers cannot mistake partial results for a
    complete refresh.
    """
    if not 1 <= count <= 200:
        raise ValueError("count must be between 1 and 200")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    owns_client = client is None
    http = client or httpx.Client(timeout=20.0)
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()

    try:
        for _ in range(max_pages):
            params: dict[str, Any] = {"count": count}
            if cursor is not None:
                params["cursor"] = cursor

            try:
                response = http.get(JOBICY_API_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise JobicyAPIError(
                    f"Unable to fetch a valid Jobicy response: {exc}"
                ) from exc

            if not isinstance(payload, dict):
                raise JobicyAPIError("Jobicy response must be a JSON object.")

            if payload.get("success") is not True:
                raise JobicyAPIError("Jobicy reported an unsuccessful response.")

            jobs = payload.get("jobs")
            if not isinstance(jobs, list):
                raise JobicyAPIError("Jobicy response has no valid jobs list.")

            for raw in jobs:
                if not isinstance(raw, dict):
                    raise JobicyAPIError(
                        "Jobicy response contains an invalid job record."
                    )
                results.append(normalize_job(raw))

            has_more = payload.get("hasMore", False)
            if not isinstance(has_more, bool):
                raise JobicyAPIError("Jobicy hasMore must be a boolean.")

            if not has_more:
                return results

            next_cursor = payload.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor.strip():
                raise JobicyAPIError(
                    "Jobicy indicated more results but supplied no cursor."
                )

            if next_cursor in seen_cursors or next_cursor == cursor:
                raise JobicyAPIError("Jobicy returned a repeated pagination cursor.")

            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise JobicyAPIError(
            f"Jobicy pagination exceeded the safety limit of {max_pages} pages."
        )
    finally:
        if owns_client:
            http.close()
