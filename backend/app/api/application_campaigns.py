from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.dependencies import get_db
from app.models.application_campaign import ApplicationCampaign
from app.models.application_execution import ApplicationExecution
from app.schemas.application_campaign import (
    ApplicationCampaignCreate,
    ApplicationCampaignProgressRead,
    ApplicationCampaignRead,
    ApplicationCampaignUpdate,
)


router = APIRouter(
    prefix="/api/application-campaigns",
    tags=["Application Campaigns"],
)


def _get_owned_campaign(
    db: Session,
    campaign_id: int,
    user_id: str,
) -> ApplicationCampaign:
    campaign = db.scalar(
        select(ApplicationCampaign).where(
            ApplicationCampaign.id == campaign_id,
            ApplicationCampaign.user_id == user_id,
        )
    )

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application campaign not found",
        )

    return campaign


@router.post(
    "",
    response_model=ApplicationCampaignRead,
    status_code=status.HTTP_201_CREATED,
)
def create_application_campaign(
    payload: ApplicationCampaignCreate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    campaign = ApplicationCampaign(
        user_id=user_id,
        name=payload.name,
        target_applications=payload.target_applications,
        starts_on=payload.starts_on,
        deadline_on=payload.deadline_on,
    )

    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return campaign


@router.get("", response_model=list[ApplicationCampaignRead])
def list_application_campaigns(
    user_id: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(ApplicationCampaign)
        .where(ApplicationCampaign.user_id == user_id)
        .order_by(ApplicationCampaign.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.get(
    "/{campaign_id}",
    response_model=ApplicationCampaignRead,
)
def get_application_campaign(
    campaign_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    return _get_owned_campaign(db, campaign_id, user_id)


@router.patch(
    "/{campaign_id}",
    response_model=ApplicationCampaignRead,
)
def update_application_campaign(
    campaign_id: int,
    payload: ApplicationCampaignUpdate,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    campaign = _get_owned_campaign(db, campaign_id, user_id)
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campaign name cannot be null",
        )

    if "target_applications" in changes and changes["target_applications"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campaign target cannot be null",
        )

    starts_on = changes.get("starts_on", campaign.starts_on)
    deadline_on = changes.get("deadline_on", campaign.deadline_on)

    if starts_on is None or deadline_on is None or deadline_on <= starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campaign deadline must be after its start date",
        )

    for field, value in changes.items():
        setattr(campaign, field, value)

    db.commit()
    db.refresh(campaign)

    return campaign


@router.get(
    "/{campaign_id}/progress",
    response_model=ApplicationCampaignProgressRead,
)
def get_application_campaign_progress(
    campaign_id: int,
    user_id: CurrentUser,
    db: Session = Depends(get_db),
):
    campaign = _get_owned_campaign(db, campaign_id, user_id)

    submitted = db.scalar(
        select(func.count(ApplicationExecution.id)).where(
            ApplicationExecution.user_id == user_id,
            ApplicationExecution.campaign_id == campaign.id,
            ApplicationExecution.status == "submitted",
            ApplicationExecution.submitted_at.is_not(None),
        )
    ) or 0

    remaining = max(campaign.target_applications - submitted, 0)
    days_remaining = max((campaign.deadline_on - date.today()).days, 0)

    required_per_week = None
    if days_remaining > 0 and remaining > 0:
        required_per_week = round(remaining / days_remaining * 7, 2)

    percentage = round(
        min(submitted / campaign.target_applications * 100, 100),
        2,
    )

    return ApplicationCampaignProgressRead(
        campaign_id=campaign.id,
        target_applications=campaign.target_applications,
        submitted=submitted,
        remaining=remaining,
        percentage=percentage,
        days_remaining=days_remaining,
        required_per_week=required_per_week,
    )
