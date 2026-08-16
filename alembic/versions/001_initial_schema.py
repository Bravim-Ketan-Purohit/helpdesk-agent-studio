"""Initial schema — actions, approvals, audit_log, oauth_tokens.

Revision ID: 001
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Action state enum
    action_state = postgresql.ENUM(
        "drafted",
        "pending_approval",
        "approved",
        "rejected",
        "executing",
        "executed",
        "failed",
        "expired",
        name="action_state",
    )
    action_state.create(op.get_bind())

    # Actions table
    op.create_table(
        "actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("preview", postgresql.JSONB()),
        sa.Column(
            "state",
            action_state,
            nullable=False,
            server_default="drafted",
        ),
        sa.Column("policy_result", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_actions_state", "actions", ["state"])
    op.create_index("ix_actions_ticket_id", "actions", ["ticket_id"])
    op.create_index("ix_actions_kind", "actions", ["kind"])

    # Approvals table
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actions.id"),
            nullable=False,
        ),
        sa.Column("approver_id", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("edited_payload", postgresql.JSONB()),
        sa.Column("edit_distance", sa.Integer()),
        sa.Column("reason", sa.Text()),
        sa.Column("nonce", sa.Text(), unique=True, nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("latency_ms", sa.Integer()),
    )
    op.create_index("ix_approvals_action_id", "approvals", ["action_id"])

    # Audit log — APPEND-ONLY. No UPDATE, no DELETE, ever.
    op.create_table(
        "audit_log",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True)),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("hash", sa.Text()),
    )
    op.create_index("ix_audit_log_action_id", "audit_log", ["action_id"])
    op.create_index("ix_audit_log_event", "audit_log", ["event"])

    # OAuth tokens — encrypted at rest
    op.create_table(
        "oauth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary()),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("wrapped_data_key", sa.LargeBinary()),
        sa.UniqueConstraint("provider", "role", "workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("oauth_tokens")
    op.drop_table("audit_log")
    op.drop_table("approvals")
    op.drop_table("actions")
    op.execute("DROP TYPE IF EXISTS action_state")
