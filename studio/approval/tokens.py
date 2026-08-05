"""Payload-bound, single-use, expiring approval tokens.

The approval token binds:
- action_id
- payload_sha256 (recomputed at execution time — mismatch = reject)
- approver_id (IdP subject ID)
- nonce (single-use, recorded in DB)
- issued_at + expires_at (5 min default)

Editing a draft invalidates the approval because the payload hash changes.
This is correct, not inconvenient.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class ApprovalToken:
    """An issued approval token — immutable after creation."""

    token: str
    action_id: uuid.UUID
    payload_hash: str
    approver_id: str
    nonce: str
    issued_at: datetime
    expires_at: datetime


class TokenIssuer:
    """Issues HMAC-based approval tokens bound to payload hashes.

    The server_key MUST come from environment/KMS, never hardcoded.
    """

    def __init__(self, server_key: bytes, ttl_seconds: int = 300) -> None:
        if len(server_key) < 32:
            raise ValueError("Server key must be at least 32 bytes")
        self._key = server_key
        self._ttl = ttl_seconds

    def issue(
        self,
        action_id: uuid.UUID,
        payload_hash: str,
        approver_id: str,
    ) -> ApprovalToken:
        """Issue a new approval token.

        Args:
            action_id: UUID of the action being approved
            payload_hash: SHA-256 of canonical JSON payload
            approver_id: IdP subject ID of the approver

        Returns:
            An ApprovalToken with HMAC signature
        """
        nonce = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self._ttl)

        token_data = self._token_data(action_id, payload_hash, approver_id, nonce, now, expires)
        signature = self._sign(token_data)

        token_str = f"{token_data}|{signature}"

        return ApprovalToken(
            token=token_str,
            action_id=action_id,
            payload_hash=payload_hash,
            approver_id=approver_id,
            nonce=nonce,
            issued_at=now,
            expires_at=expires,
        )

    def _token_data(
        self,
        action_id: uuid.UUID,
        payload_hash: str,
        approver_id: str,
        nonce: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> str:
        """Canonical token data string for signing."""
        parts = {
            "action_id": str(action_id),
            "payload_hash": payload_hash,
            "approver_id": approver_id,
            "nonce": nonce,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        return json.dumps(parts, sort_keys=True, separators=(",", ":"))

    def _sign(self, data: str) -> str:
        """HMAC-SHA256 signature."""
        return hmac.new(self._key, data.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class TokenVerificationResult:
    """Result of token verification."""

    valid: bool
    reason: str = ""
    action_id: uuid.UUID | None = None
    approver_id: str = ""


class NonceStore:
    """Abstract nonce store — subclass with a real DB backend."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def is_used(self, nonce: str) -> bool:
        """Check if a nonce has been consumed."""
        return nonce in self._used

    def mark_used(self, nonce: str) -> None:
        """Mark a nonce as consumed. Idempotent."""
        self._used.add(nonce)


class TokenVerifier:
    """Verifies approval tokens at execution time.

    Checks:
    1. Signature validity (HMAC)
    2. Expiry (token not expired)
    3. Single-use (nonce not previously consumed)
    4. Payload binding (hash matches current payload)
    """

    def __init__(self, server_key: bytes, nonce_store: NonceStore | None = None) -> None:
        if len(server_key) < 32:
            raise ValueError("Server key must be at least 32 bytes")
        self._key = server_key
        self._nonce_store = nonce_store or NonceStore()

    def verify(
        self,
        token_str: str,
        expected_payload_hash: str,
    ) -> TokenVerificationResult:
        """Verify an approval token against the current payload state.

        Args:
            token_str: The full token string (data|signature)
            expected_payload_hash: SHA-256 of the payload about to be executed

        Returns:
            TokenVerificationResult with validity and reason
        """
        # Parse token
        parts = token_str.rsplit("|", 1)
        if len(parts) != 2:
            return TokenVerificationResult(valid=False, reason="Malformed token")

        token_data, signature = parts

        # Verify signature
        expected_sig = hmac.new(self._key, token_data.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return TokenVerificationResult(valid=False, reason="Invalid signature")

        # Parse token data
        try:
            data = json.loads(token_data)
        except json.JSONDecodeError:
            return TokenVerificationResult(valid=False, reason="Corrupt token data")

        # Check expiry
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return TokenVerificationResult(valid=False, reason="Token expired")

        # Check nonce (single-use)
        nonce = data["nonce"]
        if self._nonce_store.is_used(nonce):
            return TokenVerificationResult(valid=False, reason="Token already used (replay)")

        # Check payload binding — the critical check
        if data["payload_hash"] != expected_payload_hash:
            return TokenVerificationResult(
                valid=False,
                reason="Payload hash mismatch — payload was modified after approval",
            )

        # All checks pass — consume the nonce
        self._nonce_store.mark_used(nonce)

        return TokenVerificationResult(
            valid=True,
            action_id=uuid.UUID(data["action_id"]),
            approver_id=data["approver_id"],
        )
