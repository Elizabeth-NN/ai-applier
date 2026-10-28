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
    """Build unigram, bigram, and trigram features from a document."""
    tokens = _tokens(text)
    features: Counter[str] = Counter()

    for size in (1, 2, 3):
        for start in range(len(tokens) - size + 1):
            phrase = tokens[start : start + size]
            features[" ".join(phrase)] += 1

    return features


def _feature_weights(features: Counter[str]) -> dict[str, float]:
    """Give longer, repeated terms more weight without a skills catalogue."""
    weights = {}
    for phrase, count in features.items():
        word_count = len(phrase.split())
        weights[phrase] = (1.0 + math.log(count)) * word_count
    return weights


def score_resume_job_match(
    resume_text: str,
    *,
    title: str,
    description: str | None,
    employment_type: str | None = None,
) -> dict:
    """Compare resume text with a job and explain the textual overlap.

    The score measures weighted text-feature coverage, not hiring probability,
    verified skill proficiency, or eligibility to work from a country.
    """
    job_text = " ".join(
        part for part in (title, description or "", employment_type or "") if part
    )

    resume_features = _features(resume_text)
    job_features = _features(job_text)

    if not job_features:
        return {
            "match_score": 0,
            "matched_terms": [],
            "terms_not_found_in_resume": [],
            "match_reasons": [
                "Not enough informative text was found in the job description."
            ],
        }

    job_weights = _feature_weights(job_features)
    resume_terms = set(resume_features)

    # Rank terms by their contribution to the job text. Keep the output
    # concise while calculating coverage across every extracted feature.
    matched = sorted(
        (term for term in job_features if term in resume_terms),
        key=lambda term: (-job_weights[term], term),
    )
    unmatched = sorted(
        (term for term in job_features if term not in resume_terms),
        key=lambda term: (-job_weights[term], term),
    )

    total_weight = sum(job_weights.values())
    matched_weight = sum(job_weights[term] for term in matched)
    score = round(100 * matched_weight / total_weight) if total_weight else 0

    reasons = [
        f"{len(matched)} of {len(job_features)} extracted text features also appear in the resume."
    ]
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
