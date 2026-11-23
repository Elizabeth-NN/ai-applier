from typing import Annotated

from clerk_backend_api import (
    AuthenticateRequestOptions,
    authenticate_request,
)
from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings


def _authenticated_payload(request: Request) -> dict:
    """Validate the Clerk session and return its verified claims."""
    state = authenticate_request(
        request,
        AuthenticateRequestOptions(
            secret_key=settings.clerk_secret_key,
            authorized_parties=settings.allowed_frontend_origins,
            accepts_token=["session_token"],
        ),
    )

    if not state.is_signed_in:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = state.payload or {}

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    return payload


def require_user(request: Request) -> str:
    """Return the authenticated Clerk user ID."""
    return _authenticated_payload(request)["sub"]


def require_admin(request: Request) -> str:
    """Allow only users with the trusted Clerk admin role."""
    payload = _authenticated_payload(request)
    metadata = payload.get("metadata")

    if not isinstance(metadata, dict) or metadata.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return payload["sub"]


CurrentUser = Annotated[str, Depends(require_user)]
CurrentAdmin = Annotated[str, Depends(require_admin)]
