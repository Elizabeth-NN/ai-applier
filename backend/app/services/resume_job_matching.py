"""Dynamic, explainable text matching for resumes and job descriptions.

Scores textual relevance, not hiring probability, verified proficiency,
or eligibility to work in a country.

How scoring works
-----------------
* Text is reduced to informative terms (single words) and phrases.
* Terms are matched through a *match key* so that ``develop`` / ``developer`` /
  ``development`` or ``engineer`` / ``engineering`` count as the same evidence.
  Displayed terms are always real words, never stems.
* Optionally, terms are weighted by how distinctive they are across the whole
  job corpus (inverse document frequency; see ``build_term_weights``). Generic
  words such as "apply" or "based" then count for little, while "fastapi" or
  "kubernetes" count for a lot.
* Short titles or descriptions give little evidence, so their contribution is
  scaled down instead of letting one matched word score 100%.
"""

from __future__ import annotations

import html
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache


STOP_WORDS = frozenset("""
a an the and or but if then than so because as at by for from in into
of on onto to with without within about above across after against along
among around before behind below beneath beside between beyond during
except inside near off out outside over through throughout under until
up upon via per is am are was were be been being do does did doing
have has had having can could may might must shall should will would
i me my we our us you your he she it they them their this that these those
who whom which what where when why how all any both each few more most
other some such no not only own same too very just also using used use
experience experienced ability able strong excellent good great
knowledge understanding working work role position candidate team teams
company organization opportunity responsibilities responsibility
including include required requirements preferred qualifications
qualification applicant applicants ideal successful success
mandatory essential minimum need needs needed requirement
amp br nbsp div span etc
""".split())

# These words can appear in many unrelated job descriptions. They are
# excluded from scoring evidence so generic overlap does not dominate.
LOW_VALUE_TERMS = frozenset("""
basic current information skills skill building build developed develop
community contribution contributions professional various different
multiple relevant related effective effectively support supporting
assist assisting including provide providing ensure ensuring
apply applying based built create creating created deliver delivering
bring clear enable address adapt additionally additional alongside
genuinely allow allowing developing designed improve improving
""".split())

MAX_EXPLANATION_TERMS = 20
EXPLANATION_PHRASE_SLOTS = 5

# Term weighting and evidence confidence.
MIN_TERM_WEIGHT = 0.05
MIN_EXPLANATION_WEIGHT = 0.8  # Generic terms below this are not listed.
TITLE_FULL_CONFIDENCE_TERMS = 5
DESCRIPTION_FULL_CONFIDENCE_TERMS = 6
REQUIREMENT_FULL_CONFIDENCE_TERMS = 3
_UNSEEN_TERM_KEY = ""  # Weight used for terms the corpus never saw.
# With no usable description, the title is the only evidence, so cap its pull.
TITLE_ONLY_SCORE_FACTOR = 0.6

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]*")

# --- Term normalization -----------------------------------------------------
# Terms are reduced to a canonical form on both the resume and the job side,
# so "APIs"/"API" and "NodeJS"/"Node.js" match. Canonical forms are real,
# readable words (singulars or well-known names), so explanations stay clear.

# Multi-word spellings rewritten before tokenizing.
TEXT_ALIASES = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        (r"\bnode\s+js\b", "nodejs"),
        (r"\breact\s+js\b", "reactjs"),
        (r"\bvue\s+js\b", "vuejs"),
        (r"\bnext\s+js\b", "nextjs"),
        (r"\bc\s+sharp\b", "csharp"),
        (r"\bc\s+plus\s+plus\b", "cpp"),
    )
)

# Single-token spellings mapped to one canonical name.
TOKEN_ALIASES = {
    "nodejs": "node.js",
    "node.js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "angularjs": "angular",
    "angular.js": "angular",
    "nextjs": "next.js",
    "next.js": "next.js",
    "expressjs": "express",
    "express.js": "express",
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "golang": "go",
    "postgres": "postgresql",
    "psql": "postgresql",
    "mongo": "mongodb",
    "dotnet": "net",
    "csharp": "c#",
    "cpp": "c++",
}

# Words that end in "s" but are not plurals (or whose singular would read
# badly), so they are left untouched.
PLURAL_EXCEPTIONS = frozenset("""
kubernetes postgres jenkins pandas windows devops https series species
analytics statistics mathematics physics economics logistics ethics
genetics news canvas alias bias gas lens atlas
analysis axis redis basis emphasis diagnosis thesis hypothesis synopsis
macos nagios cosmos chaos
""".split())
PLURAL_OVERRIDES = {"caches": "cache"}

# Suffixes removed only to build the internal *match key* (never displayed),
# so related word forms count as the same evidence.
KEY_SUFFIXES = ("ments", "ment", "ing", "ed", "er", "ant", "ly", "ions", "ion")

# Single-letter skills (the C and R languages). Only an uppercase letter is
# accepted, and only when it clearly stands alone (see _is_standalone_skill),
# so "R&D", "Vitamin C" or "C-level" do not count.
SINGLE_LETTER_SKILLS = frozenset("CR")
NON_SKILL_PRECEDING_WORDS = frozenset(
    "vitamin series plan option class grade type level route hepatitis".split()
)
NON_SKILL_NEIGHBORS = frozenset("&'\u2019")

# Phrase boundaries. A period only counts as a boundary when it ends a
# sentence (followed by whitespace or end of text), so "Node.js" is never
# split into "node" and "js".
SEGMENT_RE = re.compile(r"[,/;:!?|()\[\]{}\n\r\u2022\u25aa\u25e6\u2013\u2014]+|\.(?=\s|$)")

# Sentence boundaries for requirement detection. Commas are intentionally
# not boundaries so "Required: Python, SQL, Docker" stays together.
SENTENCE_RE = re.compile(r"[;!?]+|\.(?=\s|$)")

BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u2013\u2014\u25aa\u25e6]|\d+[.)])\s+")

# Inline markers: the whole sentence is treated as a requirement.
REQUIREMENT_MARKER_RE = re.compile(
    r"\b(?:required|mandatory|essential|must|need\s+to\s+have|"
    r"minimum\s+(?:qualifications|requirements))\b",
    re.IGNORECASE,
)

# Section headers such as "Requirements:" or "Minimum qualifications:" mark
# every following line (until a blank line or a new header) as required.
HEADER_REQUIREMENT_RE = re.compile(
    r"\b(?:required|mandatory|essential|must|need\s+to\s+have|minimum|"
    r"requirements?|qualifications?)\b",
    re.IGNORECASE,
)

# Anything that explicitly softens a requirement wins over a marker, so
# "not required" or "preferred qualifications" never count as required.
OPTIONAL_MARKER_RE = re.compile(
    r"\b(?:not\s+(?:required|necessary|mandatory|essential)|"
    r"nice[\s-]to[\s-]have|preferred|desired|optional|bonus|"
    r"a\s+plus|advantageous)\b",
    re.IGNORECASE,
)

# Positive wording that explicitly identifies a preferred qualification.
# Kept separate from OPTIONAL_MARKER_RE so "not required" is not preferred.
PREFERRED_MARKER_RE = re.compile(
    r"\b(?:nice[\s-]to[\s-]have|preferred|desired|optional|bonus|"
    r"a\s+plus|advantageous)\b",
    re.IGNORECASE,
)


# --- Text cleaning ----------------------------------------------------------

BLOCK_TAG_RE = re.compile(r"</?(?:br|p|li|ul|ol|div|h[1-6]|tr)\b[^>]*>", re.IGNORECASE)
TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
NEGATED_CONTRACTION_RE = re.compile(r"\b\w+n['\u2019]t\b", re.IGNORECASE)
CONTRACTION_SUFFIX_RE = re.compile(r"['\u2019](?:s|re|ve|ll|d|m)\b", re.IGNORECASE)


def _clean_text(text: str) -> str:
    """Remove HTML and contraction debris that would otherwise become terms.

    Without this, "&amp;" yields the term "amp", "<br>" yields "br" and
    "don't" yields "don".
    """
    text = html.unescape(text)
    # Block-level tags become one line break; runs such as "</p><ul><li>"
    # collapse to a single break so they never look like a blank line (which
    # would end a "Requirements:" block).
    text = BLOCK_TAG_RE.sub("\x00", text)
    text = re.sub(r"\x00+", "\n", text)
    text = TAG_RE.sub(" ", text)
    text = NEGATED_CONTRACTION_RE.sub(" ", text)
    return CONTRACTION_SUFFIX_RE.sub("", text)


# --- Tokenization -----------------------------------------------------------

def _singularize(token: str) -> str:
    """Conservatively strip plural endings from plain alphabetic words."""
    if len(token) <= 3 or not token.isalpha() or token in PLURAL_EXCEPTIONS:
        return token
    if token in PLURAL_OVERRIDES:
        return PLURAL_OVERRIDES[token]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses") or token.endswith(("xes", "ches", "shes", "zzes")):
        return token[:-2]
    if token.endswith(("ss", "us")):
        return token
    if token.endswith("s"):
        return token[:-1]
    return token


def _canonical(token: str) -> str:
    """Map a lowercase token to its canonical alias or singular form."""
    alias = TOKEN_ALIASES.get(token)
    if alias is not None:
        return alias
    return _singularize(token)


@lru_cache(maxsize=100_000)
def _match_key(token: str) -> str:
    """Return the internal key used to compare related word forms.

    "developer", "development" and "developed" all share one key, as do
    "engineer" and "engineering". Keys are used for matching only; they are
    never shown to the user.
    """
    if not token.isalpha():
        return token  # node.js, c++, c# ...

    key = token
    stripped = False
    for _ in range(2):
        for suffix in KEY_SUFFIXES:
            if key.endswith(suffix) and len(key) - len(suffix) >= 4:
                key = key[: -len(suffix)]
                stripped = True
                break
        else:
            break

    # "logging" -> "logg" -> "log", but keep "ll", "ss" and "zz" endings.
    if stripped and len(key) >= 4 and key[-1] == key[-2] and key[-1] not in "lsz":
        key = key[:-1]
    if len(key) > 4 and key.endswith("e"):
        key = key[:-1]
    return key


@lru_cache(maxsize=100_000)
def _term_key(term: str) -> str:
    """Match key for a single term or a space-separated phrase."""
    return " ".join(_match_key(word) for word in term.split())


def _is_standalone_skill(text: str, match: re.Match) -> bool:
    """Decide whether a lone 'C' or 'R' is a skill rather than noise."""
    start, end = match.span()
    before, after = text[:start], text[end:]

    if before[-1:] in NON_SKILL_NEIGHBORS or after[:1] in NON_SKILL_NEIGHBORS:
        return False
    # "R&D", "R & D", "D&R"
    if before.rstrip().endswith("&") or after.lstrip().startswith("&"):
        return False
    # "C-level", "C-suite"
    if after[:1] == "-" and after[1:2].isalpha():
        return False
    if before[-1:] == "-" and before[-2:-1].isalpha():
        return False
    # "Vitamin C", "Series C", "Plan C"
    words = before.split()
    if words and words[-1].casefold().strip(":,.;") in NON_SKILL_PRECEDING_WORDS:
        return False
    return True


def _raw_tokens(text: str) -> list[str]:
    """Normalize tokens while retaining stop words for phrase boundaries.

    Stop words are kept in their original form so they are still recognized;
    every other token is reduced to its canonical alias or singular form.
    """
    for pattern, replacement in TEXT_ALIASES:
        text = pattern.sub(replacement, text)

    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text):
        raw = match.group().strip(".")
        if raw == "IT":
            # Uppercase "IT" is the department/field, not the pronoun "it".
            tokens.append("IT")
        elif len(raw) > 1:
            token = raw.casefold()
            if token not in STOP_WORDS and token not in LOW_VALUE_TERMS:
                token = _canonical(token)
            tokens.append(token)
        elif raw in SINGLE_LETTER_SKILLS and _is_standalone_skill(text, match):
            tokens.append(raw.casefold())
    return tokens


def _tokens(text: str) -> set[str]:
    """Return distinct informative terms from the supplied text."""
    return {
        token
        for token in _raw_tokens(_clean_text(text))
        if token not in STOP_WORDS and token not in LOW_VALUE_TERMS
    }


def _phrases(text: str) -> set[str]:
    """Extract contiguous two- and three-word phrases without crossing punctuation."""
    phrases: set[str] = set()

    for segment in SEGMENT_RE.split(_clean_text(text)):
        words = _raw_tokens(segment)

        for size in (2, 3):
            for start in range(len(words) - size + 1):
                phrase_words = words[start : start + size]

                # Do not manufacture phrases by joining words separated by
                # stop words, or award evidence for generic filler phrases.
                if any(
                    word in STOP_WORDS or word in LOW_VALUE_TERMS
                    for word in phrase_words
                ):
                    continue

                phrases.add(" ".join(phrase_words))

    return phrases


def _evidence(text: str) -> tuple[set[str], set[str]]:
    """Return distinct informative terms and phrases."""
    return _tokens(text), _phrases(text)


# --- Requirements -----------------------------------------------------------

def _is_section_header(line: str) -> bool:
    """Detect short header lines such as 'Requirements:' or '## Qualifications'."""
    if BULLET_RE.match(line):
        return False
    cleaned = line.strip("#*_ \t")
    looks_like_header = line.startswith("#") or cleaned.endswith(":")
    return looks_like_header and len(_raw_tokens(cleaned)) <= 8


def _requirement_classifications(
    text: str,
) -> tuple[set[str], set[str]]:
    """Extract explicitly required and preferred terms from job text.

    Supports requirement/preference section headers, bullet lists, and inline
    wording. Contrasting clauses are separated so a preferred term does not
    cancel a required term elsewhere in the same sentence.
    """
    required: set[str] = set()
    preferred: set[str] = set()
    section: str | None = None

    for line in _clean_text(text).splitlines():
        stripped = line.strip()

        if not stripped:
            section = None
            continue

        if _is_section_header(stripped):
            if PREFERRED_MARKER_RE.search(stripped):
                section = "preferred"
            elif (
                HEADER_REQUIREMENT_RE.search(stripped)
                and not OPTIONAL_MARKER_RE.search(stripped)
            ):
                section = "required"
            else:
                section = None
            continue

        if section == "required":
            required.update(_tokens(stripped))
            continue

        if section == "preferred":
            preferred.update(_tokens(stripped))
            continue

        for sentence in SENTENCE_RE.split(stripped):
            # Keep comma-separated skill lists together, but separate
            # contrasting clauses such as "Python is required, while
            # Docker is preferred."
            clauses = re.split(
                r",?\s+(?=(?:while|whereas|but)\b)",
                sentence,
                flags=re.IGNORECASE,
            )

            for clause in clauses:
                has_preferred_marker = bool(
                    PREFERRED_MARKER_RE.search(clause)
                )
                has_optional_marker = bool(
                    OPTIONAL_MARKER_RE.search(clause)
                )

                if has_preferred_marker:
                    preferred.update(_tokens(clause))
                elif (
                    REQUIREMENT_MARKER_RE.search(clause)
                    and not has_optional_marker
                ):
                    required.update(_tokens(clause))

    # A term explicitly classified both ways is ambiguous. Do not count it
    # as a definite requirement or preference.
    overlap = required & preferred
    required.difference_update(overlap)
    preferred.difference_update(overlap)

    return required, preferred


def _requirement_terms(text: str) -> set[str]:
    """Backward-compatible access to explicitly required terms."""
    required, _ = _requirement_classifications(text)
    return required


# --- Resume preparation and corpus weights ----------------------------------

def prepare_resume_features(resume_text: str) -> frozenset[str]:
    """Extract resume match keys once for reuse across job scores.

    Keys for single terms never contain whitespace and keys for phrases always
    do, so both live safely in one frozenset.
    """
    tokens, phrases = _evidence(resume_text or "")
    return frozenset(_term_key(term) for term in tokens | phrases)


def build_term_weights(documents: Iterable[str]) -> dict[str, float]:
    """Weight terms by how distinctive they are across a corpus of job texts.

    Pass one string per job (for example ``f"{title}\\n{description}"``) once
    per matching run and reuse the result for every job. Terms found in nearly
    every job get a weight close to zero; rare terms get a high weight.
    """
    document_count = 0
    document_frequency: Counter[str] = Counter()

    for document in documents:
        document_count += 1
        document_frequency.update(_match_key(token) for token in _tokens(document or ""))

    if document_count == 0:
        return {}

    weights = {
        key: max(MIN_TERM_WEIGHT, math.log((document_count + 1) / (frequency + 1)))
        for key, frequency in document_frequency.items()
    }
    # Terms the corpus never saw are treated as maximally distinctive.
    weights[_UNSEEN_TERM_KEY] = math.log(document_count + 1)
    return weights


def _make_weigher(term_weights: Mapping[str, float] | None):
    """Return a function that weights a term or phrase (mean of its words)."""
    if not term_weights:
        return lambda term: 1.0

    unseen = term_weights.get(_UNSEEN_TERM_KEY, 1.0)

    def weigh(term: str) -> float:
        words = term.split()
        total = sum(term_weights.get(_match_key(word), unseen) for word in words)
        return max(MIN_TERM_WEIGHT, total / len(words))

    return weigh


# --- Scoring ----------------------------------------------------------------

def _coverage(targets: Iterable[str], resume_keys, weigh) -> float | None:
    """Return weighted target coverage from 0 to 100, or None if no evidence exists.

    Related word forms in the target (develop/developer/development) are
    counted once.
    """
    by_key: dict[str, str] = {}
    for term in sorted(targets):
        by_key.setdefault(_term_key(term), term)

    if not by_key:
        return None

    total = sum(weigh(term) for term in by_key.values())
    found = sum(weigh(term) for key, term in by_key.items() if key in resume_keys)
    return 100.0 * found / total


def _combined_coverage(
    token_targets: set[str],
    phrase_targets: set[str],
    resume_keys,
    weigh,
) -> float | None:
    """Combine token and phrase coverage without counting all n-grams equally."""
    token_coverage = _coverage(token_targets, resume_keys, weigh)
    phrase_coverage = _coverage(phrase_targets, resume_keys, weigh)

    if token_coverage is None and phrase_coverage is None:
        return None
    if token_coverage is None:
        return phrase_coverage
    if phrase_coverage is None:
        return token_coverage

    # Distinct terms carry most of the weight; exact phrases add useful context.
    return 0.75 * token_coverage + 0.25 * phrase_coverage


def _confidence(term_count: int, full_confidence_terms: int) -> float:
    """Scale down evidence from very short titles or descriptions.

    Never below 0.5: a short but accurate description is still real evidence,
    it just should not count as much as a detailed one.
    """
    return 0.5 + 0.5 * min(1.0, term_count / full_confidence_terms)


def _limit_terms(
    tokens: list[str],
    phrases: list[str],
    limit: int = MAX_EXPLANATION_TERMS,
) -> list[str]:
    """Cap explanation terms while always leaving room for some phrases."""
    phrase_quota = min(len(phrases), max(EXPLANATION_PHRASE_SLOTS, limit - len(tokens)))
    token_quota = limit - phrase_quota
    return tokens[:token_quota] + phrases[:phrase_quota]


RESUME_EVIDENCE_SECTIONS = (
    "skills",
    "experience",
    "projects",
    "summary",
    "education",
    "certifications",
)


def prepare_resume_section_features(
    structured_resume: Mapping[str, object],
) -> dict[str, frozenset[str]]:
    """Prepare normalized matching features for each useful resume section."""
    section_features = {}

    for section in RESUME_EVIDENCE_SECTIONS:
        entries = structured_resume.get(section, [])
        section_text = "\\n".join(
            str(entry.get("text", ""))
            for entry in entries
            if isinstance(entry, Mapping)
        )
        section_features[section] = prepare_resume_features(section_text)

    return section_features


def build_requirement_term_evidence(
    description: str | None,
    section_features: Mapping[str, frozenset[str]],
) -> dict[str, list[str]]:
    """Show which resume sections contain each required or preferred term."""
    required_terms, preferred_terms = _requirement_classifications(
        description or ""
    )

    evidence = {}

    for term in sorted(required_terms | preferred_terms):
        term_key = _term_key(term)
        evidence[term] = [
            section
            for section in RESUME_EVIDENCE_SECTIONS
            if term_key in section_features.get(section, frozenset())
        ]

    return evidence


def score_resume_job_match(
    resume_text: str,
    *,
    title: str,
    description: str | None,
    employment_type: str | None = None,  # Accepted for API compatibility; not scored.
    prepared_resume_features: frozenset[str] | None = None,
    term_weights: Mapping[str, float] | None = None,
) -> dict:
    """Score textual relevance using title, description, and explicit requirements.

    ``prepared_resume_features`` (from ``prepare_resume_features``) avoids
    re-reading the resume for every job; ``resume_text`` is ignored then.
    ``term_weights`` (from ``build_term_weights``) makes distinctive terms count
    more than generic ones. Both are optional.
    """
    if prepared_resume_features is None:
        resume_keys = prepare_resume_features(resume_text)
    else:
        resume_keys = prepared_resume_features

    weigh = _make_weigher(term_weights)

    title_tokens, title_phrases = _evidence(title or "")
    description_tokens, description_phrases = _evidence(description or "")

    required_terms, preferred_terms = _requirement_classifications(
        description or ""
    )
    requirement_tokens = required_terms

    def classify_resume_evidence(terms: set[str]) -> tuple[list[str], list[str]]:
        found = sorted(
            term for term in terms if _term_key(term) in resume_keys
        )
        not_found = sorted(terms - set(found))
        return found, not_found

    required_terms_found, required_terms_not_found = (
        classify_resume_evidence(required_terms)
    )
    preferred_terms_found, preferred_terms_not_found = (
        classify_resume_evidence(preferred_terms)
    )

    title_score = _combined_coverage(title_tokens, title_phrases, resume_keys, weigh)
    description_score = _combined_coverage(
        description_tokens, description_phrases, resume_keys, weigh
    )
    requirement_score = _coverage(requirement_tokens, resume_keys, weigh)

    title_confidence = _confidence(len(title_tokens), TITLE_FULL_CONFIDENCE_TERMS)
    description_confidence = _confidence(
        len(description_tokens), DESCRIPTION_FULL_CONFIDENCE_TERMS
    )
    requirement_confidence = _confidence(
        len(requirement_tokens), REQUIREMENT_FULL_CONFIDENCE_TERMS
    )

    # Titles are useful signals, but should not dominate weak description matches.
    # Explicit requirements remain important when the job description contains them.
    # Each value is scaled by how much evidence stands behind it.
    components: list[tuple[float, float]] = []
    if title_score is not None:
        components.append((0.45, title_score * title_confidence))
    if description_score is not None:
        components.append((0.30, description_score * description_confidence))
    if requirement_score is not None:
        components.append((0.25, requirement_score * requirement_confidence))
    if not components:
        return {
            "match_score": 0,
            "matched_terms": [],
            "terms_not_found_in_resume": [],
            "required_terms_found": required_terms_found,
            "required_terms_not_found": required_terms_not_found,
            "preferred_terms_found": preferred_terms_found,
            "preferred_terms_not_found": preferred_terms_not_found,
            "match_reasons": [
                "Not enough informative text was found in the job title or description."
            ],
        }

    total_weight = sum(weight for weight, _ in components)
    score = round(
        sum(weight * value for weight, value in components) / total_weight
    )

    title_only = title_score is not None and description_score is None
    if title_only:
        score = round(score * TITLE_ONLY_SCORE_FACTOR)

    # --- Explanations: most important evidence first, one entry per word family.
    requirement_keys = {_match_key(term) for term in requirement_tokens}
    title_keys = {_match_key(term) for term in title_tokens}

    def rank(term: str) -> tuple[int, float, bool, str]:
        word_keys = [_match_key(word) for word in term.split()]
        if any(key in requirement_keys for key in word_keys):
            tier = 0
        elif any(key in title_keys for key in word_keys):
            tier = 1
        else:
            tier = 2
        return (tier, -weigh(term), term not in title_tokens, term)

    def worth_listing(term: str) -> bool:
        if not term_weights:
            return True
        return rank(term)[0] < 2 or weigh(term) >= MIN_EXPLANATION_WEIGHT

    def present(terms: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for term in sorted(terms, key=rank):
            key = _term_key(term)
            if key in seen or not worth_listing(term):
                continue
            seen.add(key)
            ordered.append(term)
        return ordered

    job_tokens = title_tokens | description_tokens
    job_phrases = title_phrases | description_phrases

    matched_tokens = [t for t in job_tokens if _term_key(t) in resume_keys]
    missing_tokens = [t for t in job_tokens if _term_key(t) not in resume_keys]
    matched_phrases = [p for p in job_phrases if _term_key(p) in resume_keys]

    # A missing phrase made only of missing words adds nothing the missing
    # words do not already say, so only keep phrases with partial evidence.
    missing_word_keys = {_match_key(token) for token in missing_tokens}
    missing_phrases = [
        phrase
        for phrase in job_phrases
        if _term_key(phrase) not in resume_keys
        and not all(_match_key(word) in missing_word_keys for word in phrase.split())
    ]

    matched_terms = _limit_terms(present(matched_tokens), present(matched_phrases))
    missing_terms = _limit_terms(present(missing_tokens), present(missing_phrases))

    reasons = [
        f"Textual relevance score: {score}/100, based on distinct title, "
        "description, and explicit-requirement evidence."
    ]
    if title_score is not None:
        reasons.append(f"Job-title term and phrase coverage: {round(title_score)}%.")
    if description_score is not None:
        reasons.append(
            f"Description term and phrase coverage: {round(description_score)}%."
        )
    if requirement_score is not None:
        reasons.append(
            f"Explicit requirement term coverage: {round(requirement_score)}%."
        )
    if (
        (title_score is not None and title_confidence < 1)
        or (description_score is not None and description_confidence < 1)
        or (requirement_score is not None and requirement_confidence < 1)
    ):
        reasons.append(
            "Some sections contain few distinctive terms, so their weight in "
            "the score was reduced."
        )
    if title_only:
        reasons.append(
            "No usable job description text was available, so the score "
            "reflects the job title only and is capped."
        )
    if not matched_tokens and not matched_phrases:
        reasons.append(
            "No informative text evidence overlapped; review the documents manually."
        )

    return {
        "match_score": max(0, min(100, score)),
        "matched_terms": matched_terms,
        "terms_not_found_in_resume": missing_terms,
        "required_terms_found": required_terms_found,
        "required_terms_not_found": required_terms_not_found,
        "preferred_terms_found": preferred_terms_found,
        "preferred_terms_not_found": preferred_terms_not_found,
        "match_reasons": reasons,
    }


def score_resume_against_jobs(
    resume_text: str,
    jobs: Iterable[tuple[str, str | None]],
) -> list[dict]:
    """Score one resume against many jobs, with corpus weighting applied.

    ``jobs`` is an iterable of ``(title, description)`` pairs; results are
    returned in the same order. This builds the term weights and prepares the
    resume exactly once, which is the recommended way to run a full matching
    pass (without weights, generic words such as "apply" or "based" count as
    evidence).
    """
    job_list: Sequence[tuple[str, str | None]] = list(jobs)
    term_weights = build_term_weights(
        f"{title or ''}\n{description or ''}" for title, description in job_list
    )
    features = prepare_resume_features(resume_text)

    return [
        score_resume_job_match(
            "",
            title=title,
            description=description,
            prepared_resume_features=features,
            term_weights=term_weights,
        )
        for title, description in job_list
    ]
