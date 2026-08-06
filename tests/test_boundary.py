"""Boundary tests — the tests that prove the agent cannot write.

These are the most important tests in the project. They must be green
before any execution path is written. They verify the structural guarantee
that the agent module has no code path to mutate provider state.

Mark: boundary
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# Root of the studio package
STUDIO_ROOT = Path(__file__).parent.parent / "studio"
AGENT_ROOT = STUDIO_ROOT / "agent"
EXECUTOR_ROOT = STUDIO_ROOT / "executor"


@pytest.mark.boundary
class TestAgentCannotImportWriteProvider:
    """The agent module must never import or access WriteProvider."""

    def test_agent_module_does_not_import_write_provider(self) -> None:
        """Parse all agent module source files and assert no import of WriteProvider."""
        agent_files = list(AGENT_ROOT.rglob("*.py"))
        assert agent_files, "No Python files found in studio/agent/"

        violations: list[str] = []
        for filepath in agent_files:
            source = filepath.read_text()
            tree = ast.parse(source, filename=str(filepath))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    # Check direct imports from executor or WriteProvider
                    module = node.module or ""
                    if "executor" in module or "WriteProvider" in module:
                        violations.append(
                            f"{filepath.relative_to(STUDIO_ROOT)}: "
                            f"imports from '{module}'"
                        )
                    # Check imported names
                    for alias in node.names:
                        if alias.name == "WriteProvider":
                            violations.append(
                                f"{filepath.relative_to(STUDIO_ROOT)}: "
                                f"imports 'WriteProvider' from '{module}'"
                            )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if "executor" in alias.name or "WriteProvider" in alias.name:
                            violations.append(
                                f"{filepath.relative_to(STUDIO_ROOT)}: "
                                f"imports '{alias.name}'"
                            )

        assert not violations, (
            "Agent module imports executor/WriteProvider — boundary violated!\n"
            + "\n".join(violations)
        )

    def test_agent_module_does_not_import_executor(self) -> None:
        """The agent module must not import anything from studio.executor."""
        agent_files = list(AGENT_ROOT.rglob("*.py"))

        violations: list[str] = []
        for filepath in agent_files:
            source = filepath.read_text()
            tree = ast.parse(source, filename=str(filepath))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.startswith("studio.executor"):
                        violations.append(
                            f"{filepath.relative_to(STUDIO_ROOT)}: "
                            f"imports from '{module}'"
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("studio.executor"):
                            violations.append(
                                f"{filepath.relative_to(STUDIO_ROOT)}: "
                                f"imports '{alias.name}'"
                            )

        assert not violations, (
            "Agent module imports from studio.executor — boundary violated!\n"
            + "\n".join(violations)
        )

    def test_read_only_provider_has_no_mutating_methods(self) -> None:
        """ReadOnlyProvider must not have any method that can mutate state."""
        from studio.providers.base import ReadOnlyProvider

        mutating_prefixes = (
            "write", "create", "update", "delete", "post", "put",
            "patch", "remove", "execute", "mutate", "send", "transition",
        )

        methods = [
            name for name in dir(ReadOnlyProvider)
            if not name.startswith("_")
            and callable(getattr(ReadOnlyProvider, name, None))
        ]

        violations = [
            m for m in methods
            if m.startswith(mutating_prefixes)
        ]

        assert not violations, (
            f"ReadOnlyProvider has mutating methods: {violations}"
        )

    def test_write_provider_not_constructible_from_agent(self) -> None:
        """Importing studio.agent should not give access to WriteProvider."""
        import studio.agent

        # Check that WriteProvider is not accessible from agent's namespace
        agent_attrs = dir(studio.agent)
        assert "WriteProvider" not in agent_attrs
        assert "ExecutionEngine" not in agent_attrs

    def test_agent_drafter_only_accepts_read_only_provider(self) -> None:
        """ActionDrafter constructor only accepts ReadOnlyProvider instances."""
        from studio.agent.drafter import ActionDrafter
        from studio.providers.base import ReadOnlyProvider

        sig = inspect.signature(ActionDrafter.__init__)
        params = sig.parameters

        # All provider params should be typed as ReadOnlyProvider
        for name, param in params.items():
            if name == "self":
                continue
            annotation = param.annotation
            if annotation != inspect.Parameter.empty:
                # Should reference ReadOnlyProvider, not WriteProvider
                ann_str = str(annotation)
                assert "WriteProvider" not in ann_str, (
                    f"ActionDrafter.__init__ param '{name}' references WriteProvider"
                )


@pytest.mark.boundary
class TestApprovalTokenBinding:
    """Approval tokens must be bound to the payload hash."""

    def test_token_rejects_modified_payload(self) -> None:
        """A token issued for one payload must reject a different payload hash."""
        from studio.approval.tokens import TokenIssuer, TokenVerifier
        import uuid

        key = b"x" * 32
        issuer = TokenIssuer(key)
        verifier = TokenVerifier(key)

        action_id = uuid.uuid4()
        original_hash = "a" * 64  # Original payload hash
        modified_hash = "b" * 64  # Modified payload hash

        token = issuer.issue(action_id, original_hash, "approver-1")
        result = verifier.verify(token.token, modified_hash)

        assert not result.valid
        assert "mismatch" in result.reason.lower() or "modified" in result.reason.lower()

    def test_token_single_use(self) -> None:
        """A token can only be used once — replay is rejected."""
        from studio.approval.tokens import TokenIssuer, TokenVerifier
        import uuid

        key = b"x" * 32
        issuer = TokenIssuer(key)
        verifier = TokenVerifier(key)

        action_id = uuid.uuid4()
        payload_hash = "a" * 64

        token = issuer.issue(action_id, payload_hash, "approver-1")

        # First use — should succeed
        result1 = verifier.verify(token.token, payload_hash)
        assert result1.valid

        # Second use — should be rejected (replay)
        result2 = verifier.verify(token.token, payload_hash)
        assert not result2.valid
        assert "replay" in result2.reason.lower() or "used" in result2.reason.lower()

    def test_token_expiry(self) -> None:
        """An expired token must be rejected."""
        from studio.approval.tokens import TokenIssuer, TokenVerifier
        import uuid

        key = b"x" * 32
        # Issue with 0 second TTL — immediately expired
        issuer = TokenIssuer(key, ttl_seconds=0)
        verifier = TokenVerifier(key)

        action_id = uuid.uuid4()
        payload_hash = "a" * 64

        token = issuer.issue(action_id, payload_hash, "approver-1")

        import time
        time.sleep(0.01)  # Ensure expiry

        result = verifier.verify(token.token, payload_hash)
        assert not result.valid
        assert "expired" in result.reason.lower()

    def test_token_invalid_signature(self) -> None:
        """A token with wrong key must be rejected."""
        from studio.approval.tokens import TokenIssuer, TokenVerifier
        import uuid

        key1 = b"x" * 32
        key2 = b"y" * 32
        issuer = TokenIssuer(key1)
        verifier = TokenVerifier(key2)  # Different key

        action_id = uuid.uuid4()
        payload_hash = "a" * 64

        token = issuer.issue(action_id, payload_hash, "approver-1")
        result = verifier.verify(token.token, payload_hash)

        assert not result.valid
        assert "signature" in result.reason.lower() or "invalid" in result.reason.lower()


@pytest.mark.boundary
class TestExecutorRejectsUnapproved:
    """The executor must reject any action not in APPROVED state."""

    @pytest.mark.asyncio
    async def test_executor_rejects_drafted_action(self) -> None:
        """Executor must refuse to execute a DRAFTED action."""
        from studio.approval.tokens import TokenIssuer, TokenVerifier
        from studio.approval.policy import PolicyEngine
        from studio.audit.log import AuditLog
        from studio.executor.engine import ExecutionEngine
        from studio.models.actions import Action, ActionState, JiraCommentPayload
        import uuid

        key = b"x" * 32
        audit = AuditLog()
        engine = ExecutionEngine(
            write_providers={},
            token_verifier=TokenVerifier(key),
            policy_engine=PolicyEngine(),
            audit_log=audit,
        )

        action = Action(
            ticket_id="HELP-1",
            kind="jira.comment",
            payload=JiraCommentPayload(issue_key="HELP-1", body="test"),
            rationale="test",
            state=ActionState.DRAFTED,  # Not approved!
        )

        issuer = TokenIssuer(key)
        token = issuer.issue(action.id, action.payload_hash, "approver-1")

        result = await engine.execute(action, token.token)
        assert not result.success
        assert "APPROVED" in result.error or "approved" in result.error


@pytest.mark.boundary
class TestAuditLogIntegrity:
    """Audit log must be append-only with valid hash chain."""

    def test_hash_chain_valid(self) -> None:
        """Hash chain must verify after multiple appends."""
        from studio.audit.log import AuditLog
        import uuid

        log = AuditLog()
        for i in range(10):
            log.append(
                actor="system",
                event=f"test.event.{i}",
                detail={"index": i},
                action_id=uuid.uuid4(),
            )

        is_valid, reason = log.verify_chain()
        assert is_valid, reason

    def test_tampered_entry_detected(self) -> None:
        """Modifying an entry must break chain verification."""
        from studio.audit.log import AuditLog
        import uuid

        log = AuditLog()
        for i in range(5):
            log.append(
                actor="system",
                event=f"test.event.{i}",
                detail={"index": i},
            )

        # Tamper with an entry (replace with a different detail)
        original = log._entries[2]
        tampered = type(original)(
            seq=original.seq,
            at=original.at,
            actor=original.actor,
            event=original.event,
            action_id=original.action_id,
            detail={"index": 999, "tampered": True},  # Modified!
            prev_hash=original.prev_hash,
            hash=original.hash,  # Hash no longer matches
        )
        log._entries[2] = tampered

        is_valid, reason = log.verify_chain()
        assert not is_valid
        assert "mismatch" in reason.lower() or "broken" in reason.lower()
