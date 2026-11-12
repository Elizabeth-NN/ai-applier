from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import resumes as resumes_api
from app.models.candidate_profile import CandidateProfile
from app.models.job import Job
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
def prepare_durable_screening_context(
    db: Session,
    *,
    user_id: str,
    resume_id: int,
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

    stored_path = resumes_api._resolve_stored_path(resume)
    resume_text = extract_resume_text(
        stored_path,
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

    max_job_id = db.scalar(select(func.max(Job.id))) or 0

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

    term_weights = build_term_weights(job_documents())

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
