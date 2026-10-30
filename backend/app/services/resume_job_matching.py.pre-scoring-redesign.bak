"""Dynamic, explainable text matching for resumes and job descriptions.

This service does not maintain a predefined list of skills or technologies.
It compares terms extracted from the actual resume and job text.
"""

import math
import re
from collections import Counter


# Generic English words that add little value when comparing documents.
# This is a language stop-word list, not a catalogue of skills.
STOP_WORDS = frozenset("""
a an the and or but if then than so because as at by for from in into
of on onto to with without within about above across after against along
among around before behind below beneath beside between beyond during
except inside near off out outside over through throughout under until
up upon via per is am are was were be been being do does did doing
have has had having can could may might must shall should will would
i me my we our us you your he she it they them their this that these those
who whom which what where when why how all any both each few more most
other some such no not only own same too very just also
experience experienced ability able strong excellent good great
knowledge understanding working work role position candidate team
teams company organization opportunity responsibilities responsibility
including include required requirements preferred qualifications
qualification applicant applicants ideal successful success
""".split())

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]*")


def _tokens(text: str) -> list[str]:
    """Normalize text into searchable terms without a fixed skills vocabulary."""
    return [
        token.casefold().strip(".")
        for token in TOKEN_RE.findall(text)
        if token.casefold().strip(".") not in STOP_WORDS
        and len(token.strip(".")) > 1
    ]


def _features(text: str) -> Counter[str]:
    """Build unigram, bigram, and trigram features without crossing sentences."""
    features: Counter[str] = Counter()

    # Sentence boundaries prevent accidental phrases such as
    # "FastAPI Build" when separate sentences are concatenated.
    for segment in re.split(r"[.!?;\n]+", text):
        tokens = _tokens(segment)

        for size in (1, 2, 3):
            for start in range(len(tokens) - size + 1):
                phrase = tokens[start : start + size]
                features[" ".join(phrase)] += 1

    return features


REQUIREMENT_MARKER_RE = re.compile(
    r"\b(?:required|mandatory|essential|must|required qualifications|"
    r"minimum qualifications|must have|need to have)\b",
    re.IGNORECASE,
)


def _requirement_features(text: str) -> set[str]:
    """Extract features from sentences explicitly marked as requirements."""
    required: set[str] = set()

    for segment in re.split(r"[.!?;\n]+", text):
        if REQUIREMENT_MARKER_RE.search(segment):
            required.update(_features(segment))

    return required


def _feature_weights(features: Counter[str]) -> dict[str, float]:
    """Weight features by phrase length, independent of repetition frequency."""
    return {
        phrase: float(len(phrase.split()))
        for phrase in features
    }

def prepare_resume_features(resume_text: str) -> frozenset[str]:
    """Extract resume features once for reuse across multiple job scores."""
    return frozenset(_features(resume_text))


def score_resume_job_match(
    resume_text: str,
    *,
    title: str,
    description: str | None,
    employment_type: str | None = None,
    prepared_resume_features: frozenset[str] | None = None,
) -> dict:
    """Rank job relevance using resume evidence and weighted job fields.

    This score measures textual relevance, not hiring probability,
    verified proficiency, or eligibility to work in a country.
    """
    resume_features = (
        prepared_resume_features
        if prepared_resume_features is not None
        else frozenset(_features(resume_text))
    )
    title_features = _features(title or "")
    description_features = _features(description or "")
    requirement_features = _requirement_features(description or "")
    employment_features = _features(employment_type or "")

    # Weight job titles most heavily, descriptions next, and
    # employment type least. Keep the calculation deterministic.
    weights: dict[str, float] = {}

    for feature, weight in _feature_weights(title_features).items():
        weights[feature] = weights.get(feature, 0.0) + 3.0 * weight

    for feature, weight in _feature_weights(description_features).items():
        # Explicitly marked requirements carry more weight than incidental wording.
        multiplier = 5.0 if feature in requirement_features else 1.0
        weights[feature] = weights.get(feature, 0.0) + multiplier * weight

    for feature, weight in _feature_weights(employment_features).items():
        weights[feature] = weights.get(feature, 0.0) + 0.5 * weight

    if not weights:
        return {
            "match_score": 0,
            "matched_terms": [],
            "terms_not_found_in_resume": [],
            "match_reasons": [
                "Not enough informative text was found in the job description."
            ],
        }

    matched = sorted(
        (term for term in weights if term in resume_features),
        key=lambda term: (-weights[term], term),
    )
    unmatched = sorted(
        (term for term in weights if term not in resume_features),
        key=lambda term: (-weights[term], term),
    )

    total_weight = sum(weights.values())
    matched_weight = sum(weights[term] for term in matched)
    base_score = (
        round(100 * matched_weight / total_weight)
        if total_weight
        else 0
    )

    requirement_coverage = None
    if requirement_features:
        requirement_coverage = round(
            100
            * len(requirement_features.intersection(resume_features))
            / len(requirement_features)
        )
        # Explicit requirements and general relevance each contribute half.
        score = round(0.5 * base_score + 0.5 * requirement_coverage)
    else:
        score = base_score

    reasons = [
        f"{len(matched)} of {len(weights)} extracted text features also appear "
        "in the resume; job-title features receive additional weight."
    ]
    if requirement_coverage is not None:
        reasons.append(
            "Explicit requirement feature coverage: "
            f"{requirement_coverage}%."
        )
    if not matched:
        reasons.append(
            "No informative text features overlapped; review the documents manually."
        )

    return {
        "match_score": score,
        "matched_terms": matched[:20],
        "terms_not_found_in_resume": unmatched[:20],
        "match_reasons": reasons,
    }
