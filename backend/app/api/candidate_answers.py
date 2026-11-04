from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.candidate_answer import CandidateAnswer
from app.schemas.candidate_answer import (
    CandidateAnswerCreate,
    CandidateAnswerRead,
    CandidateAnswerUpdate,
)


router = APIRouter(
    prefix="/api/candidate-answers",
    tags=["Candidate Answers"],
)


@router.post(
    "",
    response_model=CandidateAnswerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate_answer(
    payload: CandidateAnswerCreate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    answer = CandidateAnswer(
        user_id=user_id,
        question_key=payload.question_key,
        question_label=payload.question_label.strip(),
        question_aliases=payload.question_aliases,
        answer=payload.answer.strip(),
        is_user_authored=True,
        is_approved=False,
    )

    db.add(answer)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An answer already exists for this question key.",
        ) from exc

    db.refresh(answer)
    return answer


@router.get("", response_model=list[CandidateAnswerRead])
def list_candidate_answers(
    user_id: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(CandidateAnswer)
        .where(CandidateAnswer.user_id == user_id)
        .order_by(CandidateAnswer.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(statement).all()


@router.get("/{answer_id}", response_model=CandidateAnswerRead)
def get_candidate_answer(
    answer_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    answer = db.scalar(
        select(CandidateAnswer).where(
            CandidateAnswer.id == answer_id,
            CandidateAnswer.user_id == user_id,
        )
    )

    if answer is None:
        raise HTTPException(status_code=404, detail="Candidate answer not found.")

    return answer


@router.patch("/{answer_id}", response_model=CandidateAnswerRead)
def update_candidate_answer(
    answer_id: int,
    payload: CandidateAnswerUpdate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    answer = db.scalar(
        select(CandidateAnswer).where(
            CandidateAnswer.id == answer_id,
            CandidateAnswer.user_id == user_id,
        )
    )

    if answer is None:
        raise HTTPException(status_code=404, detail="Candidate answer not found.")

    answer.question_label = payload.question_label.strip()
    if payload.question_aliases is not None:
        answer.question_aliases = payload.question_aliases
    answer.answer = payload.answer.strip()

    # Revised text must be reviewed and approved again.
    answer.is_user_authored = True
    answer.is_approved = False

    db.commit()
    db.refresh(answer)
    return answer


@router.post("/{answer_id}/approve", response_model=CandidateAnswerRead)
def approve_candidate_answer(
    answer_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    answer = db.scalar(
        select(CandidateAnswer).where(
            CandidateAnswer.id == answer_id,
            CandidateAnswer.user_id == user_id,
        )
    )

    if answer is None:
        raise HTTPException(status_code=404, detail="Candidate answer not found.")

    if not answer.is_user_authored:
        raise HTTPException(
            status_code=409,
            detail="Only answers confirmed as personally written can be approved.",
        )

    answer.is_approved = True
    db.commit()
    db.refresh(answer)
    return answer


@router.delete("/{answer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate_answer(
    answer_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    answer = db.scalar(
        select(CandidateAnswer).where(
            CandidateAnswer.id == answer_id,
            CandidateAnswer.user_id == user_id,
        )
    )

    if answer is None:
        raise HTTPException(status_code=404, detail="Candidate answer not found.")

    db.delete(answer)
    db.commit()
