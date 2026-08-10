"""Action drafter — the core agent logic.

Uses ONLY ReadOnlyProvider for context retrieval. Produces structured
action proposals with rationale and evidence. Never executes anything.
"""

from __future__ import annotations

import uuid
from typing import Any

from studio.models.actions import (
    Action,
    ActionPayload,
    ActionState,
    JiraCommentPayload,
    JiraTransitionPayload,
    PaymentsRefundPayload,
    SlackPostPayload,
    compute_payload_hash,
)
from studio.providers.base import ReadOnlyProvider


class ActionDrafter:
    """Drafts proposed actions for operator review.

    The drafter has access to read-only providers ONLY. It cannot execute
    anything — it produces Action objects in DRAFTED state that must go
    through the approval flow before execution.
    """

    def __init__(
        self,
        slack_reader: ReadOnlyProvider,
        jira_reader: ReadOnlyProvider,
        kb_reader: ReadOnlyProvider | None = None,
    ) -> None:
        # Read-only providers only — the type system enforces this
        self._slack = slack_reader
        self._jira = jira_reader
        self._kb = kb_reader

    async def draft(
        self,
        ticket_id: str,
        ticket_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Action | None:
        """Draft a proposed action for a ticket.

        Returns None when the agent isn't confident enough to propose anything —
        drafting nothing is better than drafting wrong for operator trust.

        Args:
            ticket_id: The ticket identifier
            ticket_data: The ticket content and metadata
            context: Additional context (customer data, past interactions)

        Returns:
            An Action in DRAFTED state, or None if the agent should abstain
        """
        context = context or {}

        # Classify the ticket
        classification = self._classify(ticket_data)

        # Retrieve relevant context
        evidence = await self._retrieve_context(ticket_id, ticket_data, classification)

        # Determine the appropriate action
        payload = self._determine_action(ticket_data, classification, evidence, context)

        if payload is None:
            return None

        # Generate rationale
        rationale = self._generate_rationale(ticket_data, classification, evidence, payload)

        return Action(
            ticket_id=ticket_id,
            kind=payload.kind,
            payload=payload,
            rationale=rationale,
            evidence=evidence,
            state=ActionState.DRAFTED,
        )

    def _classify(self, ticket_data: dict[str, Any]) -> dict[str, Any]:
        """Classify the ticket type and urgency.

        Categories:
        - routine: password reset, status question
        - judgement: ambiguous refund eligibility
        - multi_step: needs transition AND reply
        - missing_info: correct action is to ask, not act
        - trap: plausible action is wrong
        """
        subject = ticket_data.get("subject", "").lower()
        body = ticket_data.get("body", "").lower()
        ticket_type = ticket_data.get("type", "")

        # Simple keyword-based classification (in production, use an LLM)
        if any(kw in body for kw in ["password", "reset", "login", "access"]):
            return {"category": "routine", "confidence": 0.9, "action_type": "jira.comment"}
        elif any(kw in body for kw in ["refund", "charge", "billing"]):
            return {"category": "judgement", "confidence": 0.7, "action_type": "payments.refund"}
        elif any(kw in body for kw in ["status", "update", "progress"]):
            return {"category": "routine", "confidence": 0.85, "action_type": "slack.post"}
        elif any(kw in body for kw in ["escalate", "urgent", "critical"]):
            return {"category": "multi_step", "confidence": 0.75, "action_type": "jira.transition"}
        else:
            return {"category": "missing_info", "confidence": 0.4, "action_type": None}

    async def _retrieve_context(
        self,
        ticket_id: str,
        ticket_data: dict[str, Any],
        classification: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Retrieve relevant context using read-only providers."""
        evidence: list[dict[str, Any]] = []

        # Search for related past tickets
        try:
            related = await self._jira.search(
                query=ticket_data.get("subject", ""),
                max_results=5,
            )
            if related:
                evidence.append({
                    "type": "related_tickets",
                    "source": "jira",
                    "items": related[:3],
                })
        except Exception:
            pass  # Graceful degradation — missing context is not fatal

        # Search for related Slack threads
        try:
            threads = await self._slack.search(
                query=ticket_data.get("subject", ""),
                max_results=3,
            )
            if threads:
                evidence.append({
                    "type": "related_threads",
                    "source": "slack",
                    "items": threads[:2],
                })
        except Exception:
            pass

        # Search KB if available
        if self._kb:
            try:
                kb_results = await self._kb.search(
                    query=ticket_data.get("subject", ""),
                    max_results=3,
                )
                if kb_results:
                    evidence.append({
                        "type": "knowledge_base",
                        "source": "kb",
                        "items": kb_results,
                    })
            except Exception:
                pass

        return evidence

    def _determine_action(
        self,
        ticket_data: dict[str, Any],
        classification: dict[str, Any],
        evidence: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> ActionPayload | None:
        """Determine what action to propose, or None to abstain.

        When confidence is low, the agent drafts nothing rather than guessing.
        A bad draft erodes operator trust faster than no draft at all.
        """
        confidence = classification.get("confidence", 0)
        category = classification.get("category", "")
        action_type = classification.get("action_type")

        # Abstain on low confidence or missing info
        if confidence < 0.5 or category == "missing_info" or action_type is None:
            return None

        # Build the payload based on action type
        if action_type == "jira.comment":
            return JiraCommentPayload(
                issue_key=ticket_data.get("issue_key", ticket_data.get("ticket_id", "")),
                body=self._draft_comment(ticket_data, evidence),
            )
        elif action_type == "jira.transition":
            return JiraTransitionPayload(
                issue_key=ticket_data.get("issue_key", ticket_data.get("ticket_id", "")),
                transition_id=ticket_data.get("target_transition_id", ""),
                transition_name=ticket_data.get("target_transition_name", "In Progress"),
            )
        elif action_type == "slack.post":
            return SlackPostPayload(
                channel_id=ticket_data.get("channel_id", ""),
                text=self._draft_reply(ticket_data, evidence),
                thread_ts=ticket_data.get("thread_ts"),
            )
        elif action_type == "payments.refund":
            amount = float(ticket_data.get("refund_amount", 0))
            if amount <= 0:
                return None  # Can't determine amount — abstain
            return PaymentsRefundPayload(
                transaction_id=ticket_data.get("transaction_id", ""),
                amount_usd=amount,
                reason=ticket_data.get("refund_reason", "Customer request"),
                customer_id=ticket_data.get("customer_id", ""),
            )

        return None

    def _draft_comment(
        self, ticket_data: dict[str, Any], evidence: list[dict[str, Any]]
    ) -> str:
        """Draft a Jira comment body."""
        subject = ticket_data.get("subject", "")
        body = ticket_data.get("body", "")

        # Simple template-based drafting (in production, use an LLM)
        if "password" in body.lower() or "reset" in body.lower():
            return (
                "Hi, I've initiated the password reset process for your account. "
                "You should receive a reset link at your registered email within "
                "the next few minutes. If you don't see it, please check your spam "
                "folder. Let us know if you need further assistance."
            )
        return f"Regarding your request about: {subject}. We're looking into this and will update you shortly."

    def _draft_reply(
        self, ticket_data: dict[str, Any], evidence: list[dict[str, Any]]
    ) -> str:
        """Draft a Slack reply."""
        subject = ticket_data.get("subject", "")
        return f"Thanks for reaching out! Regarding your question about {subject} — we're on it and will have an update for you shortly."

    def _generate_rationale(
        self,
        ticket_data: dict[str, Any],
        classification: dict[str, Any],
        evidence: list[dict[str, Any]],
        payload: ActionPayload,
    ) -> str:
        """Generate the agent's reasoning for the proposed action.

        Operators need to know WHY to review efficiently. The rationale
        should reference specific evidence and explain the decision.
        """
        category = classification["category"]
        confidence = classification["confidence"]
        evidence_summary = f"{len(evidence)} evidence items retrieved"

        return (
            f"Classified as '{category}' (confidence: {confidence:.0%}). "
            f"Proposed {payload.kind} based on {evidence_summary}. "
            f"Ticket subject: '{ticket_data.get('subject', 'N/A')}'."
        )
