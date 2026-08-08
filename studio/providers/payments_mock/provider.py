"""Mock payments provider implementation.

NEVER real money. This is the only payments provider that will ever exist
in this repository. No Stripe, no PayPal, no Adyen — not even in test mode
with a real account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from studio.providers.base import WriteProvider


@dataclass
class MockTransaction:
    """A mock transaction record."""

    id: str
    amount_usd: float
    customer_id: str
    status: str = "completed"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    refunds: list[dict[str, Any]] = field(default_factory=list)


class MockPaymentsProvider(WriteProvider):
    """Mock payments provider for development and testing.

    Records refunds in memory. Never touches real money.
    Supports idempotent execution via idempotency_key tracking.
    """

    def __init__(self) -> None:
        self._transactions: dict[str, MockTransaction] = {}
        self._executed_keys: set[str] = set()
        self._refunds: list[dict[str, Any]] = []

    def seed_transaction(
        self,
        transaction_id: str,
        amount_usd: float,
        customer_id: str,
    ) -> MockTransaction:
        """Seed a mock transaction for testing."""
        txn = MockTransaction(
            id=transaction_id,
            amount_usd=amount_usd,
            customer_id=customer_id,
        )
        self._transactions[transaction_id] = txn
        return txn

    async def execute_action(
        self,
        action_kind: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a mock payments action.

        Supported: payments.refund
        """
        if action_kind != "payments.refund":
            raise ValueError(f"Unsupported payments action: {action_kind}")

        # Idempotency check
        if idempotency_key in self._executed_keys:
            return {
                "idempotent": True,
                "already_executed": True,
                "refund_id": f"ref_{idempotency_key[:8]}",
            }

        transaction_id = payload["transaction_id"]
        amount_usd = payload["amount_usd"]
        customer_id = payload["customer_id"]
        reason = payload.get("reason", "")

        # Verify transaction exists
        txn = self._transactions.get(transaction_id)
        if txn is None:
            raise ValueError(f"Transaction {transaction_id} not found")

        # Verify amount doesn't exceed original
        total_refunded = sum(r["amount_usd"] for r in txn.refunds)
        if total_refunded + amount_usd > txn.amount_usd:
            raise ValueError(
                f"Refund of ${amount_usd} would exceed transaction amount "
                f"(${txn.amount_usd}, already refunded: ${total_refunded})"
            )

        # Process the mock refund
        refund_id = f"ref_{uuid.uuid4().hex[:12]}"
        refund_record = {
            "refund_id": refund_id,
            "transaction_id": transaction_id,
            "amount_usd": amount_usd,
            "customer_id": customer_id,
            "reason": reason,
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        txn.refunds.append(refund_record)
        self._refunds.append(refund_record)
        self._executed_keys.add(idempotency_key)

        return refund_record

    async def verify_state(self, resource_id: str) -> dict[str, Any]:
        """Verify current state of a transaction."""
        txn = self._transactions.get(resource_id)
        if txn is None:
            return {"error": "not_found"}
        return {
            "id": txn.id,
            "amount_usd": txn.amount_usd,
            "customer_id": txn.customer_id,
            "status": txn.status,
            "total_refunded": sum(r["amount_usd"] for r in txn.refunds),
            "refund_count": len(txn.refunds),
        }

    @property
    def refunds(self) -> list[dict[str, Any]]:
        """All processed refunds (for testing assertions)."""
        return list(self._refunds)
