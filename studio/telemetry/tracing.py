"""OpenTelemetry tracing setup and utilities.

CRITICAL: Never put payload contents, tokens, or customer identifiers
in span attributes. Traces go to a third-party collector in most
deployments, and a trace attribute is as exfiltrable as a log line.
"""

from __future__ import annotations

import functools
import os
from typing import Any, Callable, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

F = TypeVar("F", bound=Callable[..., Any])

# Attributes that MUST NEVER appear in spans
FORBIDDEN_ATTRIBUTES = frozenset({
    "payload",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "customer_email",
    "customer_name",
    "customer_phone",
    "credit_card",
    "ssn",
})


def init_tracing(
    service_name: str = "helpdesk-agent-studio",
    otlp_endpoint: str | None = None,
) -> TracerProvider:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Name of the service for trace attribution
        otlp_endpoint: OTLP collector endpoint (default from env)
    """
    endpoint = otlp_endpoint or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:7710"
    )

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "0.1.0",
    })

    provider = TracerProvider(resource=resource)

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
    except ImportError:
        # OTLP exporter not available — traces go nowhere (dev mode)
        pass

    trace.set_tracer_provider(provider)
    return provider


def get_tracer(name: str = "studio") -> trace.Tracer:
    """Get a tracer instance."""
    return trace.get_tracer(name)


def validate_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Validate span attributes — strip forbidden fields.

    NEVER include payload contents, tokens, or customer identifiers.
    """
    clean = {}
    for key, value in attributes.items():
        key_lower = key.lower()
        if any(forbidden in key_lower for forbidden in FORBIDDEN_ATTRIBUTES):
            continue
        clean[key] = value
    return clean


def traced(
    span_name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """Decorator to trace a function with OpenTelemetry.

    Usage:
        @traced("agent_draft", {"kind": "jira.comment"})
        async def draft_action(...):
            ...

    Attributes are validated — forbidden fields are stripped.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            name = span_name or func.__name__
            safe_attrs = validate_attributes(attributes or {})

            with tracer.start_as_current_span(name, attributes=safe_attrs):
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            name = span_name or func.__name__
            safe_attrs = validate_attributes(attributes or {})

            with tracer.start_as_current_span(name, attributes=safe_attrs):
                return func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator
