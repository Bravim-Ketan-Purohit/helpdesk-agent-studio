"""MCP boundary tests — no write tool can be registered.

Hard rule: No write tools over MCP. Ever. Not gated, not flagged, not admin-only.
"""

from __future__ import annotations

import pytest

from studio.mcp.server import McpToolRegistry, create_mcp_server
from studio.providers.base import ReadOnlyProvider, WriteProvider


class FakeReadProvider(ReadOnlyProvider):
    """Fake read-only provider for testing."""

    async def search(self, query, **kwargs):
        return [{"result": "test"}]

    async def get(self, resource_id, **kwargs):
        return {"id": resource_id}

    async def list_resources(self, **kwargs):
        return []


class FakeWriteProvider(WriteProvider):
    """Fake write provider for testing the boundary."""

    async def execute_action(self, action_kind, payload, idempotency_key):
        return {"executed": True}

    async def verify_state(self, resource_id):
        return {"state": "test"}


@pytest.mark.boundary
class TestMcpNoWriteTools:
    """The MCP server must never register write tools."""

    def test_cannot_register_write_provider(self) -> None:
        """Attempting to register a WriteProvider as an MCP tool must raise TypeError."""
        registry = McpToolRegistry()
        write_provider = FakeWriteProvider()

        with pytest.raises(TypeError, match="SECURITY VIOLATION"):
            registry.register(
                name="dangerous_write_tool",
                description="This should never work",
                input_schema={"type": "object"},
                handler=lambda p, a: None,
                provider=write_provider,  # type: ignore — intentionally wrong
            )

    def test_registry_has_no_write_tools(self) -> None:
        """A properly configured MCP server has no write tools."""
        read_provider = FakeReadProvider()
        registry = create_mcp_server(
            slack_provider=read_provider,
            jira_provider=read_provider,
            kb_provider=read_provider,
        )

        assert not registry.has_write_tools()

    def test_all_registered_tools_are_read_only(self) -> None:
        """Every tool in the registry is backed by a ReadOnlyProvider."""
        read_provider = FakeReadProvider()
        registry = create_mcp_server(
            slack_provider=read_provider,
            jira_provider=read_provider,
        )

        # Should have 5 tools (no kb_search without kb_provider)
        tools = registry.tools
        assert len(tools) == 5

        # All tool names should be read operations
        for tool in tools:
            name = tool["name"]
            assert not any(
                write_word in name
                for write_word in ("write", "create", "update", "delete", "post", "transition")
            ), f"Tool '{name}' looks like a write operation"

    def test_mcp_server_six_tools_with_kb(self) -> None:
        """Full MCP server has exactly 6 read-only tools."""
        read_provider = FakeReadProvider()
        registry = create_mcp_server(
            slack_provider=read_provider,
            jira_provider=read_provider,
            kb_provider=read_provider,
        )

        tools = registry.tools
        assert len(tools) == 6
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "slack_search_messages",
            "slack_get_thread",
            "jira_search_issues",
            "jira_get_issue",
            "jira_get_transitions",
            "kb_search",
        }
