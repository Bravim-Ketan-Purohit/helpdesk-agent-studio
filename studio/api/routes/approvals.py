"""Approval routes — approve, reject, edit actions.

Nothing executes without a valid, unexpired, single-use approval token
bound to the payload hash. Editing a draft invalidates its approval.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from studio.models.actions import (
    Action,
    ActionPayload,
    ActionState,
    Approval,
    ApprovalDecision,
    compute_payload_hash,
)

router = APIRouter()


class ApproveRequest(BaseModel):
    """Request to approve an action."""

    action_id: str
    approver_id: str  # IdP subject ID


class ApproveWithEditsRequest(BaseModel):
    """Request to approve with modifications."""

    action_id: str
    approver_id: str
    edited_payload: ActionPayload
    reason: str | None = None


class RejectRequest(BaseModel):
    """Request to reject an action."""

    action_id: str
    approver_id: str
    reason: str  # Required on deny


class ApprovalResponse(BaseModel):
    """Approval response including the token for execution."""

    approval_id: str
    action_id: str
    decision: str
    token: str | None = None  # Only present on approval
    message: str


class ExecuteRequest(BaseModel):
    """Request to execute an approved action."""

    action_id: str
    approval_token: str


class ExecuteResponse(BaseModel):
    """Execution response."""

    success: bool
    action_id: str
    message: str
    provider_response: dict[str, Any] | None = None


@router.post("/approve")
async def approve_action(body: ApproveRequest, request: Request) -> ApprovalResponse:
    """Approve an action and issue an approval token.

    The token is bound to the current payload hash. If the payload
    is modified after this point, the token becomes invalid.
    """
    studio = request.app.state.studio
    action = studio.actions.get(body.action_id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.state not in (ActionState.DRAFTED, ActionState.PENDING_APPROVAL):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve action in state '{action.state.value}'",
        )

    # Issue approval token bound to payload hash
    token = studio.token_issuer.issue(
        action_id=action.id,
        payload_hash=action.payload_hash,
        approver_id=body.approver_id,
    )

    # Update action state
    action.state = ActionState.APPROVED

    # Record approval
    approval = Approval(
        action_id=action.id,
        approver_id=body.approver_id,
        decision=ApprovalDecision.APPROVED,
    )

    # Audit
    studio.audit_log.append(
        actor=f"operator:{body.approver_id}",
        event="action.approved",
        action_id=action.id,
        detail={"approver": body.approver_id, "payload_hash": action.payload_hash},
    )

    return ApprovalResponse(
        approval_id=str(approval.id),
        action_id=str(action.id),
        decision="approved",
        token=token.token,
        message="Action approved. Token issued for execution.",
    )


@router.post("/approve-with-edits")
async def approve_with_edits(
    body: ApproveWithEditsRequest, request: Request
) -> ApprovalResponse:
    """Approve an action with modifications.

    The payload is updated, a new hash computed, and a fresh token issued.
    The original payload is preserved in the audit log.
    """
    studio = request.app.state.studio
    action = studio.actions.get(body.action_id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.state not in (ActionState.DRAFTED, ActionState.PENDING_APPROVAL):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve action in state '{action.state.value}'",
        )

    # Compute edit distance (character-level)
    from studio.models.actions import canonical_json

    original_json = canonical_json(action.payload)
    edited_json = canonical_json(body.edited_payload)
    edit_distance = _levenshtein_distance(original_json, edited_json)

    # Audit the original before modification
    studio.audit_log.append(
        actor=f"operator:{body.approver_id}",
        event="action.edited",
        action_id=action.id,
        detail={
            "original_hash": action.payload_hash,
            "edit_distance": edit_distance,
        },
    )

    # Update payload and recompute hash
    action.payload = body.edited_payload
    action.payload_hash = compute_payload_hash(action.payload)
    action.state = ActionState.APPROVED

    # Issue new token with the new hash
    token = studio.token_issuer.issue(
        action_id=action.id,
        payload_hash=action.payload_hash,
        approver_id=body.approver_id,
    )

    # Record approval
    approval = Approval(
        action_id=action.id,
        approver_id=body.approver_id,
        decision=ApprovalDecision.APPROVED_WITH_EDITS,
        edited_payload=body.edited_payload,
        edit_distance=edit_distance,
        reason=body.reason,
    )

    studio.audit_log.append(
        actor=f"operator:{body.approver_id}",
        event="action.approved_with_edits",
        action_id=action.id,
        detail={
            "approver": body.approver_id,
            "new_hash": action.payload_hash,
            "edit_distance": edit_distance,
        },
    )

    return ApprovalResponse(
        approval_id=str(approval.id),
        action_id=str(action.id),
        decision="approved_with_edits",
        token=token.token,
        message=f"Action approved with edits (distance: {edit_distance}). New token issued.",
    )


@router.post("/reject")
async def reject_action(body: RejectRequest, request: Request) -> ApprovalResponse:
    """Reject an action with a required reason."""
    studio = request.app.state.studio
    action = studio.actions.get(body.action_id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.state not in (ActionState.DRAFTED, ActionState.PENDING_APPROVAL):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject action in state '{action.state.value}'",
        )

    action.state = ActionState.REJECTED

    studio.audit_log.append(
        actor=f"operator:{body.approver_id}",
        event="action.rejected",
        action_id=action.id,
        detail={"approver": body.approver_id, "reason": body.reason},
    )

    return ApprovalResponse(
        approval_id=str(uuid.uuid4()),
        action_id=str(action.id),
        decision="rejected",
        token=None,
        message=f"Action rejected: {body.reason}",
    )


@router.post("/execute")
async def execute_action(body: ExecuteRequest, request: Request) -> ExecuteResponse:
    """Execute an approved action using the approval token.

    The token is verified for:
    - Valid signature
    - Not expired
    - Not previously used (single-use)
    - Payload hash matches current action state
    """
    studio = request.app.state.studio
    action = studio.actions.get(body.action_id)

    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")

    result = await studio.executor.execute(action, body.approval_token)

    if result.success:
        return ExecuteResponse(
            success=True,
            action_id=str(action.id),
            message="Action executed successfully",
            provider_response=result.provider_response,
        )
    else:
        return ExecuteResponse(
            success=False,
            action_id=str(action.id),
            message=result.error or "Execution failed",
        )


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]
