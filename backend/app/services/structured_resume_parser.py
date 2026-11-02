"""Deterministic parsing of extracted resume text into structured sections."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


SECTION_ALIASES = {
    "summary": {
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "career profile",
        "objective",
        "career objective",
        "about me",
    },
    "skills": {
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "competencies",
        "technical competencies",
        "areas of expertise",
    },
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "work history",
        "career history",
        "internship experience",
        "professional background",
    },
    "projects": {
        "projects",
        "personal projects",
        "academic projects",
        "selected projects",
        "key projects",
        "project experience",
    },
    "education": {
        "education",
        "educational background",
        "academic background",
        "academic qualifications",
        "qualifications",
    },
    "certifications": {
        "certifications",
        "certificates",
        "licenses and certifications",
        "professional certifications",
        "training and certifications",
        "courses and certifications",
    },
    "contact": {
        "contact",
        "contact information",
        "personal information",
        "personal details",
    },
    "other": {
        "awards",
        "honors",
        "honours",
        "achievements",
        "accomplishments",
        "languages",
        "references",
        "volunteer experience",
        "volunteering",
        "leadership",
        "publications",
        "interests",
        "hobbies",
        "extracurricular activities",
        "additional information",
        "additional experience",
    },
}

SECTION_HEADING_LOOKUP = {
    re.sub(r"\s+", " ", alias.casefold()).strip(): section
    for section, aliases in SECTION_ALIASES.items()
    for alias in aliases
}

EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"
)

URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>()]+",
    re.IGNORECASE,
)

BULLET_RE = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)])\s*")


def _normalise_heading(line: str) -> str:
    """Normalize a possible section heading for alias matching."""
    cleaned = line.strip()
    cleaned = re.sub(r"^[#\s]+|[#\s]+$", "", cleaned)
    cleaned = cleaned.rstrip(":")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.casefold().strip()


def _parse_heading_line(line: str) -> tuple[str | None, str | None]:
    """Recognize a heading and return any content following its colon."""
    cleaned = line.strip()
    normalized = _normalise_heading(cleaned)

    if not normalized or len(normalized) > 55:
        return None, None

    section = SECTION_HEADING_LOOKUP.get(normalized)
    if section:
        return section, None

    # Also support headings with content on the same line:
    # "Technical Skills: Python, SQL"
    if ":" in cleaned:
        heading, remainder = cleaned.split(":", 1)
        normalized_heading = _normalise_heading(heading)
        section = SECTION_HEADING_LOOKUP.get(normalized_heading)

        if section:
            return section, remainder.strip() or None

    return None, None


def _detect_section_heading(line: str) -> str | None:
    """Return the canonical section name when a line is a known heading."""
    section, _ = _parse_heading_line(line)
    return section


def _extract_contact(text: str) -> dict[str, Any]:
    """Extract basic contact details without guessing missing information."""
    emails = sorted(set(EMAIL_RE.findall(text)))
    phones = sorted(
        {
            re.sub(r"\s+", " ", match).strip()
            for match in PHONE_RE.findall(text)
        }
    )
    urls = sorted(set(URL_RE.findall(text)))

    return {
        "emails": emails,
        "phone_numbers": phones,
        "links": urls,
    }


def _clean_lines(text: str) -> list[str]:
    """Normalize line endings and discard empty lines."""
    return [
        line.strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]


def _section_entries(lines: list[str]) -> list[dict[str, str]]:
    """Turn section lines into individual non-empty entries."""
    entries = []

    for line in lines:
        cleaned = BULLET_RE.sub("", line).strip()
        if cleaned:
            entries.append({"text": cleaned})

    return entries


def parse_resume_text(text: str) -> dict[str, Any]:
    """Parse extracted resume text into predictable structured sections.

    This parser is deliberately conservative:
    - It recognizes known section headings and common additional headings.
    - It preserves unmodeled section content under ``other``.
    - It supports headings with inline content after a colon.
    - It does not infer skills, employers, job titles, or qualifications.
    - It retains the original extracted text for later review.
    """
    original_text = (text or "").strip()

    sections: dict[str, list[str]] = defaultdict(list)
    current_section = "other"

    for line in _clean_lines(original_text):
        detected_section, inline_content = _parse_heading_line(line)

        if detected_section:
            # Contact details are extracted separately from the full text.
            # Keep any other contact-section text rather than discarding it.
            current_section = (
                "other" if detected_section == "contact" else detected_section
            )

            if inline_content:
                sections[current_section].append(inline_content)

            continue

        sections[current_section].append(line)

    structured_sections = {
        name: _section_entries(section_lines)
        for name, section_lines in sections.items()
    }

    for name in SECTION_ALIASES:
        structured_sections.setdefault(name, [])

    structured_sections.setdefault("other", [])

    return {
        "contact": _extract_contact(original_text),
        "summary": structured_sections["summary"],
        "skills": structured_sections["skills"],
        "experience": structured_sections["experience"],
        "projects": structured_sections["projects"],
        "education": structured_sections["education"],
        "certifications": structured_sections["certifications"],
        "other": structured_sections["other"],
        "original_text": original_text,
    }
