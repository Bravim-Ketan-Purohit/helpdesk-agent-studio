"""Base provider types enforcing the credential separation boundary.

ReadOnlyProvider: the ONLY provider type the agent module may use.
WriteProvider: lives exclusively in studio.executor. The agent module cannot
import or construct it — enforced by an import-graph test.

This is the structural guarantee that a jailbroken agent still cannot write,
because there is no code path to write with.
"""

from __future__ import annotations

import abc
from typing import Any


class ReadOnlyProvider(abc.ABC):
    """Base class for read-only provider access.

    Subclasses implement search, read, and list operations ONLY.
    No mutating method exists on this type — not suppressed, not hidden,
    not overridable. The method simply does not exist.
    """

    @abc.abstractmethod
    async def search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search provider resources."""
        ...

    @abc.abstractmethod
    async def get(self, resource_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a single resource by ID."""
        ...

    @abc.abstractmethod
    async def list_resources(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List resources matching filters."""
        ...


class WriteProvider(abc.ABC):
    """Base class for write-capable provider access.

    Lives EXCLUSIVELY in studio.executor. Never imported from studio.agent.
    Requires write credentials that the agent process does not possess.

    The import-graph test in tests/test_boundary.py asserts that no module
    under studio.agent can reach this type.
    """

    @abc.abstractmethod
    async def execute_action(
        self,
        action_kind: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a mutating action against the provider.

        Args:
            action_kind: The action type (e.g., 'jira.comment', 'slack.post')
            payload: The approved payload to execute
            idempotency_key: Unique key preventing double-execution

        Returns:
            Provider response with execution result
        """
        ...

    @abc.abstractmethod
    async def verify_state(self, resource_id: str) -> dict[str, Any]:
        """Verify current state of a resource before execution.

        Used to compute the live before/after diff shown to operators.
        """
        ...
