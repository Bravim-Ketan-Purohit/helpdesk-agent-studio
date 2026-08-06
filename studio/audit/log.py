"""Append-only, hash-chained audit log.

Every state change, approval, execution, and failure is recorded here.
The hash chain ensures tamper evidence — each entry includes the hash of
the previous entry, so any deletion or modification breaks the chain.

Never log tokens, access codes, or customer PII.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    """A single audit log entry — immutable after creation."""

    seq: int
    at: datetime
    actor: str  # agent | operator:<id> | executor | system
    event: str
    action_id: uuid.UUID | None
    detail: dict[str, Any]
    prev_hash: str
    hash: str


class AuditLog:
    """Append-only audit log with hash chain verification.

    In production, backed by Postgres with no UPDATE/DELETE grants.
    This implementation provides the in-memory interface and hash chain logic.
    """

    GENESIS_HASH = "0" * 64  # SHA-256 of nothing — the chain anchor

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._last_hash: str = self.GENESIS_HASH
        self._seq: int = 0

    @property
    def entries(self) -> list[AuditEntry]:
        """Return all entries (read-only view)."""
        return list(self._entries)

    @property
    def last_hash(self) -> str:
        """Hash of the most recent entry."""
        return self._last_hash

    def append(
        self,
        actor: str,
        event: str,
        detail: dict[str, Any],
        action_id: uuid.UUID | None = None,
    ) -> AuditEntry:
        """Append a new entry to the audit log.

        Args:
            actor: Who performed the action (agent, operator:<id>, executor, system)
            event: Event type (e.g., 'action.drafted', 'action.approved', 'action.executed')
            detail: Event details (NEVER include tokens or customer PII)
            action_id: Optional UUID of the related action

        Returns:
            The created AuditEntry with its hash
        """
        self._seq += 1
        now = datetime.now(timezone.utc)

        # Compute hash: H(seq || at || actor || event || action_id || detail || prev_hash)
        hash_input = self._hash_input(
            seq=self._seq,
            at=now,
            actor=actor,
            event=event,
            action_id=action_id,
            detail=detail,
            prev_hash=self._last_hash,
        )
        entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        entry = AuditEntry(
            seq=self._seq,
            at=now,
            actor=actor,
            event=event,
            action_id=action_id,
            detail=detail,
            prev_hash=self._last_hash,
            hash=entry_hash,
        )

        self._entries.append(entry)
        self._last_hash = entry_hash
        return entry

    def verify_chain(self) -> tuple[bool, str]:
        """Verify the integrity of the entire hash chain.

        Returns:
            (is_valid, reason) — True if chain is intact, else False with explanation
        """
        if not self._entries:
            return True, "Empty log"

        prev_hash = self.GENESIS_HASH
        for entry in self._entries:
            if entry.prev_hash != prev_hash:
                return False, (
                    f"Chain broken at seq {entry.seq}: "
                    f"expected prev_hash {prev_hash[:16]}..., "
                    f"got {entry.prev_hash[:16]}..."
                )

            expected_hash = hashlib.sha256(
                self._hash_input(
                    seq=entry.seq,
                    at=entry.at,
                    actor=entry.actor,
                    event=entry.event,
                    action_id=entry.action_id,
                    detail=entry.detail,
                    prev_hash=entry.prev_hash,
                ).encode()
            ).hexdigest()

            if entry.hash != expected_hash:
                return False, (
                    f"Hash mismatch at seq {entry.seq}: "
                    f"expected {expected_hash[:16]}..., got {entry.hash[:16]}..."
                )

            prev_hash = entry.hash

        return True, f"Chain valid: {len(self._entries)} entries"

    @staticmethod
    def _hash_input(
        seq: int,
        at: datetime,
        actor: str,
        event: str,
        action_id: uuid.UUID | None,
        detail: dict[str, Any],
        prev_hash: str,
    ) -> str:
        """Canonical input for hash computation."""
        data = {
            "seq": seq,
            "at": at.isoformat(),
            "actor": actor,
            "event": event,
            "action_id": str(action_id) if action_id else None,
            "detail": detail,
            "prev_hash": prev_hash,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
