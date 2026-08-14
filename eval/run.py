"""Evaluation runner — drafts, then grades.

Usage: python -m eval.run --suite eval/tickets --rubric eval/rubric.yaml

1. Agent drafts for all N tickets. Drafts stored unseen by the grader.
2. Grade against the pre-registered rubric.
3. Report the triple: approved unmodified / edited / rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def load_tickets(suite_dir: Path) -> list[dict[str, Any]]:
    """Load all tickets from the suite directory."""
    tickets: list[dict[str, Any]] = []
    for yaml_file in sorted(suite_dir.glob("*.yaml")):
        if yaml_file.name == "manifest.yaml":
            continue
        with open(yaml_file) as f:
            data = yaml.safe_load(f) or {}
        tickets.extend(data.get("tickets", []))
    return tickets


def load_rubric(rubric_path: Path) -> dict[str, Any]:
    """Load the pre-registered rubric."""
    with open(rubric_path) as f:
        return yaml.safe_load(f) or {}


def grade_draft(
    draft: dict[str, Any] | None,
    rubric_entry: dict[str, Any],
) -> dict[str, Any]:
    """Grade a single draft against the rubric.

    Returns: {decision, edit_distance, reason}
    """
    correct_action = rubric_entry.get("correct_action", "none")

    # If rubric says "none" (missing info or trap), drafting anything is wrong
    if correct_action == "none":
        if draft is None:
            return {"decision": "approved", "edit_distance": 0, "reason": "Correctly abstained"}
        else:
            return {
                "decision": "rejected",
                "edit_distance": 0,
                "reason": f"Should have abstained but drafted {draft.get('kind', 'unknown')}",
            }

    # If draft is None but action was expected
    if draft is None:
        return {
            "decision": "rejected",
            "edit_distance": 0,
            "reason": f"Failed to draft (expected {correct_action})",
        }

    # Check action kind matches
    if draft.get("kind") != correct_action:
        return {
            "decision": "rejected",
            "edit_distance": 0,
            "reason": f"Wrong action kind: got {draft.get('kind')}, expected {correct_action}",
        }

    # Check required fields
    required = rubric_entry.get("required_fields", [])
    payload = draft.get("payload", {})
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return {
            "decision": "approved_with_edits",
            "edit_distance": len(str(missing)) * 5,
            "reason": f"Missing fields: {missing}",
        }

    return {"decision": "approved", "edit_distance": 0, "reason": "Matches rubric"}


def run_evaluation(suite_dir: Path, rubric_path: Path) -> dict[str, Any]:
    """Run the full evaluation suite."""
    tickets = load_tickets(suite_dir)
    rubric = load_rubric(rubric_path)
    rubric_entries = {t["id"]: t for t in rubric.get("tickets", [])}

    results: list[dict[str, Any]] = []
    approved = 0
    approved_edited = 0
    rejected = 0
    trap_correct = 0
    trap_total = 0
    edit_distances: list[int] = []

    for ticket in tickets:
        ticket_id = ticket["id"]
        rubric_entry = rubric_entries.get(ticket_id, {})

        # In production, run the agent here. For now, simulate.
        # The actual agent integration happens when the agent module is wired.
        draft = None  # Placeholder — will be replaced with agent output

        grade = grade_draft(draft, rubric_entry)
        grade["ticket_id"] = ticket_id
        grade["category"] = rubric_entry.get("category", "unknown")

        if grade["decision"] == "approved":
            approved += 1
        elif grade["decision"] == "approved_with_edits":
            approved_edited += 1
            edit_distances.append(grade["edit_distance"])
        else:
            rejected += 1

        # Track trap performance
        if rubric_entry.get("category") == "trap":
            trap_total += 1
            if grade["decision"] == "approved":  # Correctly abstained
                trap_correct += 1

        results.append(grade)

    total = len(results)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tickets": total,
        "approved_unmodified": approved,
        "approved_with_edits": approved_edited,
        "rejected": rejected,
        "approval_rate_unmodified": approved / total if total > 0 else 0,
        "approval_rate_with_edits": approved_edited / total if total > 0 else 0,
        "rejection_rate": rejected / total if total > 0 else 0,
        "median_edit_distance": sorted(edit_distances)[len(edit_distances) // 2] if edit_distances else 0,
        "trap_performance": f"{trap_correct}/{trap_total}",
        "reviewer": "single-reviewer against pre-registered rubric",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation suite")
    parser.add_argument("--suite", default="eval/tickets", help="Ticket suite directory")
    parser.add_argument("--rubric", default="eval/rubric.yaml", help="Rubric YAML file")
    parser.add_argument("--output", default="eval/results/latest.json", help="Output file")
    args = parser.parse_args()

    suite_dir = Path(args.suite)
    rubric_path = Path(args.rubric)
    output_path = Path(args.output)

    if not suite_dir.exists():
        print(f"Suite directory not found: {suite_dir}")
        sys.exit(1)
    if not rubric_path.exists():
        print(f"Rubric not found: {rubric_path}")
        sys.exit(1)

    print(f"Running evaluation: {suite_dir} against {rubric_path}")
    results = run_evaluation(suite_dir, rubric_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults ({results['total_tickets']} tickets):")
    print(f"  Approved unmodified: {results['approved_unmodified']} ({results['approval_rate_unmodified']:.1%})")
    print(f"  Approved with edits: {results['approved_with_edits']} ({results['approval_rate_with_edits']:.1%})")
    print(f"  Rejected:            {results['rejected']} ({results['rejection_rate']:.1%})")
    print(f"  Trap performance:    {results['trap_performance']}")
    print(f"  Reviewer:            {results['reviewer']}")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
