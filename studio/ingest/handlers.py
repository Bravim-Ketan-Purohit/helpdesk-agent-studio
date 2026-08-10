"""Event handlers — process verified inbound events into tickets.

Events are queued for processing after the 3-second Slack ack requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class IngestedTicket:
    """A ticket created from an inbound event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""  # "slack" | "jira"
    external_id: str = ""  # Slack ts or Jira issue key
    subject: str = ""
    body: str = ""
    channel_id: str | None = None
    thread_ts: str | None = None
    issue_key: str | None = None
    customer_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def handle_slack_event(event: dict[str, Any]) -> IngestedTicket | None:
    """Process a Slack event into a ticket.

    Handles: message events in monitored channels.
    Ignores: bot messages, message_changed, message_deleted.
    """
    event_type = event.get("type")
    subtype = event.get("subtype")

    # Ignore bot messages and edits/deletes
    if subtype in ("bot_message", "message_changed", "message_deleted"):
        return None

    if event_type == "message":
        text = event.get("text", "")
        channel = event.get("channel", "")
        ts = event.get("ts", "")
        user = event.get("user", "")

        if not text or not channel:
            return None

        return IngestedTicket(
            source="slack",
            external_id=ts,
            subject=text[:100],
            body=text,
            channel_id=channel,
            thread_ts=ts,
            customer_id=user,
            metadata={"raw_event": event},
        )

    return None


def handle_jira_webhook(payload: dict[str, Any]) -> IngestedTicket | None:
    """Process a Jira webhook into a ticket.

    Handles: issue_created, issue_updated events.
    """
    webhook_event = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})

    if not issue:
        return None

    fields = issue.get("fields", {})
    issue_key = issue.get("key", "")

    return IngestedTicket(
        source="jira",
        external_id=issue_key,
        subject=fields.get("summary", ""),
        body=fields.get("description", "") or "",
        issue_key=issue_key,
        metadata={
            "webhook_event": webhook_event,
            "status": fields.get("status", {}).get("name", ""),
            "priority": fields.get("priority", {}).get("name", ""),
        },
    )
