"""Slack write provider — lives exclusively in studio.executor.

Scopes required: chat:write, chat:write.public
These are WRITE scopes. The agent process NEVER has access to this token.

This module is ONLY imported from studio.executor. The import-graph test
asserts that studio.agent cannot reach it.
"""

from __future__ import annotations

from typing import Any

import httpx

from studio.providers.base import WriteProvider


class SlackWriteProvider(WriteProvider):
    """Write-capable Slack API client.

    ONLY used by the executor. The agent process has no access to this
    client or its credentials.
    """

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://slack.com/api",
    ) -> None:
        self._token = access_token
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def execute_action(
        self,
        action_kind: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a Slack write action.

        Supported: slack.post (post message, reply in thread)
        """
        if action_kind == "slack.post":
            return await self._post_message(payload, idempotency_key)
        else:
            raise ValueError(f"Unsupported Slack action: {action_kind}")

    async def _post_message(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        """Post a message to a Slack channel."""
        body: dict[str, Any] = {
            "channel": payload["channel_id"],
            "text": payload["text"],
        }
        if payload.get("thread_ts"):
            body["thread_ts"] = payload["thread_ts"]
        if payload.get("blocks"):
            body["blocks"] = payload["blocks"]

        resp = await self._client.post(
            "/chat.postMessage",
            json=body,
            headers={"X-Idempotency-Key": idempotency_key},
        )
        resp.raise_for_status()
        return resp.json()

    async def verify_state(self, resource_id: str) -> dict[str, Any]:
        """Verify current state of a Slack channel/thread."""
        resp = await self._client.get(
            "/conversations.history",
            params={"channel": resource_id, "limit": 5},
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
