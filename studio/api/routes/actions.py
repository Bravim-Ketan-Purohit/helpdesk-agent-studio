"""Action CRUD routes — list, get, draft actions."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from studio.models.actions import (
    Action,
    ActionPayload,
    ActionState,
    compute_payload_hash,
)

router = APIRouter()


class DraftActionRequest(BaseModel):
    """Request to create a draft action."""

    ticket_id: str
    payload: ActionPayload
    rationale: str
    evidence: list[dict[str, Any]] = []


class ActionResponse(BaseModel):
    """Action response model."""

    id: str
    ticket_id: str
    kind: str
    payload: dict[str, Any]
    payload_hash: str
    rationale: str
    evidence: list[dict[str, Any]]
    state: str
    policy_result: dict[str, Any]
    idempotency_key: str
    created_at: str


@router.get("")
async def list_actions(
    request: Request,
    state: str | None = None,
    kind: str | None = None,
) -> list[ActionResponse]:
    """List actions with optional state/kind filters."""
    studio = request.app.state.studio
    actions = list(studio.actions.values())

    if state:
        actions = [a for a in actions if a.state.value == state]
    if kind:
        actions = [a for a in actions if a.kind == kind]

    return [_to_response(a) for a in actions]


@router.get("/{action_id}")
async def get_action(action_id: str, request: Request) -> ActionResponse:
    """Get a single action by ID."""
    studio = request.app.state.studio
    action = studio.actions.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return _to_response(action)


@router.post("", status_code=201)
async def create_draft(body: DraftActionRequest, request: Request) -> ActionResponse:
    """Create a draft action.

    The action is created in DRAFTED state and must be approved before execution.
    Policy is evaluated immediately to show the operator what's required.
    """
    studio = request.app.state.studio

    action = Action(
        ticket_id=body.ticket_id,
        kind=body.payload.kind,
        payload=body.payload,
        rationale=body.rationale,
        evidence=body.evidence,
        state=ActionState.DRAFTED,
    )

    # Evaluate policy
    policy_result = studio.policy_engine.evaluate(
        action.kind, action.payload.model_dump()
    )
    action.policy_result = policy_result.to_dict()

    if not policy_result.allowed:
        action.state = ActionState.REJECTED
        studio.audit_log.append(
            actor="system",
            event="action.policy_denied",
            action_id=action.id,
            detail={"reasons": policy_result.denied_reasons},
        )

    # Store action
    studio.actions[str(action.id)] = action

    # Audit
    studio.audit_log.append(
        actor="agent",
        event="action.drafted",
        action_id=action.id,
        detail={"kind": action.kind, "ticket_id": action.ticket_id},
    )

    return _to_response(action)


def _to_response(action: Action) -> ActionResponse:
    """Convert Action model to API response."""
    return ActionResponse(
        id=str(action.id),
        ticket_id=action.ticket_id,
        kind=action.kind,
        payload=action.payload.model_dump(),
        payload_hash=action.payload_hash,
        rationale=action.rationale,
        evidence=action.evidence,
        state=action.state.value,
        policy_result=action.policy_result,
        idempotency_key=action.idempotency_key,
        created_at=action.created_at.isoformat(),
    )
