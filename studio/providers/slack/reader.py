"""Slack read-only provider — search and read operations only.

Scopes required: channels:history, channels:read, users:read, search:read
These are read-only scopes. No write scope is requested or available.
"""

from __future__ import annotations

from typing import Any

import httpx

from studio.providers.base import ReadOnlyProvider


class SlackReadOnlyProvider(ReadOnlyProvider):
    """Read-only Slack API client.

    This client can ONLY search and read. It has no write methods because
    ReadOnlyProvider defines none. The OAuth token used here has only
    read scopes — even if someone tried to call a write endpoint with this
    token, Slack would reject it.
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

    async def search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search Slack messages."""
        max_results = kwargs.get("max_results", 20)
        resp = await self._client.get(
            "/search.messages",
            params={"query": query, "count": max_results},
        )
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("messages", {}).get("matches", [])
        return [
            {
                "channel": m.get("channel", {}).get("id", ""),
                "text": m.get("text", ""),
                "ts": m.get("ts", ""),
                "user": m.get("user", ""),
                "permalink": m.get("permalink", ""),
            }
            for m in messages[:max_results]
        ]

    async def get(self, resource_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a Slack conversation/thread."""
        channel_id = resource_id
        thread_ts = kwargs.get("thread_ts")

        if thread_ts:
            resp = await self._client.get(
                "/conversations.replies",
                params={"channel": channel_id, "ts": thread_ts},
            )
        else:
            resp = await self._client.get(
                "/conversations.history",
                params={"channel": channel_id, "limit": kwargs.get("limit", 20)},
            )

        resp.raise_for_status()
        return resp.json()

    async def list_resources(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List Slack channels."""
        resp = await self._client.get(
            "/conversations.list",
            params={"limit": kwargs.get("limit", 100)},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("channels", [])

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
