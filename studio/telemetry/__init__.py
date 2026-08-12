"""OpenTelemetry instrumentation.

Spans: ingest_event, agent_draft, retrieve, policy_evaluate, present,
approve, execute, provider_call.

Attributes: action_id, kind, policy_result, approver_role, provider,
rate_limit_state.

NEVER put payload contents, tokens, or customer identifiers in span attributes.
Traces leave the cluster; a span attribute is as exfiltrable as a log line.
"""

from studio.telemetry.tracing import init_tracing, get_tracer, traced

__all__ = ["init_tracing", "get_tracer", "traced"]
