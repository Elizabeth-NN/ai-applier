import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import ARRAY, JSON, String, Text, select
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
# The first alias that exists as a real column is used.
FIELD_ALIASES: dict[str, list[str]] = {
    "full_name": ["full_name", "name"],
    "first_name": ["first_name"],
    "last_name": ["last_name"],
    "email": ["email", "contact_email", "email_address"],
    "phone": ["phone", "phone_number", "phone_no"],
    "location": ["location", "city"],
    "headline": ["headline", "professional_headline", "title", "current_title"],
    "summary": ["summary", "professional_summary", "bio", "about"],
    "skills": ["skills"],
    "target_roles": ["target_roles", "target_job_roles", "desired_roles", "target_titles"],
    "experience": ["work_experience", "experience", "work_history", "experiences"],
    "education": ["education", "educations"],
    "projects": ["projects"],
    "certifications": ["certifications", "certificates"],
    "links": ["professional_links", "links", "social_links", "urls"],
    "linkedin_url": ["linkedin_url", "linkedin"],
    "github_url": ["github_url", "github"],
}

# JSON columns that hold an object rather than a list.
DICT_COLUMNS = {"professional_links", "links", "social_links", "urls", "work_preferences", "preferences"}

# Keys that are redundant when another field already carries the information.
REDUNDANT_WHEN_UNMAPPED = {"first_name", "last_name"}


class ResumeFillResult(BaseModel):
    profile: CandidateProfileRead
    updated_fields: list[str]
    kept_fields: list[str]
    unmapped_fields: list[str]


def _get_profile(user_id: str, db: Session) -> CandidateProfile | None:
    return db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id,
        )
    )


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped in ("", "[]", "{}", "null")
    return value == [] or value == {}


def _column_for(key: str, columns) -> str | None:
    for alias in FIELD_ALIASES.get(key, []):
        if alias in columns:
            col = columns[alias]
            if not col.primary_key and not col.foreign_keys:
                return alias
    return None


def _coerce(value, column):
    """Convert a parsed value into what the column can store."""
    is_json = isinstance(column.type, (JSON, ARRAY))
    if is_json:
        return value
    # Text-like column.
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return ", ".join(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    return value


def _existing_as_python(raw):
    """Read the current column value as a Python object if it is JSON text."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def _fill_null_defaults(profile: CandidateProfile) -> None:
    """Replace NULL text/JSON columns with empty values.

    The profile form binds these straight into controlled inputs, which
    cannot accept null. Only columns that are currently None are touched.
    """
    for column in CandidateProfile.__table__.columns:
        if column.primary_key or column.foreign_keys:
            continue
        if getattr(profile, column.name, None) is not None:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        if isinstance(column.type, (String, Text)):
            setattr(profile, column.name, "")
        elif isinstance(column.type, (JSON, ARRAY)):
            setattr(profile, column.name, {} if column.name in DICT_COLUMNS else [])


def _apply_parsed_fields(
    profile: CandidateProfile,
    parsed: dict,
    overwrite: bool,
) -> tuple[list[str], list[str], list[str]]:
    """Returns (updated columns, kept columns, parsed keys with no column)."""
    columns = CandidateProfile.__table__.columns
    updated: list[str] = []
    kept: list[str] = []
    unmapped: list[str] = []
    has_links_column = _column_for("links", columns) is not None

    for key, value in parsed.items():
        column_name = _column_for(key, columns)

        if column_name is None:
            redundant = key in REDUNDANT_WHEN_UNMAPPED or (
                key in {"linkedin_url", "github_url"} and has_links_column
            )
            if not redundant:
                unmapped.append(key)
            continue

        # linkedin/github are also covered by the links column; skip duplicates
        # when the links dict already supplied them.
        if key in {"linkedin_url", "github_url"} and has_links_column:
            continue

        column = columns[column_name]
        current = getattr(profile, column_name, None)

        # Dict columns (professional links) merge key by key.
        if isinstance(value, dict):
            existing = _existing_as_python(current)
            existing = existing if isinstance(existing, dict) else {}
            merged = (
                {**existing, **value} if overwrite else {**value, **existing}
            )
            merged = {k: v for k, v in merged.items() if not _is_empty(v)}
            if merged == existing:
                kept.append(column_name)
                continue
            setattr(profile, column_name, _coerce(merged, column))
            updated.append(column_name)
            continue

        if not overwrite and not _is_empty(current):
            kept.append(column_name)
            continue

        setattr(profile, column_name, _coerce(value, column))
        updated.append(column_name)

    return updated, kept, unmapped


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
    response_model=ResumeFillResult,
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

    updated, kept, unmapped = _apply_parsed_fields(profile, parsed, overwrite)
    _fill_null_defaults(profile)

    if not updated and not kept:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "None of the details found in the resume match columns on the "
                f"profile model ({', '.join(sorted(parsed))}). "
                "Update FIELD_ALIASES in candidate_profile.py."
            ),
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The resume did not contain all required profile fields. "
                "Save the profile once with the form, then run this again."
            ),
        ) from exc

    db.refresh(profile)
    return ResumeFillResult(
        profile=CandidateProfileRead.model_validate(profile, from_attributes=True),
        updated_fields=updated,
        kept_fields=kept,
        unmapped_fields=unmapped,
    )