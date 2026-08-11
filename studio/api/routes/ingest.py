"""Ingest routes — webhook endpoints for Slack events and Jira webhooks.

All inbound webhooks are verified before processing.
Slack: signature + timestamp window
Jira: webhook verification token
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from studio.ingest.handlers import handle_jira_webhook, handle_slack_event
from studio.ingest.webhooks import verify_jira_webhook, verify_slack_signature

router = APIRouter()


@router.post("/slack/events")
async def slack_events(request: Request) -> dict[str, Any] | Response:
    """Receive Slack events with signature verification.

    Handles:
    - URL verification challenge (returns challenge)
    - Event callbacks (processes after verification)
    """
    body_bytes = await request.body()
    body = await request.json()

    # Handle URL verification (Slack app setup)
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    # Verify signature
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if signing_secret:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")

        verification = verify_slack_signature(
            signing_secret=signing_secret,
            timestamp=timestamp,
            body=body_bytes,
            signature=signature,
        )

        if not verification.valid:
            raise HTTPException(status_code=401, detail=verification.reason)

    # Process the event (ack within 3 seconds, queue heavy work)
    event = body.get("event", {})
    ticket = handle_slack_event(event)

    if ticket:
        # In production, queue this for async processing
        studio = request.app.state.studio
        studio.audit_log.append(
            actor="system",
            event="ticket.ingested",
            detail={"source": "slack", "ticket_id": ticket.id},
        )

    # Ack immediately (Slack requires response within 3 seconds)
    return Response(status_code=200)


@router.post("/jira/webhook")
async def jira_webhook(request: Request) -> dict[str, Any]:
    """Receive Jira webhooks with verification.

    Handles: issue_created, issue_updated, comment_created
    """
    body = await request.json()

    # Verify webhook
    shared_secret = os.environ.get("JIRA_WEBHOOK_SECRET", "")
    verification = verify_jira_webhook(shared_secret, body)

    if not verification.valid:
        raise HTTPException(status_code=401, detail=verification.reason)

    # Handle verification challenge
    if body.get("webhookEvent") == "jira:webhooks_verification":
        return {"status": "verified"}

    # Process the webhook
    ticket = handle_jira_webhook(body)

    if ticket:
        studio = request.app.state.studio
        studio.audit_log.append(
            actor="system",
            event="ticket.ingested",
            detail={"source": "jira", "ticket_id": ticket.id, "issue_key": ticket.issue_key},
        )

    return {"status": "received"}
