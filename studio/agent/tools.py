"""Agent tools — read-only operations available to the agent.

These tools are backed by ReadOnlyProvider instances ONLY.
No write operation can be expressed here because ReadOnlyProvider
has no mutating methods.
"""

from __future__ import annotations

from typing import Any

from studio.providers.base import ReadOnlyProvider


class AgentTools:
    """Read-only tools for the agent.

    Every tool here delegates to a ReadOnlyProvider method.
    The type system guarantees no write path exists.
    """

    def __init__(
        self,
        slack: ReadOnlyProvider,
        jira: ReadOnlyProvider,
        kb: ReadOnlyProvider | None = None,
    ) -> None:
        self._slack = slack
        self._jira = jira
        self._kb = kb

    async def search_slack(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search Slack messages (read-only)."""
        return await self._slack.search(query, max_results=max_results)

    async def get_thread(self, channel_id: str, thread_ts: str) -> dict[str, Any]:
        """Get a Slack thread (read-only)."""
        return await self._slack.get(channel_id, thread_ts=thread_ts)

    async def search_jira(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search Jira issues (read-only)."""
        return await self._jira.search(query, max_results=max_results)

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Get a Jira issue (read-only)."""
        return await self._jira.get(issue_key)

    async def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Get available transitions for an issue (read-only)."""
        if hasattr(self._jira, "get_transitions"):
            return await self._jira.get_transitions(issue_key)
        return await self._jira.list_resources(issue_key=issue_key)

    async def search_kb(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Search the knowledge base (read-only)."""
        if self._kb is None:
            return []
        return await self._kb.search(query, max_results=max_results)
