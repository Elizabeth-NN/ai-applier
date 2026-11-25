import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pathlib import Path
from sqlalchemy import func, literal, or_, select

from app.models import (
    AutomationRun,
    AutomationScreeningResult,
    AutomationTask,
    HimalayasIngestionState,
    Resume,
)
from sqlalchemy.orm import Session

from app.core.auth import CurrentAdmin, CurrentUser
from app.api import resumes as resumes_api
from app.services import resume_storage
from app.db.dependencies import get_db
from app.models.candidate_profile import CandidateProfile
from app.models.job import Job
from app.services.job_matching_corpus import mark_job_matching_corpus_changed
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
from app.schemas.job import (
    ApplicationUrlUpdate,
    EligibilityVerificationRequest,
    JobCreate,
    JobRead,
    JobSearchResult,
    ResumeJobMatchResult,
    JobScreeningResult,
    JobScreeningItem,
    JobScreeningRunStatus,
    JobScreeningResultsPage,
    JobScreeningStartRequest,
    JobScreeningStartResponse,
)
from app.schemas.himalayas_ingestion import HimalayasBatchIngestionResult
from app.services.job_ingestion import (
    ingest_himalayas_jobs,
    ingest_jobicy_jobs,
)
from app.services.himalayas_adapter import HimalayasAPIError
from app.services.jobicy_adapter import JobicyAPIError
from app.services.job_status_sync import sync_jobicy_statuses
from app.services.job_relevance import (
    classify_experience_level,
    score_job_relevance,
)
from app.services.job_screening import screen_job


router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

# Term weights describe how distinctive each word is across the whole job
# corpus, so they do not depend on the resume. Building them tokenizes every
# job description, so they are cached briefly and rebuilt when the corpus
# changes (job count or newest job) or the cache expires.
_TERM_WEIGHT_TTL_SECONDS = 600
_term_weight_cache: dict = {"key": None, "expires_at": 0.0, "weights": {}}
_term_weight_lock = threading.Lock()

# Completed match results are user-specific and more expensive to rebuild.
# Keep this cache small and short-lived; screening metadata is never cached.
_MATCH_RESULT_TTL_SECONDS = 300
_MATCH_RESULT_CACHE_MAX_ENTRIES = 8
_match_result_cache: OrderedDict = OrderedDict()
_match_result_lock = threading.Lock()


def _stable_fingerprint(value) -> str:
    """Create a deterministic fingerprint for JSON-compatible input data."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _job_corpus_fingerprint(job_rows) -> str:
    """Fingerprint every field that affects matching or ranking."""
    return _stable_fingerprint(
        [
            (
                row.id,
                row.title,
                row.company,
                row.description,
                row.created_at.isoformat() if row.created_at else None,
            )
            for row in job_rows
        ]
    )


def _corpus_term_weights(
    job_rows,
    corpus_fingerprint: str | None = None,
) -> dict[str, float]:
    """Return cached corpus term weights, rebuilding them when stale."""
    corpus_key = corpus_fingerprint or _job_corpus_fingerprint(job_rows)
    now = time.monotonic()

    with _term_weight_lock:
        if (
            _term_weight_cache["key"] == corpus_key
            and now < _term_weight_cache["expires_at"]
        ):
            return _term_weight_cache["weights"]

    weights = build_term_weights(
        prepare_job_matching_text(row.title, row.description, row.company)
        for row in job_rows
    )

    with _term_weight_lock:
        _term_weight_cache["key"] = corpus_key
        _term_weight_cache["expires_at"] = now + _TERM_WEIGHT_TTL_SECONDS
        _term_weight_cache["weights"] = weights

    return weights


def _get_cached_match_results(cache_key):
    """Return a safe copy of cached results, refreshing their LRU position."""
    now = time.monotonic()

    with _match_result_lock:
        cached = _match_result_cache.get(cache_key)
        if cached is None:
            return None

        expires_at, results = cached
        if now >= expires_at:
            del _match_result_cache[cache_key]
            return None

        _match_result_cache.move_to_end(cache_key)
        return copy.deepcopy(results)


def _store_cached_match_results(cache_key, results) -> None:
    """Store plain, user-scoped match data in the bounded process cache."""
    with _match_result_lock:
        _match_result_cache[cache_key] = (
            time.monotonic() + _MATCH_RESULT_TTL_SECONDS,
            copy.deepcopy(results),
        )
        _match_result_cache.move_to_end(cache_key)

        while len(_match_result_cache) > _MATCH_RESULT_CACHE_MAX_ENTRIES:
            _match_result_cache.popitem(last=False)


def _invalidate_corpus_term_weights() -> None:
    """Invalidate cached weights after matching-relevant job changes."""
    with _term_weight_lock:
        _term_weight_cache["key"] = None
        _term_weight_cache["expires_at"] = 0.0
        _term_weight_cache["weights"] = {}

@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    payload: JobCreate,
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    job = Job(**payload.model_dump())

    db.add(job)
    mark_job_matching_corpus_changed(db)
    db.commit()
    db.refresh(job)
    _invalidate_corpus_term_weights()

    return job


@router.get("", response_model=list[JobRead])
def list_jobs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(Job)
        .order_by(Job.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()



@router.get("/search", response_model=JobSearchResult)
def search_jobs(
    q: str = Query(default="", max_length=255),
    remote_type: str | None = Query(
        default=None,
        pattern="^(remote|hybrid|onsite|unknown)$",
    ),
    eligibility_status: str | None = Query(
        default=None,
        pattern="^(eligible|ineligible|unknown)$",
    ),
    listing_status: str | None = Query(
        default=None,
        pattern="^(active|closed|unknown)$",
    ),
    employment_type: str | None = Query(
        default=None,
        pattern="^(full-time|part-time|contract|internship|unknown)$",
    ),
    experience_level: str | None = Query(
        default=None,
        pattern="^(entry-level|junior|mid-level|senior|internship|unknown)$",
    ),
    sort_by: str = Query(default="newest", pattern="^(newest|relevance)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search stored jobs using text and discovery metadata."""
    statement = select(Job)
    count_statement = select(func.count()).select_from(Job)
    filters = []

    term = q.strip()
    if term:
        pattern = f"%{term}%"
        filters.append(
            or_(
                Job.title.ilike(pattern),
                Job.company.ilike(pattern),
                Job.location.ilike(pattern),
            )
        )

    if remote_type == "unknown":
        filters.append(
            or_(
                Job.remote_type.is_(None),
                Job.remote_type == "unknown",
            )
        )
    elif remote_type is not None:
        filters.append(Job.remote_type == remote_type)

    if eligibility_status is not None:
        filters.append(Job.eligibility_status == eligibility_status)

    if listing_status is not None:
        filters.append(Job.listing_status == listing_status)

    if employment_type == "unknown":
        filters.append(
            or_(
                Job.employment_type.is_(None),
                func.trim(Job.employment_type) == "",
            )
        )
    elif employment_type is not None:
        normalized_type = func.replace(
            func.lower(func.coalesce(Job.employment_type, "")),
            " ",
            "",
        )
        normalized_type = func.replace(normalized_type, ";", ",")
        delimited_type = literal(",") + normalized_type + literal(",")
        filters.append(
            delimited_type.contains(f",{employment_type.replace(' ', '').lower()},")
        )

    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)

    if experience_level is not None:
        # Experience level is derived from listing text, so classify candidate
        # jobs before calculating totals and applying pagination.
        items = db.scalars(
            statement.order_by(Job.created_at.desc(), Job.id.desc())
        ).all()

        items = [
            job
            for job in items
            if classify_experience_level(
                {
                    "title": job.title,
                    "description": job.description,
                    "employment_type": job.employment_type,
                }
            ) == experience_level
        ]
        total = len(items)

        if sort_by != "relevance":
            items = items[skip : skip + limit]
    else:
        total = db.scalar(count_statement) or 0

        if sort_by == "relevance":
            # Score every matching job before pagination so the order is global,
            # not limited to the newest page.
            items = db.scalars(
                statement.order_by(Job.created_at.desc(), Job.id.desc())
            ).all()
        else:
            # Preserve the existing efficient newest-first behavior.
            items = db.scalars(
                statement
                .order_by(Job.created_at.desc(), Job.id.desc())
                .offset(skip)
                .limit(limit)
            ).all()

    search_items = []
    for job in items:
        job_data = JobRead.model_validate(job).model_dump()
        relevance = score_job_relevance(
            {
                "title": job.title,
                "description": job.description,
                "employment_type": job.employment_type,
            }
        )
        search_items.append(
            {
                **job_data,
                "relevance_score": relevance["score"],
                "matched_role_families": relevance["matched_role_families"],
                "relevance_reasons": relevance["reasons"],
                "experience_level": classify_experience_level(
                    {
                        "title": job.title,
                        "description": job.description,
                        "employment_type": job.employment_type,
                    }
                ),
            }
        )

    if sort_by == "relevance":
        search_items.sort(
            key=lambda item: (
                item["relevance_score"],
                item["created_at"],
                item["id"],
            ),
            reverse=True,
        )
        search_items = search_items[skip : skip + limit]

    return {
        "items": search_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/ingest/jobicy")
def refresh_jobicy_jobs(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Import and refresh jobs from the public Jobicy feed."""
    try:
        result = ingest_jobicy_jobs(db)

        if result["inserted"] or result["updated"]:
            _invalidate_corpus_term_weights()

        return result
    except JobicyAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Jobicy could not provide a complete, valid feed.",
        ) from exc


@router.post("/ingest/himalayas")
def refresh_himalayas_jobs(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Import and refresh jobs from the public Himalayas feed."""
    try:
        result = ingest_himalayas_jobs(db)

        if result["inserted"] or result["updated"]:
            _invalidate_corpus_term_weights()

        return result
    except HimalayasAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Himalayas could not provide a complete, valid feed.",
        ) from exc


@router.post("/sync/jobicy-status")
def sync_jobicy_listing_statuses(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Synchronize active, closed, and unknown status for imported listings."""
    try:
        return sync_jobicy_statuses(db)
    except JobicyAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Jobicy listing statuses could not be verified.",
        ) from exc


@router.post("/{job_id}/eligibility", response_model=JobRead)
def verify_job_eligibility(
    job_id: int,
    payload: EligibilityVerificationRequest,
    admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Record an admin's evidence-backed decision about Kenya eligibility."""
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.eligibility_status = payload.eligibility_status

    if payload.eligibility_status == "unknown":
        job.eligibility_evidence_url = None
        job.eligibility_evidence = None
        job.eligibility_verified_at = None
        job.eligibility_verified_by = None
    else:
        job.eligibility_evidence_url = str(payload.evidence_url)
        job.eligibility_evidence = payload.evidence.strip()
        job.eligibility_verified_at = datetime.now(timezone.utc)
        job.eligibility_verified_by = admin_id

        countries = list(job.eligible_countries or [])
        kenya_names = {"kenya"}

        if payload.eligibility_status == "eligible":
            if not any(
                country.strip().casefold() in kenya_names
                for country in countries
            ):
                countries.append("Kenya")
            job.eligible_countries = countries
        elif job.eligible_countries is not None:
            job.eligible_countries = [
                country
                for country in countries
                if country.strip().casefold() not in kenya_names
            ]

    db.commit()
    db.refresh(job)
    return job

@router.patch("/{job_id}/application-url", response_model=JobRead)
def update_job_application_url(
    job_id: int,
    payload: ApplicationUrlUpdate,
    admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Set or clear the verified employer application URL."""
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.application_url = (
        str(payload.application_url)
        if payload.application_url is not None
        else None
    )

    db.commit()
    db.refresh(job)
    return job

@router.get("/matches", response_model=ResumeJobMatchResult)
def match_jobs_to_resume(
    user_id: CurrentUser,
    resume_id: int = Query(..., ge=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Rank stored jobs by text overlap with the authenticated user's resume."""
    # Resolve the resume using both its ID and the authenticated owner.
    resume = resumes_api._owned_resume(resume_id, user_id, db)
    try:
        resume_bytes = resume_storage.read_resume(
            resume.storage_key,
            local_dir=resumes_api.STORAGE_DIR,
        )
    except (FileNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume file not found",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected resume file could not be read.",
        ) from exc

    # Hash the current contents so changed resume bytes invalidate the cache.
    resume_sha256 = hashlib.sha256(resume_bytes).hexdigest()

    candidate_profile = db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id
        )
    )

    profile_data = (
        {
            "headline": candidate_profile.headline,
            "professional_summary": candidate_profile.professional_summary,
            "skills": candidate_profile.skills,
            "experience": candidate_profile.experience,
            "projects": candidate_profile.projects,
            "education": candidate_profile.education,
            "certifications": candidate_profile.certifications,
        }
        if candidate_profile is not None
        else {}
    )

    profile_fingerprint = _stable_fingerprint(profile_data)

    # Load lightweight rows so changes to any matching-relevant job field
    # produce a new cache key, including edits that preserve created_at.
    job_rows = db.execute(
        select(
            Job.id,
            Job.title,
            Job.company,
            Job.description,
            Job.created_at,
        )
    ).all()

    corpus_fingerprint = _job_corpus_fingerprint(job_rows)

    cache_key = (
        str(user_id),
        resume.id,
        resume.original_filename,
        resume_sha256,
        profile_fingerprint,
        corpus_fingerprint,
    )

    scored = _get_cached_match_results(cache_key)

    if scored is None:
        resume_text = extract_resume_text(
            resume_bytes,
            resume.original_filename,
        )

        prepared_resume_features = prepare_resume_features(resume_text)

        # Parse once on a cache miss; section evidence explains where
        # requirements appear without changing the resume-only score.
        structured_resume = parse_resume_text(resume_text)
        section_features = prepare_resume_section_features(structured_resume)

        profile_section_features: dict[str, frozenset[str]] = {}
        profile_features = frozenset()

        if candidate_profile is not None:
            profile_section_features = (
                prepare_candidate_profile_section_features(profile_data)
            )
            profile_features = frozenset().union(
                *profile_section_features.values()
            )

        has_profile_evidence = bool(profile_features)
        combined_features = prepared_resume_features | profile_features

        # Corpus-wide term weights are reused when the job corpus is unchanged.
        term_weights = _corpus_term_weights(
            job_rows,
            corpus_fingerprint=corpus_fingerprint,
        )

        scored_rows = []

        for row in job_rows:
            match = score_resume_job_match(
                "",
                title=row.title,
                description=row.description,
                company=row.company,
                prepared_resume_features=prepared_resume_features,
                term_weights=term_weights,
            )
            match["term_evidence"] = build_requirement_term_evidence(
                row.description,
                section_features,
                company=row.company,
            )

            if has_profile_evidence:
                combined_match = score_resume_job_match(
                    "",
                    title=row.title,
                    description=row.description,
                    company=row.company,
                    prepared_resume_features=combined_features,
                    term_weights=term_weights,
                )

                matched_sources = classify_match_terms(
                    combined_match["matched_terms"],
                    prepared_resume_features,
                    profile_features,
                )
                required_sources = classify_match_terms(
                    combined_match["required_terms_found"],
                    prepared_resume_features,
                    profile_features,
                )
                preferred_sources = classify_match_terms(
                    combined_match["preferred_terms_found"],
                    prepared_resume_features,
                    profile_features,
                )

                match.update(
                    {
                        "profile_match_score": combined_match["match_score"],
                        "profile_matched_terms": matched_sources["profile"],
                        "profile_only_matched_terms": matched_sources["profile_only"],
                        "terms_not_found_in_resume_or_profile": (
                            combined_match["terms_not_found_in_resume"]
                        ),
                        "required_terms_found_in_profile": (
                            required_sources["profile"]
                        ),
                        "required_terms_found_in_resume_or_profile": (
                            combined_match["required_terms_found"]
                        ),
                        "required_terms_not_found_in_resume_or_profile": (
                            combined_match["required_terms_not_found"]
                        ),
                        "preferred_terms_found_in_profile": (
                            preferred_sources["profile"]
                        ),
                        "preferred_terms_found_in_resume_or_profile": (
                            combined_match["preferred_terms_found"]
                        ),
                        "preferred_terms_not_found_in_resume_or_profile": (
                            combined_match["preferred_terms_not_found"]
                        ),
                        "profile_term_evidence": build_requirement_term_evidence(
                            row.description,
                            profile_section_features,
                            company=row.company,
                            section_names=PROFILE_EVIDENCE_SECTIONS,
                        ),
                        "profile_match_reasons": combined_match["match_reasons"],
                    }
                )

            scored_rows.append((row, match))

        # Rank the complete corpus before storing results or paginating.
        scored_rows.sort(
            key=lambda pair: (
                (
                    pair[1]["profile_match_score"]
                    if pair[1].get("profile_match_score") is not None
                    else pair[1]["match_score"]
                ),
                pair[1]["match_score"],
                pair[0].created_at,
                pair[0].id,
            ),
            reverse=True,
        )

        # Store IDs and plain match dictionaries, never ORM row objects.
        scored = [
            (row.id, match)
            for row, match in scored_rows
        ]
        _store_cached_match_results(cache_key, scored)

    # Pagination uses the cached complete ranking on both cache hits and misses.
    page = scored[skip : skip + limit]
    page_ids = [job_id for job_id, _ in page]
    jobs_by_id = (
        {
            job.id: job
            for job in db.scalars(select(Job).where(Job.id.in_(page_ids)))
        }
        if page_ids
        else {}
    )

    items = []
    for job_id, match in page:
        job = jobs_by_id.get(job_id)
        if job is None:  # Deleted between the two queries.
            continue
        items.append({**JobRead.model_validate(job).model_dump(), **match})

    return {
        "resume_id": resume.id,
        "resume_filename": resume.original_filename,
        "items": items,
        "total": len(scored),
        "skip": skip,
        "limit": limit,
    }


@router.get("/screen", response_model=JobScreeningResult)
def screen_jobs_for_candidate(
    user_id: CurrentUser,
    resume_id: int = Query(..., ge=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return ranked resume matches with candidate-specific screening."""
    # Reuse the existing authenticated matching flow. This also verifies
    # resume ownership and preserves its ranking and pagination behavior.
    match_result = match_jobs_to_resume(
        user_id=user_id,
        resume_id=resume_id,
        skip=skip,
        limit=limit,
        db=db,
    )

    # Only this user's target roles and work preferences affect screening.
    candidate_profile = db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id
        )
    )

    profile_data = (
        {
            "target_roles": candidate_profile.target_roles,
            "work_preferences": candidate_profile.work_preferences,
        }
        if candidate_profile is not None
        else {}
    )

    screened_items = []
    for item in match_result["items"]:
        screening = screen_job(
            job=item,
            profile=profile_data,
            match=item,
        )
        screened_items.append({**item, **screening})

    return {
        "resume_id": match_result["resume_id"],
        "resume_filename": match_result["resume_filename"],
        "items": screened_items,
        "total": match_result["total"],
        "skip": match_result["skip"],
        "limit": match_result["limit"],
    }


@router.post(
    "/screen/start",
    response_model=JobScreeningStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Authentication is required."},
        409: {"description": "A screening run is already active."},
    },
)
def start_job_screening(
    payload: JobScreeningStartRequest,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Queue durable screening of the full job corpus for an owned resume."""
    resume = db.scalar(
        select(Resume).where(
            Resume.id == payload.resume_id,
            Resume.user_id == user_id,
        )
    )

    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found",
        )

    active_run = db.scalar(
        select(AutomationRun).where(
            AutomationRun.user_id == user_id,
            AutomationRun.pipeline_type == "job_screening",
            AutomationRun.status.in_(["queued", "running"]),
        )
    )

    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A job-screening run is already active.",
        )

    run = AutomationRun(
        user_id=user_id,
        pipeline_type="job_screening",
        trigger_type="manual",
        status="queued",
        summary={
            "resume_id": resume.id,
            "processed_count": 0,
            "prioritized_count": 0,
            "review_count": 0,
            "excluded_count": 0,
        },
    )
    db.add(run)

    try:
        db.flush()

        task = AutomationTask(
            run_id=run.id,
            user_id=user_id,
            task_type="screen_jobs",
            status="queued",
            idempotency_key="screen-jobs",
            payload={"resume_id": resume.id},
            attempts=0,
            max_attempts=3,
        )
        db.add(task)
        db.commit()
        db.refresh(run)
        db.refresh(task)
    except Exception:
        db.rollback()
        raise

    return {
        "run_id": run.id,
        "task_id": task.id,
        "pipeline_type": "job_screening",
        "status": run.status,
        "task_status": task.status,
        "resume_id": resume.id,
    }

@router.get(
    "/screen/runs/{run_id}",
    response_model=JobScreeningRunStatus,
)
def get_job_screening_run(
    run_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    """Return safe progress metadata for the current user's screening run."""
    run = db.scalar(
        select(AutomationRun).where(
            AutomationRun.id == run_id,
            AutomationRun.user_id == user_id,
            AutomationRun.pipeline_type == "job_screening",
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Screening run not found")

    task = db.scalar(
        select(AutomationTask).where(
            AutomationTask.run_id == run.id,
            AutomationTask.user_id == user_id,
            AutomationTask.task_type == "screen_jobs",
        )
    )
    summary = run.summary or {}
    failed = run.status == "failed" or (
        task is not None and task.status == "failed"
    )

    return {
        "run_id": run.id,
        "pipeline_type": "job_screening",
        "status": run.status,
        "resume_id": summary.get("resume_id"),
        "expected_total": summary.get("expected_total", 0),
        "processed_count": summary.get("processed_count", 0),
        "prioritized_count": summary.get("prioritized_count", 0),
        "review_count": summary.get("review_count", 0),
        "excluded_count": summary.get("excluded_count", 0),
        "task_status": task.status if task else None,
        "task_attempts": task.attempts if task else None,
        "task_max_attempts": task.max_attempts if task else None,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "updated_at": run.updated_at,
        "error_message": (
            "Screening failed. You can retry the run or contact support."
            if failed else None
        ),
    }


@router.get(
    "/screen/runs/{run_id}/results",
    response_model=JobScreeningResultsPage,
)
def get_job_screening_run_results(
    run_id: int,
    user_id: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return persisted screening snapshots for an owned run."""
    run = db.scalar(
        select(AutomationRun).where(
            AutomationRun.id == run_id,
            AutomationRun.user_id == user_id,
            AutomationRun.pipeline_type == "job_screening",
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Screening run not found")

    filters = [
        AutomationScreeningResult.run_id == run.id,
        AutomationScreeningResult.user_id == user_id,
    ]
    resume_id = (run.summary or {}).get("resume_id")
    if isinstance(resume_id, int) and not isinstance(resume_id, bool):
        filters.append(AutomationScreeningResult.resume_id == resume_id)

    total = db.scalar(
        select(func.count())
        .select_from(AutomationScreeningResult)
        .where(*filters)
    ) or 0

    rows = db.scalars(
        select(AutomationScreeningResult)
        .where(*filters)
        .order_by(
            AutomationScreeningResult.ranking_score.desc(),
            AutomationScreeningResult.match_score.desc(),
            AutomationScreeningResult.job_created_at.desc(),
            AutomationScreeningResult.job_id.desc(),
        )
        .offset(skip)
        .limit(limit)
    ).all()

    items = [
        JobScreeningItem.model_validate(row.result)
        for row in rows
    ]
    return {
        "run_id": run.id,
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.post(
    "/ingest/himalayas/start",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Authentication is required."},
        403: {"description": "Admin access is required."},
        409: {"description": "An automated Himalayas scan is already active."},
    },
)
def start_himalayas_ingestion(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Start a durable, worker-driven full scan of the Himalayas feed."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    now = datetime.now(timezone.utc)
    dialect = db.get_bind().dialect.name

    try:
        # Initialize the singleton row without committing separately.
        if dialect == "postgresql":
            statement = pg_insert(HimalayasIngestionState).values(
                id=1,
                status="running",
                processed_batches={},
            ).on_conflict_do_nothing(index_elements=["id"])
            db.execute(statement)
        elif dialect == "sqlite":
            statement = sqlite_insert(HimalayasIngestionState).values(
                id=1,
                status="running",
                processed_batches={},
            ).on_conflict_do_nothing(index_elements=["id"])
            db.execute(statement)
        else:
            state = db.get(HimalayasIngestionState, 1)
            if state is None:
                db.add(HimalayasIngestionState(
                    id=1,
                    status="running",
                    processed_batches={},
                ))
                db.flush()

        state = db.scalar(
            select(HimalayasIngestionState)
            .where(HimalayasIngestionState.id == 1)
            .with_for_update()
        )

        if state is None:
            raise RuntimeError(
                "Could not initialize Himalayas ingestion state."
            )

        if state.automation_run_id is not None:
            active_run = db.get(AutomationRun, state.automation_run_id)
            if active_run is not None and active_run.status in {
                "queued",
                "running",
            }:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A Himalayas ingestion run is already active "
                        f"(run_id={active_run.id})."
                    ),
                )

        run = AutomationRun(
            user_id=None,
            pipeline_type="himalayas_ingestion",
            trigger_type="manual",
            status="queued",
            summary={},
        )
        db.add(run)
        db.flush()

        task = AutomationTask(
            run_id=run.id,
            user_id=None,
            task_type="ingest_himalayas_batch",
            status="queued",
            idempotency_key="initial-batch",
            payload={"max_pages": 25},
            max_attempts=3,
        )
        db.add(task)

        # Reset legacy/finished state and claim the cursor for this run.
        state.cursor = None
        state.automation_run_id = run.id
        state.processed_batches = {}
        state.status = "running"
        state.pages_fetched = 0
        state.fetched = 0
        state.inserted = 0
        state.updated = 0
        state.expired = 0
        state.expiry_reconciled_at = None
        state.started_at = now
        state.updated_at = now
        state.completed_at = None

        db.commit()
        db.refresh(run)
        db.refresh(task)

        return {
            "run_id": run.id,
            "task_id": task.id,
            "pipeline_type": run.pipeline_type,
            "status": run.status,
            "task_status": task.status,
            "max_pages": 25,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post(
    "/ingest/himalayas/resume",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Authentication is required."},
        403: {"description": "Admin access is required."},
        409: {"description": "The saved Himalayas scan cannot be resumed."},
    },
)
def resume_himalayas_ingestion(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
):
    """Resume a failed automated scan from its last committed cursor."""
    now = datetime.now(timezone.utc)

    try:
        state = db.scalar(
            select(HimalayasIngestionState)
            .where(HimalayasIngestionState.id == 1)
            .with_for_update()
        )

        if state is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No saved Himalayas ingestion state exists.",
            )

        if state.status != "running" or not state.cursor:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Himalayas ingestion can only resume from a running "
                    "state with a saved cursor."
                ),
            )

        if state.automation_run_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The saved scan has no automation run to resume.",
            )

        previous_run = db.get(AutomationRun, state.automation_run_id)
        if (
            previous_run is None
            or previous_run.pipeline_type != "himalayas_ingestion"
            or previous_run.status != "failed"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The previous Himalayas ingestion run is not failed.",
            )

        active_task = db.scalar(
            select(AutomationTask.id)
            .where(
                AutomationTask.run_id == previous_run.id,
                AutomationTask.task_type == "ingest_himalayas_batch",
                AutomationTask.status.in_(["queued", "running"]),
            )
            .limit(1)
        )
        if active_task is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The previous Himalayas run still has an active task.",
            )

        run = AutomationRun(
            user_id=None,
            pipeline_type="himalayas_ingestion",
            trigger_type="manual",
            status="queued",
            summary={},
        )
        db.add(run)
        db.flush()

        task = AutomationTask(
            run_id=run.id,
            user_id=None,
            task_type="ingest_himalayas_batch",
            status="queued",
            idempotency_key="initial-batch",
            payload={"max_pages": 25},
            max_attempts=3,
        )
        db.add(task)

        # Preserve cursor, counters, replay history, and expiry marker.
        state.automation_run_id = run.id
        state.status = "running"
        state.started_at = now
        state.updated_at = now
        state.completed_at = None

        db.commit()
        db.refresh(run)
        db.refresh(task)

        return {
            "run_id": run.id,
            "task_id": task.id,
            "previous_run_id": previous_run.id,
            "pipeline_type": run.pipeline_type,
            "status": run.status,
            "task_status": task.status,
            "max_pages": 25,
            "resumed": True,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post(
    "/ingest/himalayas/batch",
    response_model=HimalayasBatchIngestionResult,
    responses={
        401: {"description": "Authentication is required."},
        403: {"description": "Admin access is required."},
        502: {"description": "The Himalayas API returned an invalid response or failed."},
    },
)
def refresh_himalayas_batch(
    _admin_id: CurrentAdmin,
    db: Session = Depends(get_db),
    max_pages: int = Query(default=5, ge=1, le=25),
):
    """Import or resume a bounded batch from the Himalayas feed."""
    from app.services.job_ingestion import ingest_himalayas_batch

    try:
        result = ingest_himalayas_batch(db, max_pages=max_pages)

        if result["inserted_this_batch"] or result["updated_this_batch"]:
            _invalidate_corpus_term_weights()

        return result
    except HimalayasAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Himalayas could not provide a valid batch.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
