"""Jira write provider — lives exclusively in studio.executor.

Scopes required: write:jira-work
This is a WRITE scope. The agent process NEVER has access to this token.
"""

from __future__ import annotations

from typing import Any

import httpx

from studio.providers.base import WriteProvider


class JiraWriteProvider(WriteProvider):
    """Write-capable Jira API client.

    ONLY used by the executor. The agent process has no access to this
    client or its credentials.
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
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def execute_action(
        self,
        action_kind: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a Jira write action.

        Supported: jira.comment, jira.transition
        """
        if action_kind == "jira.comment":
            return await self._add_comment(payload)
        elif action_kind == "jira.transition":
            return await self._do_transition(payload)
        else:
            raise ValueError(f"Unsupported Jira action: {action_kind}")

    async def _add_comment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add a comment to a Jira issue."""
        issue_key = payload["issue_key"]
        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": payload["body"]}],
                    }
                ],
            }
        }
        resp = await self._client.post(f"/issue/{issue_key}/comment", json=body)
        resp.raise_for_status()
        return resp.json()

    async def _do_transition(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Transition a Jira issue to a new status."""
        issue_key = payload["issue_key"]
        body: dict[str, Any] = {
            "transition": {"id": payload["transition_id"]},
        }
        if payload.get("comment"):
            body["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": payload["comment"]}
                                        ],
                                    }
                                ],
                            }
                        }
                    }
                ]
            }
        if payload.get("fields"):
            body["fields"] = payload["fields"]

        resp = await self._client.post(f"/issue/{issue_key}/transitions", json=body)
        resp.raise_for_status()
        return {"status": "transitioned", "transition_id": payload["transition_id"]}

    async def verify_state(self, resource_id: str) -> dict[str, Any]:
        """Verify current state of a Jira issue."""
        resp = await self._client.get(f"/issue/{resource_id}")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
