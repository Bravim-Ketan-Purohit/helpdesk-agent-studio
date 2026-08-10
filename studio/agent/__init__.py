"""Agent module — drafts proposed actions using READ-ONLY provider access.

CRITICAL INVARIANT: This module can NEVER construct, import, or access a
WriteProvider. The agent process has no write credentials — not in env,
not in config, not through a shared factory.

This is enforced by:
1. Type system: only ReadOnlyProvider is available here
2. Import graph test: tests/test_boundary.py asserts no path from
   studio.agent to studio.executor or WriteProvider
3. Runtime: agent process env has no write tokens

A jailbroken agent still cannot write because there is no code path to
write with.
"""
