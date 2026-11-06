"""Conservative, explainable screening of jobs against candidate evidence."""

from collections.abc import Mapping
from typing import Any

from app.services.job_relevance import (
    classify_experience_level,
    score_job_relevance,
)


EARLY_CAREER_LEVELS = {"internship", "entry-level", "junior"}
KNOWN_EXPERIENCE_LEVELS = EARLY_CAREER_LEVELS | {"mid-level", "senior"}


def _string_list(value: Any) -> list[str]:
    """Return only non-empty strings from a list-like profile field."""
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _preference_types(value: Any) -> list[str]:
    """Normalize employment types without assuming malformed preferences."""
    if not isinstance(value, list):
        return []
    return [
        item.strip().casefold()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def screen_job(
    job: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
    match: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Screen one job using job metadata and the authenticated user's evidence.

    Unknown or malformed data is never treated as a confirmed disqualifier.
    The match score is reported as context, not as a hiring probability.
    """
    profile = profile if isinstance(profile, Mapping) else {}
    match = match if isinstance(match, Mapping) else {}

    role_result = score_job_relevance(job)
    experience_level = classify_experience_level(job)

    target_roles = _string_list(profile.get("target_roles"))
    title = str(job.get("title") or "").casefold()
    role_title_match = any(
        target.casefold() in title for target in target_roles
    )

    if role_title_match or role_result["score"] >= 40:
        role_alignment = "aligned"
    elif role_result["score"] > 0:
        role_alignment = "partial"
    else:
        role_alignment = "weak"

    if experience_level in EARLY_CAREER_LEVELS:
        experience_fit = "aligned"
    elif experience_level in {"mid-level", "senior"}:
        experience_fit = "mismatch"
    else:
        experience_fit = "unknown"

    preferences = profile.get("work_preferences")
    if not isinstance(preferences, Mapping):
        preferences = {}

    remote_preference = preferences.get("remote")
    remote_type = str(job.get("remote_type") or "").strip().casefold()

    if remote_preference is True:
        if remote_type == "remote":
            remote_fit = "aligned"
        elif remote_type in {"hybrid", "onsite"}:
            remote_fit = "mismatch"
        else:
            remote_fit = "unknown"
    else:
        remote_fit = "not_specified"

    preferred_types = _preference_types(
        preferences.get("employment_type")
    )
    employment_type = str(job.get("employment_type") or "").strip().casefold()

    if preferred_types and employment_type:
        # Some sources store multiple employment types in one string.
        actual_types = {
            part.strip()
            for part in employment_type.replace("/", ",").split(",")
            if part.strip()
        }
        employment_fit = (
            "aligned"
            if any(
                preferred in actual_types
                or preferred == employment_type
                for preferred in preferred_types
            )
            else "mismatch"
        )
    elif preferred_types:
        employment_fit = "unknown"
    else:
        employment_fit = "not_specified"

    eligibility_status = str(
        job.get("eligibility_status") or "unknown"
    ).strip().casefold()
    eligible_countries = job.get("eligible_countries")

    if eligibility_status == "ineligible":
        kenya_eligibility = "ineligible"
    elif eligibility_status == "eligible":
        if isinstance(eligible_countries, list) and eligible_countries:
            countries = {
                country.strip().casefold()
                for country in eligible_countries
                if isinstance(country, str) and country.strip()
            }
            if "kenya" in countries:
                kenya_eligibility = "eligible"
            elif countries:
                kenya_eligibility = "conflicting_evidence"
            else:
                kenya_eligibility = "unknown"
        else:
            kenya_eligibility = "eligible"
    elif isinstance(eligible_countries, list) and any(
        isinstance(country, str) and country.strip().casefold() == "kenya"
        for country in eligible_countries
    ):
        kenya_eligibility = "eligible"
    else:
        kenya_eligibility = "unknown"

    listing_status = str(
        job.get("listing_status") or "unknown"
    ).strip().casefold()
    if listing_status not in {"active", "closed"}:
        listing_status = "unknown"

    reasons: list[str] = []
    exclusions: list[str] = []
    review_reasons: list[str] = []

    if role_alignment == "aligned":
        reasons.append("The role aligns with the target software roles.")
    elif role_alignment == "partial":
        review_reasons.append(
            "Some software-role keywords match, but target-role alignment needs review."
        )
    else:
        review_reasons.append(
            "No strong match to the target software role families was found."
        )

    if experience_fit == "aligned":
        reasons.append(
            f"The listing explicitly indicates an {experience_level} opportunity."
        )
    elif experience_fit == "mismatch":
        review_reasons.append(
            f"The listing indicates {experience_level} experience; check whether it fits your target level."
        )
    else:
        review_reasons.append(
            "The experience level could not be established from the listing."
        )

    if remote_fit == "mismatch":
        review_reasons.append(
            "The job's work arrangement does not match the remote preference."
        )
    elif remote_fit == "unknown":
        review_reasons.append(
            "The job's work arrangement needs verification."
        )

    if employment_fit == "mismatch":
        review_reasons.append(
            "The employment type does not match the saved preference."
        )
    elif employment_fit == "unknown":
        review_reasons.append(
            "The employment type needs verification against the saved preference."
        )

    if kenya_eligibility == "ineligible":
        exclusions.append(
            "The job is explicitly marked as ineligible for the candidate."
        )
    elif kenya_eligibility == "conflicting_evidence":
        review_reasons.append(
            "The eligibility status conflicts with the listed eligible countries."
        )
    elif kenya_eligibility == "unknown":
        review_reasons.append(
            "Eligibility for applicants in Kenya has not been verified."
        )

    if listing_status == "closed":
        exclusions.append("The job listing is marked as closed.")
    elif listing_status == "unknown":
        review_reasons.append(
            "The listing's active status has not been verified."
        )

    if exclusions:
        recommendation = "exclude"
    elif review_reasons:
        recommendation = "review"
    else:
        recommendation = "prioritize"

    match_score = match.get("profile_match_score")
    if not isinstance(match_score, (int, float)):
        match_score = match.get("match_score")
    if not isinstance(match_score, (int, float)):
        match_score = None

    return {
        "recommendation": recommendation,
        "role_alignment": role_alignment,
        "role_relevance_score": role_result["score"],
        "role_relevance_reasons": role_result["reasons"],
        "experience_level": experience_level,
        "experience_fit": experience_fit,
        "remote_fit": remote_fit,
        "employment_fit": employment_fit,
        "kenya_eligibility": kenya_eligibility,
        "listing_status": listing_status,
        "match_score": match_score,
        "reasons": reasons + review_reasons + exclusions,
    }
