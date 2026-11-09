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
    "Software engineering": (
        "software engineer",
        "software developer",
        "software engineering",
        "software development",
        "software programmer",
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
    employment_type = str(job.get("employment_type") or "")

    title_text = title.casefold()
    non_target_title = any(
        _contains_phrase(title_text, phrase)
        for phrase in (
            "qa",
            "quality assurance",
            "product manager",
            "sales engineer",
            "solutions engineer",
            "customer success",
            "data manager",
            "data scientist",
            "data analyst",
            "human data",
            "talent scientist",
        )
    )

    matched_families: list[str] = []
    reasons: list[str] = []
    points = 0

    # Use the job title as role evidence; company-description keywords alone
    # must not turn an unrelated position into a software-development match.
    for family, keywords in ROLE_KEYWORDS.items():
        title_match = (
            not non_target_title
            and any(_contains_phrase(title_text, word) for word in keywords)
        )

        if title_match:
            matched_families.append(family)
            reasons.append(f"{family} matches the job title")
            points += 40

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


def classify_experience_level(job: Mapping[str, Any]) -> str:
    """Classify a job using explicit experience-level evidence.

    Returns one of: internship, entry-level, junior, mid-level, senior,
    or unknown.

    Ambiguous or conflicting evidence is deliberately classified as unknown.
    This is a listing-text classification, not a judgement of applicant
    suitability or hiring eligibility.
    """
    title = str(job.get("title") or "").casefold()
    description = str(job.get("description") or "").casefold()
    employment_type = str(job.get("employment_type") or "").casefold()

    # Internship is a distinct employment category and takes precedence.
    if (
        _contains_phrase(title, "intern")
        or _contains_phrase(title, "internship")
        or _contains_phrase(employment_type, "internship")
    ):
        return "internship"

    title_patterns = {
        "entry-level": (
            "entry-level",
            "entry level",
            "graduate",
            "new grad",
            "new graduate",
            "trainee",
        ),
        "junior": ("junior", "jr."),
        "mid-level": (
            "mid-level",
            "mid level",
            "intermediate",
        ),
        "senior": (
            "senior",
            "staff engineer",
            "staff software engineer",
            "principal",
            "lead engineer",
            "lead developer",
            "engineering manager",
            "director of engineering",
            "head of engineering",
        ),
    }

    signals = {
        level
        for level, phrases in title_patterns.items()
        if any(_contains_phrase(title, phrase) for phrase in phrases)
    }

    # Only accept explicit level descriptions tied to a role or position.
    # Mentions such as "work with senior engineers" are not classification
    # evidence.
    description_patterns = {
        "entry-level": (
            r"\bentry[- ]level\s+(?:role|position|opportunity)\b",
            r"\b(?:role|position|opportunity)\s+is\s+entry[- ]level\b",
        ),
        "junior": (
            r"\bjunior\s+(?:role|position|opportunity)\b",
            r"\b(?:role|position|opportunity)\s+is\s+junior\b",
        ),
        "mid-level": (
            r"\b(?:mid[- ]level|intermediate)\s+"
            r"(?:role|position|opportunity)\b",
            r"\b(?:role|position|opportunity)\s+is\s+"
            r"(?:mid[- ]level|intermediate)\b",
        ),
        "senior": (
            r"\bsenior[- ]level\s+(?:role|position|opportunity)\b",
            r"\b(?:role|position|opportunity)\s+is\s+senior[- ]level\b",
        ),
    }

    for level, patterns in description_patterns.items():
        if any(re.search(pattern, description) for pattern in patterns):
            signals.add(level)

    if len(signals) == 1:
        return signals.pop()

    return "unknown"
