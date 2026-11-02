from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


@router.get("", response_model=CandidateProfileRead | None)
def get_candidate_profile(
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    return db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id,
        )
    )


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
    profile = db.scalar(
        select(CandidateProfile).where(
            CandidateProfile.user_id == user_id,
        )
    )

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
