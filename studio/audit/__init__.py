"""Append-only audit log with hash chain.

No UPDATE, no DELETE, ever. The hash chain makes the log tamper-evident.
"""

from studio.audit.log import AuditLog, AuditEntry

__all__ = ["AuditLog", "AuditEntry"]
