"""OAuth flows for Slack and Jira.

Slack: OAuth v2 install flow with state parameter validation.
Jira: OAuth 2.0 3LO with refresh-token rotation.

Both flows use separate app installs (or separate scope sets) for the
read and write roles — the credential separation is enforced at the OAuth level.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx


@dataclass(frozen=True)
class OAuthConfig:
    """OAuth application configuration."""

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]


@dataclass
class TokenResponse:
    """OAuth token response."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str = ""
    token_type: str = "Bearer"
    team_id: str | None = None  # Slack workspace ID
    cloud_id: str | None = None  # Jira cloud ID


class SlackOAuthFlow:
    """Slack OAuth v2 install flow.

    Separate installs for read-only (agent) and write (executor) scopes.
    State parameter validated to prevent CSRF.
    """

    AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
    TOKEN_URL = "https://slack.com/api/oauth.v2.access"

    def __init__(self, config: OAuthConfig) -> None:
        self._config = config
        self._pending_states: set[str] = set()

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate authorization URL with CSRF state parameter.

        Returns:
            (url, state) — redirect user to url, validate state on callback
        """
        state = secrets.token_urlsafe(32)
        self._pending_states.add(state)

        params = {
            "client_id": self._config.client_id,
            "scope": ",".join(self._config.scopes),
            "redirect_uri": self._config.redirect_uri,
            "state": state,
        }
        url = f"{self.AUTHORIZE_URL}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, code: str, state: str) -> TokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            state: State parameter — must match what we sent

        Raises:
            ValueError: If state doesn't match (CSRF protection)
        """
        if state not in self._pending_states:
            raise ValueError("Invalid state parameter — possible CSRF attack")
        self._pending_states.discard(state)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("ok"):
            raise ValueError(f"Slack OAuth error: {data.get('error', 'unknown')}")

        return TokenResponse(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope", ""),
            team_id=data.get("team", {}).get("id"),
        )


class JiraOAuthFlow:
    """Jira OAuth 2.0 3LO with refresh-token rotation.

    Handles 401 → refresh → retry once. Stores cloudid for API calls.
    """

    AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
    TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

    def __init__(self, config: OAuthConfig) -> None:
        self._config = config
        self._pending_states: set[str] = set()

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate Jira authorization URL."""
        state = secrets.token_urlsafe(32)
        self._pending_states.add(state)

        params = {
            "audience": "api.atlassian.com",
            "client_id": self._config.client_id,
            "scope": " ".join(self._config.scopes),
            "redirect_uri": self._config.redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        url = f"{self.AUTHORIZE_URL}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, code: str, state: str) -> TokenResponse:
        """Exchange authorization code for tokens."""
        if state not in self._pending_states:
            raise ValueError("Invalid state parameter — possible CSRF attack")
        self._pending_states.discard(state)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Get accessible resources to find cloud_id
            cloud_id = await self._get_cloud_id(data["access_token"], client)

        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope", ""),
            cloud_id=cloud_id,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Refresh an expired access token.

        Jira uses refresh-token rotation: the old refresh token is invalidated
        and a new one is returned.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope", ""),
        )

    async def _get_cloud_id(self, access_token: str, client: httpx.AsyncClient) -> str:
        """Get the Jira cloud ID for API calls."""
        resp = await client.get(
            self.RESOURCES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        resources = resp.json()
        if resources:
            return resources[0].get("id", "")
        return ""
