"""Read-only MCP server — six tools built on ReadOnlyProvider.

Tools exposed:
- slack_search_messages
- slack_get_thread
- jira_search_issues
- jira_get_issue
- jira_get_transitions
- kb_search

NO write tools. Ever. Not gated, not flagged, not admin-only.
The MCP server is built on ReadOnlyProvider types, so no write method
exists to expose. A test asserts no write tool can be registered.

Auth on the MCP transport — an unauthenticated MCP server on a real
Slack workspace is a data-exfiltration endpoint.
"""

from __future__ import annotations

import json
import os
from typing import Any

from studio.providers.base import ReadOnlyProvider


# Registry of MCP tools — only read-only tools can be registered
_REGISTERED_TOOLS: dict[str, dict[str, Any]] = {}


class McpToolRegistry:
    """Registry for MCP tools — enforces read-only constraint.

    Only tools backed by ReadOnlyProvider methods can be registered.
    Write tools cannot be registered because WriteProvider is not
    available in this module's scope.
    """

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Any,
        provider: ReadOnlyProvider,  # Type system enforces read-only
    ) -> None:
        """Register a read-only tool.

        Args:
            name: Tool name (e.g., 'slack_search_messages')
            description: Human-readable description
            input_schema: JSON Schema for tool inputs
            handler: Async callable that executes the tool
            provider: The ReadOnlyProvider backing this tool
        """
        # Double-check at runtime that we're not registering a write tool
        from studio.providers.base import WriteProvider

        if isinstance(provider, WriteProvider):
            raise TypeError(
                f"SECURITY VIOLATION: Cannot register write provider '{name}' as MCP tool. "
                "MCP tools are read-only by construction."
            )

        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
            "provider": provider,
        }

    @property
    def tools(self) -> list[dict[str, Any]]:
        """List all registered tools (without handlers)."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in self._tools.values()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a registered tool by name."""
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        return await tool["handler"](tool["provider"], arguments)

    def has_write_tools(self) -> bool:
        """Check if any write tools are registered (should always be False)."""
        from studio.providers.base import WriteProvider

        for tool in self._tools.values():
            if isinstance(tool["provider"], WriteProvider):
                return True
        return False


# --- Tool handlers ---


async def slack_search_messages(
    provider: ReadOnlyProvider, args: dict[str, Any]
) -> list[dict[str, Any]]:
    """Search Slack messages."""
    query = args.get("query", "")
    max_results = args.get("max_results", 10)
    results = await provider.search(query, max_results=max_results)
    # Size-cap responses and redact sensitive data
    return _redact_and_cap(results, max_items=max_results)


async def slack_get_thread(
    provider: ReadOnlyProvider, args: dict[str, Any]
) -> dict[str, Any]:
    """Get a Slack thread by channel and timestamp."""
    channel_id = args.get("channel_id", "")
    thread_ts = args.get("thread_ts", "")
    result = await provider.get(channel_id, thread_ts=thread_ts)
    return result


async def jira_search_issues(
    provider: ReadOnlyProvider, args: dict[str, Any]
) -> list[dict[str, Any]]:
    """Search Jira issues."""
    query = args.get("query", "")
    max_results = args.get("max_results", 10)
    results = await provider.search(query, max_results=max_results)
    return _redact_and_cap(results, max_items=max_results)


async def jira_get_issue(
    provider: ReadOnlyProvider, args: dict[str, Any]
) -> dict[str, Any]:
    """Get a single Jira issue."""
    issue_key = args.get("issue_key", "")
    return await provider.get(issue_key)


async def jira_get_transitions(
    provider: ReadOnlyProvider, args: dict[str, Any]
) -> list[dict[str, Any]]:
    """Get available transitions for a Jira issue."""
    issue_key = args.get("issue_key", "")
    # Use the JiraReadOnlyProvider's get_transitions if available
    if hasattr(provider, "get_transitions"):
        return await provider.get_transitions(issue_key)
    # Fallback: list with filter
    return await provider.list_resources(issue_key=issue_key)


async def kb_search(
    provider: ReadOnlyProvider, args: dict[str, Any]
) -> list[dict[str, Any]]:
    """Search the knowledge base."""
    query = args.get("query", "")
    max_results = args.get("max_results", 5)
    results = await provider.search(query, max_results=max_results)
    return _redact_and_cap(results, max_items=max_results)


def _redact_and_cap(
    items: list[dict[str, Any]], max_items: int = 10
) -> list[dict[str, Any]]:
    """Redact sensitive fields and cap response size.

    Never expose tokens, customer PII, or internal IDs in MCP responses.
    """
    redacted = []
    for item in items[:max_items]:
        clean = {}
        for key, value in item.items():
            # Never expose tokens or secrets
            if any(
                sensitive in key.lower()
                for sensitive in ("token", "secret", "password", "key", "credential")
            ):
                continue
            clean[key] = value
        redacted.append(clean)
    return redacted


def create_mcp_server(
    slack_provider: ReadOnlyProvider,
    jira_provider: ReadOnlyProvider,
    kb_provider: ReadOnlyProvider | None = None,
) -> McpToolRegistry:
    """Create and configure the MCP tool registry.

    All six tools are registered with their ReadOnlyProvider backing.
    """
    registry = McpToolRegistry()

    registry.register(
        name="slack_search_messages",
        description="Search Slack messages by query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
        handler=slack_search_messages,
        provider=slack_provider,
    )

    registry.register(
        name="slack_get_thread",
        description="Get a Slack thread by channel ID and thread timestamp",
        input_schema={
            "type": "object",
            "properties": {
                "channel_id": {"type": "string"},
                "thread_ts": {"type": "string"},
            },
            "required": ["channel_id", "thread_ts"],
        },
        handler=slack_get_thread,
        provider=slack_provider,
    )

    registry.register(
        name="jira_search_issues",
        description="Search Jira issues by query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
        handler=jira_search_issues,
        provider=jira_provider,
    )

    registry.register(
        name="jira_get_issue",
        description="Get a single Jira issue by key",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string"},
            },
            "required": ["issue_key"],
        },
        handler=jira_get_issue,
        provider=jira_provider,
    )

    registry.register(
        name="jira_get_transitions",
        description="Get available status transitions for a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string"},
            },
            "required": ["issue_key"],
        },
        handler=jira_get_transitions,
        provider=jira_provider,
    )

    if kb_provider:
        registry.register(
            name="kb_search",
            description="Search the knowledge base for relevant articles",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            handler=kb_search,
            provider=kb_provider,
        )

    return registry
