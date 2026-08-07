"""Jira read-only provider — search, get, and list operations only.

Scopes required: read:jira-work, read:jira-user
These are read-only scopes. No write scope is available to this client.
"""

from __future__ import annotations

from typing import Any

import httpx

from studio.providers.base import ReadOnlyProvider


class JiraReadOnlyProvider(ReadOnlyProvider):
    """Read-only Jira API client.

    This client can ONLY search and read. It uses OAuth 2.0 3LO with
    read-only scopes. The write client is a separate OAuth installation
    with different credentials.
    """

    def __init__(
        self,
        access_token: str,
        cloud_id: str,
        base_url: str | None = None,
    ) -> None:
        self._token = access_token
        self._cloud_id = cloud_id
        self._base_url = base_url or f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search Jira issues using JQL."""
        max_results = kwargs.get("max_results", 20)
        jql = kwargs.get("jql", f'text ~ "{query}"')
        resp = await self._client.get(
            "/search",
            params={"jql": jql, "maxResults": max_results},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "key": issue["key"],
                "summary": issue["fields"].get("summary", ""),
                "status": issue["fields"].get("status", {}).get("name", ""),
                "assignee": issue["fields"].get("assignee", {}).get("displayName", ""),
                "priority": issue["fields"].get("priority", {}).get("name", ""),
            }
            for issue in data.get("issues", [])
        ]

    async def get(self, resource_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a single Jira issue by key."""
        resp = await self._client.get(f"/issue/{resource_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Get available transitions for an issue."""
        resp = await self._client.get(f"/issue/{issue_key}/transitions")
        resp.raise_for_status()
        data = resp.json()
        return data.get("transitions", [])

    async def list_resources(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List Jira projects."""
        resp = await self._client.get("/project")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
