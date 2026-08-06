"""Hash-chain verification CLI.

Usage: python -m studio.audit.verify
"""

from __future__ import annotations

import sys


def main() -> None:
    """Verify the audit log hash chain from the database."""
    # In production, this reads from Postgres.
    # For now, it demonstrates the verification interface.
    from studio.audit.log import AuditLog

    print("Audit log hash-chain verification")
    print("=" * 40)

    # TODO: Load entries from Postgres
    log = AuditLog()
    is_valid, reason = log.verify_chain()

    if is_valid:
        print(f"PASS: {reason}")
        sys.exit(0)
    else:
        print(f"FAIL: {reason}")
        sys.exit(1)


if __name__ == "__main__":
    main()
