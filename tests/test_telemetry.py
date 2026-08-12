"""Telemetry tests — no payload contents, tokens, or customer identifiers in spans.

Traces leave the cluster; a span attribute is as exfiltrable as a log line.
"""

from __future__ import annotations

import pytest

from studio.telemetry.tracing import validate_attributes, FORBIDDEN_ATTRIBUTES


@pytest.mark.boundary
class TestNoSensitiveDataInSpans:
    """Span attributes must never contain sensitive data."""

    def test_forbidden_attributes_stripped(self) -> None:
        """Validate that forbidden attribute keys are removed."""
        dirty_attrs = {
            "action_id": "abc-123",
            "kind": "jira.comment",
            "payload": '{"issue_key": "HELP-1", "body": "secret content"}',
            "token": "xoxb-secret-token",
            "access_token": "bearer-secret",
            "customer_email": "customer@example.com",
            "customer_name": "John Doe",
        }

        clean = validate_attributes(dirty_attrs)

        # Safe attributes preserved
        assert "action_id" in clean
        assert "kind" in clean

        # Forbidden attributes stripped
        assert "payload" not in clean
        assert "token" not in clean
        assert "access_token" not in clean
        assert "customer_email" not in clean
        assert "customer_name" not in clean

    def test_all_forbidden_patterns_caught(self) -> None:
        """Every forbidden pattern is caught regardless of casing."""
        for forbidden in FORBIDDEN_ATTRIBUTES:
            attrs = {forbidden: "sensitive_value", "safe_key": "safe_value"}
            clean = validate_attributes(attrs)
            assert forbidden not in clean, f"Forbidden key '{forbidden}' was not stripped"

    def test_partial_match_catches_embedded_forbidden(self) -> None:
        """Keys containing forbidden substrings are also caught."""
        attrs = {
            "user_password_hash": "abc123",
            "refresh_token_enc": "encrypted",
            "customer_name_display": "visible",
        }

        clean = validate_attributes(attrs)
        assert len(clean) == 0

    def test_safe_attributes_preserved(self) -> None:
        """Normal operational attributes pass through."""
        attrs = {
            "action_id": "uuid-here",
            "kind": "jira.comment",
            "policy_result": "allowed",
            "approver_role": "senior_approver",
            "provider": "jira",
            "rate_limit_state": "ok",
            "latency_ms": 150,
        }

        clean = validate_attributes(attrs)
        assert clean == attrs
