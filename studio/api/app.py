"""FastAPI application entry point.

The API serves the dashboard and exposes the approval workflow.
Provider tokens are never exposed over the API. Structured logs with
action_id, ticket_id, actor, state — never a token, never a full customer record.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from studio.api.routes import actions, approvals, audit, health, ingest, metrics, oauth
from studio.approval.policy import PolicyEngine
from studio.approval.tokens import TokenIssuer, TokenVerifier, NonceStore
from studio.audit.log import AuditLog
from studio.executor.engine import ExecutionEngine
from studio.providers.payments_mock.provider import MockPaymentsProvider


# Application state — initialized at startup
class AppState:
    """Shared application state."""

    def __init__(self) -> None:
        # Server key for approval tokens — MUST come from env/KMS in production
        server_key = os.environ.get("APPROVAL_TOKEN_KEY", "x" * 32).encode()
        if len(server_key) < 32:
            server_key = server_key.ljust(32, b"x")

        self.policy_engine = PolicyEngine(
            policy_path=Path(__file__).parent.parent.parent / "policy.yaml"
        )
        self.audit_log = AuditLog()
        self.nonce_store = NonceStore()
        self.token_issuer = TokenIssuer(server_key)
        self.token_verifier = TokenVerifier(server_key, self.nonce_store)

        # Mock payments provider (the only payments provider, ever)
        self.payments_provider = MockPaymentsProvider()
        # Seed some test transactions
        self.payments_provider.seed_transaction("txn_001", 45.00, "cust_001")
        self.payments_provider.seed_transaction("txn_002", 125.00, "cust_002")
        self.payments_provider.seed_transaction("txn_003", 750.00, "cust_003")

        # Execution engine with write providers
        self.executor = ExecutionEngine(
            write_providers={"payments": self.payments_provider},
            token_verifier=self.token_verifier,
            policy_engine=self.policy_engine,
            audit_log=self.audit_log,
        )

        # In-memory action store (production uses Postgres)
        self.actions: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialize and cleanup."""
    app.state.studio = AppState()
    yield


app = FastAPI(
    title="Helpdesk Agent Studio",
    description="Enterprise helpdesk agent with human-in-the-loop approval boundary",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for the Next.js dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:7700",
        "http://127.0.0.1:7700",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router, tags=["health"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(oauth.router, prefix="/api/oauth", tags=["oauth"])
