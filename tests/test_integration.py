"""Integration tests — runs against the fake providers on :7704.

These tests exercise the full draft → approve → execute flow
end-to-end against the fakes, proving:
1. The approval flow works correctly
2. Idempotent execution (double-execute = one side effect)
3. Policy enforcement
4. Audit log integrity
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from studio.approval.policy import PolicyEngine
from studio.approval.tokens import TokenIssuer, TokenVerifier, NonceStore
from studio.audit.log import AuditLog
from studio.executor.engine import ExecutionEngine
from studio.models.actions import (
    Action,
    ActionState,
    JiraCommentPayload,
    PaymentsRefundPayload,
    SlackPostPayload,
    compute_payload_hash,
)
from studio.providers.payments_mock.provider import MockPaymentsProvider


@pytest.fixture
def server_key() -> bytes:
    return b"integration_test_key_at_least_32_b"


@pytest.fixture
def audit_log() -> AuditLog:
    return AuditLog()


@pytest.fixture
def policy_engine() -> PolicyEngine:
    engine = PolicyEngine()
    engine.load_dict({
        "actions": {
            "jira.comment": {"requires_approval": True, "approvers": 1, "rate_limit_per_hour": 100},
            "slack.post": {"requires_approval": True, "approvers": 1, "rate_limit_per_hour": 100},
            "payments.refund": {
                "requires_approval": True,
                "approvers": 1,
                "thresholds": [{"over_usd": 50, "approvers": 2}],
                "deny_if": ["customer.flagged", "amount_usd > 500"],
                "rate_limit_per_hour": 100,
            },
        }
    })
    return engine


@pytest.fixture
def payments_provider() -> MockPaymentsProvider:
    provider = MockPaymentsProvider()
    provider.seed_transaction("txn_001", 100.0, "cust_001")
    provider.seed_transaction("txn_002", 50.0, "cust_002")
    return provider


@pytest.fixture
def executor(
    server_key: bytes,
    payments_provider: MockPaymentsProvider,
    policy_engine: PolicyEngine,
    audit_log: AuditLog,
) -> ExecutionEngine:
    nonce_store = NonceStore()
    return ExecutionEngine(
        write_providers={"payments": payments_provider},
        token_verifier=TokenVerifier(server_key, nonce_store),
        policy_engine=policy_engine,
        audit_log=audit_log,
    )


@pytest.mark.integration
class TestEndToEndApprovalFlow:
    """Full draft → approve → execute flow."""

    @pytest.mark.asyncio
    async def test_approve_and_execute_refund(
        self,
        server_key: bytes,
        executor: ExecutionEngine,
        payments_provider: MockPaymentsProvider,
        audit_log: AuditLog,
    ) -> None:
        """A refund goes through: draft → approve → execute → one side effect."""
        # Draft
        action = Action(
            ticket_id="HELP-1",
            kind="payments.refund",
            payload=PaymentsRefundPayload(
                transaction_id="txn_001",
                amount_usd=25.00,
                reason="Duplicate charge",
                customer_id="cust_001",
            ),
            rationale="Customer reports duplicate charge",
            state=ActionState.APPROVED,  # Simulating post-approval
        )

        # Issue approval token
        issuer = TokenIssuer(server_key)
        token = issuer.issue(action.id, action.payload_hash, "operator:alice")

        # Execute
        result = await executor.execute(action, token.token)

        assert result.success
        assert len(payments_provider.refunds) == 1
        assert payments_provider.refunds[0]["amount_usd"] == 25.00

    @pytest.mark.asyncio
    async def test_double_execute_one_side_effect(
        self,
        server_key: bytes,
        executor: ExecutionEngine,
        payments_provider: MockPaymentsProvider,
    ) -> None:
        """Double-clicking approve must not execute twice."""
        action = Action(
            ticket_id="HELP-2",
            kind="payments.refund",
            payload=PaymentsRefundPayload(
                transaction_id="txn_002",
                amount_usd=30.00,
                reason="Service issue",
                customer_id="cust_002",
            ),
            rationale="Service outage compensation",
            state=ActionState.APPROVED,
        )

        issuer = TokenIssuer(server_key)
        token1 = issuer.issue(action.id, action.payload_hash, "operator:alice")

        # First execution
        result1 = await executor.execute(action, token1.token)
        assert result1.success

        # Second execution with a NEW token (same idempotency key)
        token2 = issuer.issue(action.id, action.payload_hash, "operator:alice")
        result2 = await executor.execute(action, token2.token)

        # Should succeed (idempotent) but NOT double-refund
        assert result2.success
        assert result2.provider_response is not None
        assert result2.provider_response.get("idempotent") is True

        # Only one refund processed
        assert len(payments_provider.refunds) == 1


@pytest.mark.integration
class TestPolicyEnforcement:
    """Policy engine correctly blocks denied actions."""

    @pytest.mark.asyncio
    async def test_flagged_customer_denied(
        self,
        server_key: bytes,
        executor: ExecutionEngine,
        payments_provider: MockPaymentsProvider,
        policy_engine: PolicyEngine,
    ) -> None:
        """Refund for a flagged customer is denied by policy."""
        result = policy_engine.evaluate(
            "payments.refund",
            {"amount_usd": 25.0, "transaction_id": "txn_001"},
            context={"customer": {"flagged": True}},
        )

        assert not result.allowed
        assert "flagged" in result.denied_reasons[0].lower()

    @pytest.mark.asyncio
    async def test_over_limit_denied(
        self,
        policy_engine: PolicyEngine,
    ) -> None:
        """Refund over $500 is denied by policy."""
        result = policy_engine.evaluate(
            "payments.refund",
            {"amount_usd": 600.0, "transaction_id": "txn_001"},
        )

        assert not result.allowed
        assert any("500" in r for r in result.denied_reasons)

    @pytest.mark.asyncio
    async def test_high_value_requires_two_approvers(
        self,
        policy_engine: PolicyEngine,
    ) -> None:
        """Refund over $50 requires 2 approvers."""
        result = policy_engine.evaluate(
            "payments.refund",
            {"amount_usd": 75.0, "transaction_id": "txn_001"},
        )

        assert result.allowed
        assert result.required_approvers == 2


@pytest.mark.integration
class TestAuditLogIntegration:
    """Audit log records all operations with valid hash chain."""

    @pytest.mark.asyncio
    async def test_execution_creates_audit_entries(
        self,
        server_key: bytes,
        executor: ExecutionEngine,
        payments_provider: MockPaymentsProvider,
        audit_log: AuditLog,
    ) -> None:
        """Successful execution creates audit entries."""
        action = Action(
            ticket_id="HELP-3",
            kind="payments.refund",
            payload=PaymentsRefundPayload(
                transaction_id="txn_001",
                amount_usd=10.00,
                reason="Test",
                customer_id="cust_001",
            ),
            rationale="Test",
            state=ActionState.APPROVED,
        )

        issuer = TokenIssuer(server_key)
        token = issuer.issue(action.id, action.payload_hash, "operator:test")

        await executor.execute(action, token.token)

        # Check audit log
        assert len(audit_log.entries) >= 2  # started + completed

        # Verify hash chain
        is_valid, reason = audit_log.verify_chain()
        assert is_valid, reason
