from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ARRAY, JSON, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.resumes import (
    extract_resume_text,
    get_owned_resume,
    parse_resume_fields,
)
from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.candidate_profile import CandidateProfile
from app.schemas.candidate_profile import (
    CandidateProfileRead,
    CandidateProfileUpsert,
)


router = APIRouter(
    prefix="/api/candidate-profile",
    tags=["Candidate Profile"],
)

# Parsed key -> possible column names on the CandidateProfile model.
# The first alias that exists as a real column is used; the rest are ignored,
# so this works even if your model only has a subset of these fields.
FIELD_ALIASES: dict[str, list[str]] = {
    "full_name": ["full_name", "name"],
    "first_name": ["first_name"],
    "last_name": ["last_name"],
    "email": ["email", "contact_email"],
    "phone": ["phone", "phone_number"],
    "location": ["location", "city"],
    "linkedin_url": ["linkedin_url", "linkedin"],
    "github_url": ["github_url", "github"],
    "headline": ["headline", "title", "current_title"],
    "summary": ["summary", "bio", "about"],
    "skills": ["skills"],
}


def _get_profile(user_id: str, db: Session) -> CandidateProfile | None:
    return db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id,
        )
    )


def _is_empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _apply_parsed_fields(
    profile: CandidateProfile,
    parsed: dict,
    overwrite: bool,
) -> list[str]:
    """Copy parsed values onto the profile. Returns the columns that changed."""
    columns = CandidateProfile.__table__.columns
    updated: list[str] = []

    for key, value in parsed.items():
        column_name = next(
            (alias for alias in FIELD_ALIASES.get(key, []) if alias in columns),
            None,
        )
        if column_name is None:
            continue

        column = columns[column_name]
        if column.primary_key or column.foreign_keys:
            continue

        if isinstance(value, list) and not isinstance(column.type, (JSON, ARRAY)):
            value = ", ".join(value)

        if not overwrite and not _is_empty(getattr(profile, column_name, None)):
            continue

        setattr(profile, column_name, value)
        updated.append(column_name)

    return updated


@router.get("", response_model=CandidateProfileRead | None)
def get_candidate_profile(
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    return _get_profile(user_id, db)


@router.put(
    "",
    response_model=CandidateProfileRead,
    status_code=status.HTTP_200_OK,
)
def upsert_candidate_profile(
    payload: CandidateProfileUpsert,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    profile = _get_profile(user_id, db)

    if profile is None:
        profile = CandidateProfile(user_id=user_id)
        db.add(profile)

    for field, value in payload.model_dump().items():
        setattr(profile, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate profile already exists for this account.",
        ) from exc

    db.refresh(profile)
    return profile


@router.post(
    "/from-resume/{resume_id}",
    response_model=CandidateProfileRead,
    status_code=status.HTTP_200_OK,
)
def fill_candidate_profile_from_resume(
    resume_id: int,
    user_id: CurrentUser,
    overwrite: bool = Query(
        False,
        description="Replace fields that already have a value. "
        "By default only empty fields are filled.",
    ),
    db: Session = Depends(get_db),
):
    resume = get_owned_resume(resume_id, user_id, db)
    parsed = parse_resume_fields(extract_resume_text(resume))

    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract any profile information from this resume.",
        )

    profile = _get_profile(user_id, db)
    if profile is None:
        profile = CandidateProfile(user_id=user_id)
        db.add(profile)

    _apply_parsed_fields(profile, parsed, overwrite)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The resume did not contain all required profile fields. "
                "Create the profile with PUT /api/candidate-profile first, "
                "then run this again."
            ),
        ) from exc

    db.refresh(profile)
    return profile
