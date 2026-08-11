"""Metrics routes — approval rate computation and exports.

The approval-rate triple is the resume number:
- approved unmodified / total
- approved after edits / total
- rejected / total
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ApprovalMetrics(BaseModel):
    """Approval rate metrics — the resume number."""

    total_actions: int
    approved_unmodified: int
    approved_with_edits: int
    rejected: int
    approval_rate_unmodified: float
    approval_rate_with_edits: float
    rejection_rate: float
    median_edit_distance: float | None
    median_decision_latency_ms: float | None


@router.get("")
async def get_metrics(request: Request) -> ApprovalMetrics:
    """Compute current approval rate metrics."""
    studio = request.app.state.studio

    # Count by state from audit log events
    approved = 0
    approved_edited = 0
    rejected = 0
    edit_distances: list[int] = []
    latencies: list[int] = []

    for entry in studio.audit_log.entries:
        if entry.event == "action.approved":
            approved += 1
        elif entry.event == "action.approved_with_edits":
            approved_edited += 1
            dist = entry.detail.get("edit_distance")
            if dist is not None:
                edit_distances.append(dist)
        elif entry.event == "action.rejected":
            rejected += 1

    total = approved + approved_edited + rejected

    return ApprovalMetrics(
        total_actions=total,
        approved_unmodified=approved,
        approved_with_edits=approved_edited,
        rejected=rejected,
        approval_rate_unmodified=approved / total if total > 0 else 0.0,
        approval_rate_with_edits=approved_edited / total if total > 0 else 0.0,
        rejection_rate=rejected / total if total > 0 else 0.0,
        median_edit_distance=_median(edit_distances) if edit_distances else None,
        median_decision_latency_ms=_median(latencies) if latencies else None,
    )


def _median(values: list[int | float]) -> float:
    """Compute median of a list."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
    return float(sorted_vals[n // 2])
