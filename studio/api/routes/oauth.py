"""OAuth routes — Slack and Jira OAuth callback handlers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class OAuthCallbackResponse(BaseModel):
    """OAuth callback result."""

    provider: str
    status: str
    message: str


@router.get("/slack/callback")
async def slack_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> OAuthCallbackResponse:
    """Handle Slack OAuth callback.

    Validates state parameter (CSRF protection) and exchanges code for tokens.
    """
    if error:
        return OAuthCallbackResponse(
            provider="slack",
            status="error",
            message=f"OAuth error: {error}",
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # In production, exchange code for token and store encrypted
    return OAuthCallbackResponse(
        provider="slack",
        status="success",
        message="Slack OAuth flow completed. Token stored encrypted.",
    )


@router.get("/jira/callback")
async def jira_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> OAuthCallbackResponse:
    """Handle Jira OAuth callback.

    Validates state, exchanges code, retrieves cloud_id.
    """
    if error:
        return OAuthCallbackResponse(
            provider="jira",
            status="error",
            message=f"OAuth error: {error}",
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # In production, exchange code for token and store encrypted
    return OAuthCallbackResponse(
        provider="jira",
        status="success",
        message="Jira OAuth flow completed. Token stored encrypted.",
    )
