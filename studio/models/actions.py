"""Action payload models — one per action kind, discriminated union on `kind`.

Payload hashing uses canonical JSON (sorted keys, no whitespace) so the hash
is stable. An unstable hash breaks approval binding in a way that looks random.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class ActionState(str, Enum):
    """State machine for action lifecycle."""

    DRAFTED = "drafted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
    EXPIRED = "expired"


# --- Payload types (discriminated union on 'kind') ---


class JiraCommentPayload(BaseModel):
    """Payload for posting a comment on a Jira issue."""

    kind: Literal["jira.comment"] = "jira.comment"
    issue_key: str
    body: str


class JiraTransitionPayload(BaseModel):
    """Payload for transitioning a Jira issue to a new status."""

    kind: Literal["jira.transition"] = "jira.transition"
    issue_key: str
    transition_id: str
    transition_name: str
    comment: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class SlackPostPayload(BaseModel):
    """Payload for posting a message to a Slack channel."""

    kind: Literal["slack.post"] = "slack.post"
    channel_id: str
    text: str
    thread_ts: str | None = None
    blocks: list[dict[str, Any]] | None = None


class PaymentsRefundPayload(BaseModel):
    """Payload for issuing a refund (mock provider only, never real money)."""

    kind: Literal["payments.refund"] = "payments.refund"
    transaction_id: str
    amount_usd: float
    reason: str
    customer_id: str


# Discriminated union of all action payloads
ActionPayload = Annotated[
    JiraCommentPayload | JiraTransitionPayload | SlackPostPayload | PaymentsRefundPayload,
    Field(discriminator="kind"),
]


def canonical_json(payload: BaseModel) -> str:
    """Produce canonical JSON for stable hashing.

    Sorted keys, no whitespace, no trailing newline.
    This is the ONLY way to serialize a payload for hashing.
    """
    return json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":"))


def compute_payload_hash(payload: BaseModel) -> str:
    """Compute SHA-256 hash of the canonical JSON representation."""
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


# --- Action model ---


class Action(BaseModel):
    """A proposed action drafted by the agent, pending operator approval."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    ticket_id: str
    kind: str
    payload: ActionPayload
    payload_hash: str = ""
    rationale: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    preview: dict[str, Any] | None = None
    state: ActionState = ActionState.DRAFTED
    policy_result: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        """Compute payload hash after initialization."""
        if not self.payload_hash:
            self.payload_hash = compute_payload_hash(self.payload)


class ApprovalDecision(str, Enum):
    """Possible approval decisions."""

    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"


class Approval(BaseModel):
    """An operator's approval decision on a proposed action."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    action_id: uuid.UUID
    approver_id: str  # IdP subject ID, not a local user row
    decision: ApprovalDecision
    edited_payload: ActionPayload | None = None
    edit_distance: int | None = None
    reason: str | None = None
    nonce: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: int | None = None
