from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import resumes as resumes_api
from app.services import resume_storage
from app.models.candidate_profile import CandidateProfile
from app.models.job import Job
from app.models.job_matching_corpus_state import JobMatchingCorpusState
from app.models.resume import Resume
from app.services.resume_text import extract_resume_text
from app.services.structured_resume_parser import parse_resume_text
from app.services.resume_job_matching import (
    PROFILE_EVIDENCE_SECTIONS,
    build_requirement_term_evidence,
    build_term_weights,
    classify_match_terms,
    prepare_candidate_profile_section_features,
    prepare_job_matching_text,
    prepare_resume_features,
    prepare_resume_section_features,
    score_resume_job_match,
)
from app.schemas.job import JobRead

def prepare_durable_screening_context(
    db: Session,
    *,
    user_id: str,
    resume_id: int,
    max_job_id: int | None = None,
) -> dict[str, Any]:
    """Prepare shared resume and corpus data for durable job screening."""

    resume = db.scalar(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == user_id,
        )
    )
    if resume is None:
        raise ValueError("Resume not found or does not belong to this user.")

    try:
        resume_bytes = resume_storage.read_resume(
            resume.storage_key,
            local_dir=resumes_api.STORAGE_DIR,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("Stored resume file not found.") from exc
    except OSError as exc:
        raise ValueError("Stored resume file could not be read.") from exc

    resume_text = extract_resume_text(
        resume_bytes,
        resume.original_filename,
    )

    prepared_resume_features = prepare_resume_features(resume_text)

    structured_resume = parse_resume_text(resume_text)
    resume_section_features = prepare_resume_section_features(
        structured_resume
    )

    candidate_profile = db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id,
        )
    )

    profile_data: dict[str, Any] = {}
    if candidate_profile is not None:
        profile_data = {
            "headline": candidate_profile.headline,
            "professional_summary": candidate_profile.professional_summary,
            "skills": candidate_profile.skills or [],
            "experience": candidate_profile.experience or [],
            "projects": candidate_profile.projects or [],
            "education": candidate_profile.education or [],
            "certifications": candidate_profile.certifications or [],
        }

    profile_section_features = prepare_candidate_profile_section_features(
        profile_data
    )
    profile_features = frozenset().union(
        *profile_section_features.values()
    )
    combined_features = prepared_resume_features | profile_features

    has_profile_evidence = bool(profile_features)

    if max_job_id is None:
        max_job_id = db.scalar(select(func.max(Job.id))) or 0
    elif (
        isinstance(max_job_id, bool)
        or not isinstance(max_job_id, int)
        or max_job_id < 0
    ):
        raise ValueError("max_job_id must be a non-negative integer.")

    expected_total = db.scalar(
        select(func.count(Job.id)).where(Job.id <= max_job_id)
    ) or 0

    def job_documents() -> Iterator[str]:
        statement = (
            select(Job.title, Job.description, Job.company)
            .where(Job.id <= max_job_id)
            .order_by(Job.id.asc())
            .execution_options(stream_results=True)
        )

        rows = db.execute(statement).yield_per(500)

        for title, description, company in rows:
            yield prepare_job_matching_text(
                title,
                description,
                company,
            )

    corpus_state = db.execute(
        select(
            JobMatchingCorpusState.revision,
            JobMatchingCorpusState.term_weights,
        ).where(JobMatchingCorpusState.id == 1)
    ).one_or_none()

    if corpus_state is None:
        raise RuntimeError("Job matching corpus state is not initialized.")

    corpus_revision, cached_weights = corpus_state
    cached_entry = cached_weights or {}

    if (
        cached_entry.get("revision") == corpus_revision
        and cached_entry.get("max_job_id") == max_job_id
        and isinstance(cached_entry.get("weights"), dict)
    ):
        term_weights = cached_entry["weights"]
    else:
        term_weights = build_term_weights(job_documents())

        state_to_update = db.scalar(
            select(JobMatchingCorpusState)
            .where(JobMatchingCorpusState.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current_max_job_id = db.scalar(select(func.max(Job.id))) or 0

        if state_to_update is None:
            raise RuntimeError("Job matching corpus state disappeared.")

        # Do not cache weights if the corpus changed during preparation.
        if (
            state_to_update.revision == corpus_revision
            and current_max_job_id == max_job_id
        ):
            state_to_update.term_weights = {
                "revision": corpus_revision,
                "max_job_id": max_job_id,
                "weights": term_weights,
            }
            db.commit()
        else:
            db.rollback()

    return {
        "resume_id": resume_id,
        "max_job_id": max_job_id,
        "expected_total": expected_total,
        "resume_features": prepared_resume_features,
        "resume_section_features": resume_section_features,
        "profile_data": profile_data,
        "profile_section_features": profile_section_features,
        "profile_features": profile_features,
        "combined_features": combined_features,
        "has_profile_evidence": has_profile_evidence,
        "term_weights": term_weights,
    }

def score_durable_screening_batch(
    db: Session,
    *,
    context: Mapping[str, Any],
    last_job_id: int = 0,
    batch_size: int = 100,
) -> list[dict[str, Any]]:
    """Score the next batch using shared corpus-wide matching weights."""

    statement = (
        select(Job)
        .where(
            Job.id > last_job_id,
            Job.id <= context["max_job_id"],
        )
        .order_by(Job.id.asc())
        .limit(batch_size)
    )

    jobs = db.scalars(statement).all()
    scored_items: list[dict[str, Any]] = []

    for job in jobs:
        match = score_resume_job_match(
            "",
            title=job.title,
            description=job.description,
            company=job.company,
            prepared_resume_features=context["resume_features"],
            term_weights=context["term_weights"],
        )

        match["term_evidence"] = build_requirement_term_evidence(
            job.description,
            context["resume_section_features"],
            company=job.company,
        )

        if context["has_profile_evidence"]:
            profile_match = score_resume_job_match(
                "",
                title=job.title,
                description=job.description,
                company=job.company,
                prepared_resume_features=context["combined_features"],
                term_weights=context["term_weights"],
            )

            matched_terms = profile_match.get("matched_terms", [])
            required_terms = profile_match.get(
                "required_terms_found",
                [],
            )
            preferred_terms = profile_match.get(
                "preferred_terms_found",
                [],
            )

            profile_matched_terms = classify_match_terms(
                matched_terms,
                context["resume_features"],
                context["profile_features"],
            )
            required_classification = classify_match_terms(
                required_terms,
                context["resume_features"],
                context["profile_features"],
            )
            preferred_classification = classify_match_terms(
                preferred_terms,
                context["resume_features"],
                context["profile_features"],
            )

            match.update(
                {
                    "profile_match_score": profile_match["match_score"],
                    "profile_matched_terms":profile_matched_terms["profile"],
                    "profile_only_matched_terms": profile_matched_terms["profile_only"],
                    "terms_not_found_in_resume_or_profile": (
                        profile_match["terms_not_found_in_resume"]
                    ),
                    "required_terms_found_in_profile": (
                        required_classification["profile"]
                    ),
                    "required_terms_found_in_resume_or_profile": (
                        required_terms
                    ),
                    "required_terms_not_found_in_resume_or_profile": (
                        profile_match["required_terms_not_found"]
                    ),
                    "preferred_terms_found_in_profile": (
                        preferred_classification["profile"]
                    ),
                    "preferred_terms_found_in_resume_or_profile": (
                        preferred_terms
                    ),
                    "preferred_terms_not_found_in_resume_or_profile": (
                        profile_match["preferred_terms_not_found"]
                    ),
                    "profile_term_evidence": build_requirement_term_evidence(
                        job.description,
                        context["profile_section_features"],
                        company=job.company,
                        section_names=PROFILE_EVIDENCE_SECTIONS,
                    ),
                    "profile_match_reasons": profile_match["match_reasons"],
                }
            )


        job_data = JobRead.model_validate(job).model_dump(mode="json")

        scored_items.append(
            {
                **job_data,
                **match,
            }
        )

    return scored_items
