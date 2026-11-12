from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AutomationRun,
    AutomationScreeningResult,
    Job,
    Resume,
)


def save_screening_results(
    db: Session,
    *,
    run_id: int,
    user_id: str,
    resume_id: int,
    results: list[dict[str, Any]],
) -> int:
    """Persist a batch of screening snapshots for an owned screening run."""

    run = db.get(AutomationRun, run_id)
    if run is None:
        raise ValueError("Automation run does not exist.")

    if run.user_id != user_id:
        raise ValueError("Automation run ownership mismatch.")

    if run.pipeline_type != "job_screening":
        raise ValueError("Automation run is not a job-screening run.")

    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user_id:
        raise ValueError("Resume does not belong to this user.")

    if not results:
        return 0

    job_ids = []
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Every screening result must be a dictionary.")

        job_id = result.get("id")
        if not isinstance(job_id, int) or isinstance(job_id, bool):
            raise ValueError("Every screening result must contain a valid job id.")

        job_ids.append(job_id)

    if len(job_ids) != len(set(job_ids)):
        raise ValueError("A batch cannot contain duplicate job results.")

    jobs_by_id = {
        job.id: job
        for job in db.scalars(
            select(Job).where(Job.id.in_(job_ids))
        ).all()
    }
    missing_jobs = set(job_ids) - set(jobs_by_id)

    if missing_jobs:
        raise ValueError(
            f"Screening results reference missing jobs: {sorted(missing_jobs)}"
        )

    existing_results = {
        item.job_id: item
        for item in db.scalars(
            select(AutomationScreeningResult).where(
                AutomationScreeningResult.run_id == run_id,
                AutomationScreeningResult.job_id.in_(job_ids),
            )
        ).all()
    }

    saved = 0

    try:
        for result, job_id in zip(results, job_ids):
            match_score = result.get("match_score")
            profile_match_score = result.get("profile_match_score")

            if (
                not isinstance(match_score, int)
                or isinstance(match_score, bool)
                or not 0 <= match_score <= 100
            ):
                raise ValueError("Screening result has an invalid match score.")

            if profile_match_score is not None and (
                not isinstance(profile_match_score, int)
                or isinstance(profile_match_score, bool)
                or not 0 <= profile_match_score <= 100
            ):
                raise ValueError(
                    "Screening result has an invalid profile match score."
                )

            ranking_score = (
                profile_match_score
                if profile_match_score is not None
                else match_score
            )
            job_created_at = jobs_by_id[job_id].created_at

            existing = existing_results.get(job_id)

            if existing is not None:
                if existing.user_id != user_id:
                    raise ValueError("Existing screening result ownership mismatch.")

                if existing.resume_id != resume_id:
                    raise ValueError(
                        "A screening run cannot mix different resumes."
                    )

                existing.result = result
                existing.ranking_score = ranking_score
                existing.match_score = match_score
                existing.job_created_at = job_created_at
            else:
                db.add(
                    AutomationScreeningResult(
                        run_id=run_id,
                        user_id=user_id,
                        resume_id=resume_id,
                        job_id=job_id,
                        result=result,
                        ranking_score=ranking_score,
                        match_score=match_score,
                        job_created_at=job_created_at,
                    )
                )

            saved += 1

        db.commit()
        return saved
    except Exception:
        db.rollback()
        raise
