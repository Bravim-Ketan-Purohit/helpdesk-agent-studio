"""Audit log routes — read-only access to the append-only audit trail."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class AuditEntryResponse(BaseModel):
    """Audit entry response model."""

    seq: int
    at: str
    actor: str
    event: str
    action_id: str | None
    detail: dict[str, Any]
    prev_hash: str
    hash: str


class ChainVerificationResponse(BaseModel):
    """Hash chain verification result."""

    valid: bool
    reason: str
    entry_count: int


@router.get("")
async def list_audit_entries(
    request: Request,
    action_id: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEntryResponse]:
    """List audit log entries with optional filters."""
    studio = request.app.state.studio
    entries = studio.audit_log.entries

    if action_id:
        entries = [e for e in entries if str(e.action_id) == action_id]
    if actor:
        entries = [e for e in entries if e.actor == actor]

    entries = entries[offset : offset + limit]

    return [
        AuditEntryResponse(
            seq=e.seq,
            at=e.at.isoformat(),
            actor=e.actor,
            event=e.event,
            action_id=str(e.action_id) if e.action_id else None,
            detail=e.detail,
            prev_hash=e.prev_hash,
            hash=e.hash,
        )
        for e in entries
    ]


@router.get("/verify")
async def verify_chain(request: Request) -> ChainVerificationResponse:
    """Verify the integrity of the audit log hash chain."""
    studio = request.app.state.studio
    is_valid, reason = studio.audit_log.verify_chain()

    return ChainVerificationResponse(
        valid=is_valid,
        reason=reason,
        entry_count=len(studio.audit_log.entries),
    )
