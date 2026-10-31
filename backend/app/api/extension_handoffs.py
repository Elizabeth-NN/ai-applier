"""Unauthenticated, single-use Chrome extension handoff redemption."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.schemas.application_execution import (
    ExtensionHandoffRedeemRequest,
    ExtensionHandoffRedeemResponse,
)
from app.services.application_preparation import redeem_extension_handoff


router = APIRouter(
    prefix="/api/extension-handoffs",
    tags=["Extension Handoffs"],
)


@router.post(
    "/redeem",
    response_model=ExtensionHandoffRedeemResponse,
)
def redeem_handoff(
    payload: ExtensionHandoffRedeemRequest,
    db: Session = Depends(get_db),
):
    """Redeem a short-lived credential without Clerk authentication."""
    return redeem_extension_handoff(
        db,
        token=payload.token.get_secret_value(),
        active_url=payload.active_url,
    )
