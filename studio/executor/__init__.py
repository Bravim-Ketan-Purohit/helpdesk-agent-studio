"""Executor module — the ONLY write-capable path.

Separate credentials, separate process. The executor:
1. Verifies the approval token (payload binding, expiry, single-use)
2. Re-checks policy
3. Executes idempotently
4. Records in the audit log

The agent module CANNOT import from here. Enforced by test.
"""

from studio.executor.engine import ExecutionEngine

__all__ = ["ExecutionEngine"]
