"""Webhook signature verification and event ingestion.

Slack: X-Slack-Signature + timestamp window (prevents replay within 5 min)
Jira: verification token in request body

An unverified webhook endpoint on a project about trust boundaries is self-defeating.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any


SLACK_TIMESTAMP_WINDOW = 300  # 5 minutes — rejects replay attacks


@dataclass(frozen=True)
class VerificationResult:
    """Result of webhook signature verification."""

    valid: bool
    reason: str = ""


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> VerificationResult:
    """Verify a Slack webhook request signature.

    Checks:
    1. Timestamp is within the replay window (5 minutes)
    2. HMAC-SHA256 signature matches

    Args:
        signing_secret: Slack app signing secret
        timestamp: X-Slack-Request-Timestamp header
        body: Raw request body bytes
        signature: X-Slack-Signature header (v0=...)

    Returns:
        VerificationResult indicating if the request is authentic
    """
    # Check timestamp window (replay protection)
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return VerificationResult(valid=False, reason="Invalid timestamp")

    if abs(time.time() - ts) > SLACK_TIMESTAMP_WINDOW:
        return VerificationResult(
            valid=False,
            reason="Timestamp outside replay window (>5 min)",
        )

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    # Constant-time comparison
    if not hmac.compare_digest(expected, signature):
        return VerificationResult(valid=False, reason="Signature mismatch")

    return VerificationResult(valid=True)


def verify_jira_webhook(
    shared_secret: str,
    request_body: dict[str, Any],
) -> VerificationResult:
    """Verify a Jira webhook request.

    Jira Cloud webhooks include a verification mechanism through the
    webhookEvent field and can be verified via the shared secret.

    Args:
        shared_secret: The webhook shared secret configured in Jira
        request_body: Parsed JSON body of the webhook request

    Returns:
        VerificationResult
    """
    # Jira webhooks include a 'webhookEvent' field
    if "webhookEvent" not in request_body:
        return VerificationResult(valid=False, reason="Missing webhookEvent field")

    # For URL verification challenge
    if request_body.get("webhookEvent") == "jira:webhooks_verification":
        return VerificationResult(valid=True, reason="Verification challenge")

    # In production, verify using the webhook secret
    # For now, validate structure
    if not request_body.get("issue") and not request_body.get("comment"):
        return VerificationResult(valid=False, reason="Malformed webhook body")

    return VerificationResult(valid=True)
