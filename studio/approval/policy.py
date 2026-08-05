"""Declarative policy engine — evaluated before presenting a draft and again before execution.

Policy is loaded from policy.yaml. Default posture: nothing auto-approves.
Rate limits per action type per hour prevent a runaway loop from queuing 400 drafts.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PolicyResult:
    """Result of policy evaluation for a single action."""

    allowed: bool
    requires_approval: bool
    required_approvers: int
    denied_reasons: list[str] = field(default_factory=list)
    auto_approve: bool = False
    rate_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "required_approvers": self.required_approvers,
            "denied_reasons": self.denied_reasons,
            "auto_approve": self.auto_approve,
            "rate_limited": self.rate_limited,
        }


@dataclass
class RateLimitEntry:
    """Track action counts per type per hour."""

    counts: defaultdict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def record(self, action_kind: str) -> None:
        """Record an action occurrence."""
        self.counts[action_kind].append(time.time())

    def count_in_window(self, action_kind: str, window_seconds: int = 3600) -> int:
        """Count actions of a type within the time window."""
        cutoff = time.time() - window_seconds
        entries = self.counts[action_kind]
        # Prune old entries
        self.counts[action_kind] = [t for t in entries if t > cutoff]
        return len(self.counts[action_kind])


class PolicyEngine:
    """Evaluates actions against the declarative policy.

    Loaded from policy.yaml. The engine is stateless except for rate limiting.
    """

    def __init__(self, policy_path: Path | str | None = None) -> None:
        self._policy: dict[str, Any] = {}
        self._rate_limits = RateLimitEntry()

        if policy_path is not None:
            self.load(Path(policy_path))

    def load(self, path: Path) -> None:
        """Load policy from a YAML file."""
        with open(path) as f:
            self._policy = yaml.safe_load(f) or {}

    def load_dict(self, policy: dict[str, Any]) -> None:
        """Load policy from a dictionary (for testing)."""
        self._policy = policy

    def evaluate(
        self,
        action_kind: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> PolicyResult:
        """Evaluate policy for a proposed action.

        Args:
            action_kind: The action type (e.g., 'jira.comment')
            payload: The action payload
            context: Additional context (customer flags, amounts, etc.)

        Returns:
            PolicyResult indicating whether the action is allowed and what approval is needed
        """
        context = context or {}
        actions_policy = self._policy.get("actions", {})
        action_config = actions_policy.get(action_kind)

        # Unknown action types require approval by default
        if action_config is None:
            return PolicyResult(
                allowed=True,
                requires_approval=True,
                required_approvers=1,
            )

        # Normalize config
        if isinstance(action_config, dict):
            config = action_config
        else:
            config = {"requires_approval": True, "approvers": 1}

        # Check rate limits
        rate_limit = config.get("rate_limit_per_hour")
        if rate_limit is not None:
            current_count = self._rate_limits.count_in_window(action_kind)
            if current_count >= rate_limit:
                return PolicyResult(
                    allowed=False,
                    requires_approval=True,
                    required_approvers=config.get("approvers", 1),
                    rate_limited=True,
                    denied_reasons=[
                        f"Rate limit exceeded: {current_count}/{rate_limit} per hour"
                    ],
                )

        # Check deny_if conditions
        deny_reasons = self._evaluate_deny_conditions(
            config.get("deny_if", []), payload, context
        )
        if deny_reasons:
            return PolicyResult(
                allowed=False,
                requires_approval=True,
                required_approvers=config.get("approvers", 1),
                denied_reasons=deny_reasons,
            )

        # Determine required approvers (check thresholds)
        required_approvers = config.get("approvers", 1)
        thresholds = config.get("thresholds", [])
        for threshold in thresholds:
            over_usd = threshold.get("over_usd", 0)
            amount = payload.get("amount_usd", 0)
            if amount > over_usd:
                required_approvers = max(
                    required_approvers, threshold.get("approvers", 1)
                )

        # Check auto-approve
        auto_approve = config.get("auto_approve", False)

        # Record for rate limiting
        self._rate_limits.record(action_kind)

        return PolicyResult(
            allowed=True,
            requires_approval=config.get("requires_approval", True),
            required_approvers=required_approvers,
            auto_approve=auto_approve,
        )

    def _evaluate_deny_conditions(
        self,
        conditions: list[str],
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        """Evaluate deny_if conditions.

        Supported conditions:
        - "customer.flagged" — checks context["customer"]["flagged"]
        - "amount_usd > N" — checks payload["amount_usd"] > N
        """
        reasons: list[str] = []
        for condition in conditions:
            if condition == "customer.flagged":
                customer = context.get("customer", {})
                if customer.get("flagged", False):
                    reasons.append("Customer is flagged")
            elif ">" in condition:
                parts = condition.split(">")
                if len(parts) == 2:
                    field_name = parts[0].strip()
                    threshold = float(parts[1].strip())
                    value = payload.get(field_name, 0)
                    if isinstance(value, (int, float)) and value > threshold:
                        reasons.append(f"{field_name} ({value}) exceeds limit ({threshold})")
        return reasons
