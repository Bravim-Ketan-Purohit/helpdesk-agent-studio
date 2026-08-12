"""MCP server — read-only tools, by construction.

Exposes the agent's read-only capabilities as Model Context Protocol tools.
Built on ReadOnlyProvider types — no write method exists to expose.

Hard rule: NO write tools over MCP. Ever. Not gated, not flagged, not admin-only.
The MCP server is built on ReadOnlyProvider types, so there is no write method
to expose — keep it that way.
"""
