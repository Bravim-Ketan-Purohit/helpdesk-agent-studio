"""Execution engine — idempotent, audited, approval-gated.

Nothing executes without a valid, unexpired, single-use approval token
bound to the payload hash. No bypass flag, no --force, no dev shortcut.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from studio.approval.policy import PolicyEngine, PolicyResult
from studio.approval.tokens import TokenVerifier, TokenVerificationResult
from studio.audit.log import AuditLog
from studio.models.actions import Action, ActionState, compute_payload_hash
from studio.providers.base import WriteProvider


@dataclass
class ExecutionResult:
    """Result of an execution attempt."""

    success: bool
    action_id: uuid.UUID
    provider_response: dict[str, Any] | None = None
    error: str | None = None


class ExecutionEngine:
    """Executes approved actions through write providers.

    Pre-conditions checked before every execution:
    1. Action is in APPROVED state
    2. Approval token is valid (signature, expiry, nonce, payload hash)
    3. Policy still allows the action (re-evaluated at execution time)
    4. Idempotency key has not been used

    On failure: action returns to FAILED state, visible to the operator.
    Never silent failure.
    """

    def __init__(
        self,
        write_providers: dict[str, WriteProvider],
        token_verifier: TokenVerifier,
        policy_engine: PolicyEngine,
        audit_log: AuditLog,
    ) -> None:
        self._providers = write_providers
        self._verifier = token_verifier
        self._policy = policy_engine
        self._audit = audit_log
        self._executed_keys: set[str] = set()

    async def execute(
        self,
        action: Action,
        approval_token: str,
    ) -> ExecutionResult:
        """Execute an approved action.

        Args:
            action: The action to execute (must be in APPROVED state)
            approval_token: The approval token string

        Returns:
            ExecutionResult indicating success or failure
        """
        # Check 1: Action must be in APPROVED state
        if action.state != ActionState.APPROVED:
            self._audit.append(
                actor="executor",
                event="execution.rejected",
                action_id=action.id,
                detail={"reason": f"Action in state {action.state.value}, expected approved"},
            )
            return ExecutionResult(
                success=False,
                action_id=action.id,
                error=f"Action must be in APPROVED state, got {action.state.value}",
            )

        # Check 2: Verify approval token
        current_hash = compute_payload_hash(action.payload)
        verification = self._verifier.verify(approval_token, current_hash)

        if not verification.valid:
            self._audit.append(
                actor="executor",
                event="execution.token_rejected",
                action_id=action.id,
                detail={"reason": verification.reason},
            )
            return ExecutionResult(
                success=False,
                action_id=action.id,
                error=f"Token verification failed: {verification.reason}",
            )

        # Check 3: Re-evaluate policy at execution time
        policy_result = self._policy.evaluate(
            action.kind, action.payload.model_dump()
        )
        if not policy_result.allowed:
            self._audit.append(
                actor="executor",
                event="execution.policy_denied",
                action_id=action.id,
                detail={"reasons": policy_result.denied_reasons},
            )
            return ExecutionResult(
                success=False,
                action_id=action.id,
                error=f"Policy denied: {', '.join(policy_result.denied_reasons)}",
            )

        # Check 4: Idempotency — same key must not execute twice
        if action.idempotency_key in self._executed_keys:
            self._audit.append(
                actor="executor",
                event="execution.duplicate_blocked",
                action_id=action.id,
                detail={"idempotency_key": action.idempotency_key},
            )
            return ExecutionResult(
                success=True,  # Idempotent — report success without re-executing
                action_id=action.id,
                provider_response={"idempotent": True, "already_executed": True},
            )

        # Determine provider
        provider_name = action.kind.split(".")[0]  # e.g., "jira" from "jira.comment"
        provider = self._providers.get(provider_name)
        if provider is None:
            self._audit.append(
                actor="executor",
                event="execution.no_provider",
                action_id=action.id,
                detail={"provider": provider_name},
            )
            return ExecutionResult(
                success=False,
                action_id=action.id,
                error=f"No write provider registered for '{provider_name}'",
            )

        # Execute
        action.state = ActionState.EXECUTING
        self._audit.append(
            actor="executor",
            event="execution.started",
            action_id=action.id,
            detail={"kind": action.kind, "idempotency_key": action.idempotency_key},
        )

        try:
            response = await provider.execute_action(
                action_kind=action.kind,
                payload=action.payload.model_dump(),
                idempotency_key=action.idempotency_key,
            )
        except Exception as e:
            action.state = ActionState.FAILED
            self._audit.append(
                actor="executor",
                event="execution.failed",
                action_id=action.id,
                detail={"error": str(e), "kind": action.kind},
            )
            return ExecutionResult(
                success=False,
                action_id=action.id,
                error=str(e),
            )

        # Success
        action.state = ActionState.EXECUTED
        self._executed_keys.add(action.idempotency_key)
        self._audit.append(
            actor="executor",
            event="execution.completed",
            action_id=action.id,
            detail={
                "kind": action.kind,
                "provider_response_keys": list(response.keys()) if response else [],
            },
        )

        return ExecutionResult(
            success=True,
            action_id=action.id,
            provider_response=response,
        )
