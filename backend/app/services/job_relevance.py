"""Deterministic, explainable relevance scoring for software job listings."""

import re
from collections.abc import Mapping
from typing import Any


# Role families and their indicative keywords.
# Phrase matching is case-insensitive and uses word boundaries.
ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Python/backend": (
        "python",
        "fastapi",
        "django",
        "flask",
        "backend",
        "back-end",
        "rest api",
        "api development",
        "sqlalchemy",
    ),
    "Full-stack": (
        "full stack",
        "full-stack",
        "fullstack",
        "next.js",
        "nextjs",
        "web application",
    ),
    "React/frontend": (
        "react",
        "next.js",
        "nextjs",
        "frontend",
        "front-end",
        "javascript",
        "typescript",
    ),
}

ENTRY_LEVEL_KEYWORDS = (
    "junior",
    "entry-level",
    "entry level",
    "graduate",
    "new grad",
    "associate",
    "intern",
    "internship",
    "trainee",
)

SENIOR_LEVEL_KEYWORDS = (
    "senior",
    "staff engineer",
    "principal engineer",
    "engineering manager",
    "director of engineering",
    "lead engineer",
)


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a phrase without matching it inside unrelated words."""
    pattern = rf"(?<!\w){re.escape(phrase.casefold())}(?!\w)"
    return re.search(pattern, text.casefold()) is not None


def score_job_relevance(job: Mapping[str, Any]) -> dict[str, Any]:
    """Return a heuristic 0-100 score, matched role families, and reasons.

    This score measures keyword alignment with the target software roles.
    It does not establish applicant eligibility, listing validity, or hiring
    probability.
    """
    title = str(job.get("title") or "")
    description = str(job.get("description") or "")
    employment_type = str(job.get("employment_type") or "")

    title_text = title.casefold()
    combined_text = f"{title}\n{description}".casefold()

    matched_families: list[str] = []
    reasons: list[str] = []
    points = 0

    # A target role in the title is stronger evidence than a description-only
    # mention. Award one contribution per role family to limit keyword spam.
    for family, keywords in ROLE_KEYWORDS.items():
        title_match = any(_contains_phrase(title_text, word) for word in keywords)
        description_match = any(
            _contains_phrase(description, word) for word in keywords
        )

        if title_match:
            matched_families.append(family)
            reasons.append(f"{family} matches the job title")
            points += 40
        elif description_match:
            matched_families.append(family)
            reasons.append(f"{family} appears in the job description")
            points += 20

    if any(_contains_phrase(title_text, word) for word in ENTRY_LEVEL_KEYWORDS):
        points += 20
        reasons.append("Title indicates a junior, graduate, or entry-level role")

    if any(_contains_phrase(title_text, word) for word in SENIOR_LEVEL_KEYWORDS):
        points -= 20
        reasons.append("Title indicates a senior or leadership role")

    if _contains_phrase(employment_type, "internship") or _contains_phrase(
        title_text, "intern"
    ):
        # Internship is relevant to early-career applicants, but cap the total.
        if not any("entry-level" in reason for reason in reasons):
            points += 5
            reasons.append("Internship opportunity")

    score = max(0, min(100, points))

    if not reasons:
        reasons.append("No strong keyword match for the target role families")

    return {
        "score": score,
        "matched_role_families": matched_families,
        "reasons": reasons,
    }
