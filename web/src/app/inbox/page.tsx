"use client";

import { useEffect, useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Action, ApprovalResponse } from "@/lib/api";

/**
 * Inbox — drafted actions queue.
 *
 * Keyboard-first triage:
 * - j/k: navigate up/down
 * - a: approve selected
 * - e: edit selected (opens review pane)
 * - r: reject selected
 */
export default function InboxPage() {
  const [actions, setActions] = useState<Action[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedAction, setSelectedAction] = useState<Action | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approvalToken, setApprovalToken] = useState<string | null>(null);

  const fetchActions = useCallback(async () => {
    try {
      const res = await fetch("/api/actions?state=drafted");
      if (!res.ok) throw new Error("Failed to fetch actions");
      const data = await res.json();
      setActions(data);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      switch (e.key) {
        case "j":
          setSelectedIndex((i) => Math.min(i + 1, actions.length - 1));
          break;
        case "k":
          setSelectedIndex((i) => Math.max(i - 1, 0));
          break;
        case "a":
          if (actions[selectedIndex]) handleApprove(actions[selectedIndex]);
          break;
        case "r":
          if (actions[selectedIndex]) handleReject(actions[selectedIndex]);
          break;
        case "e":
        case "Enter":
          if (actions[selectedIndex]) setSelectedAction(actions[selectedIndex]);
          break;
        case "Escape":
          setSelectedAction(null);
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [actions, selectedIndex]);

  const handleApprove = async (action: Action) => {
    try {
      const res = await fetch("/api/approvals/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_id: action.id,
          approver_id: "operator:current",
        }),
      });
      const data: ApprovalResponse = await res.json();
      if (data.token) {
        setApprovalToken(data.token);
        // Auto-execute after approval
        await fetch("/api/approvals/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action_id: action.id,
            approval_token: data.token,
          }),
        });
      }
      fetchActions();
    } catch (err) {
      setError("Failed to approve action");
    }
  };

  const handleReject = async (action: Action) => {
    const reason = prompt("Reason for rejection (required):");
    if (!reason) return;

    try {
      await fetch("/api/approvals/reject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_id: action.id,
          approver_id: "operator:current",
          reason,
        }),
      });
      fetchActions();
    } catch (err) {
      setError("Failed to reject action");
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen p-8">
        <div className="max-w-6xl mx-auto">
          <p className="text-muted-foreground">Loading actions...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Inbox</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {actions.length} drafted actions pending review.{" "}
              <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">j</kbd>/
              <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">k</kbd>{" "}
              navigate,{" "}
              <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">a</kbd>{" "}
              approve,{" "}
              <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">r</kbd>{" "}
              reject
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchActions}>
            Refresh
          </Button>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-destructive/10 text-destructive rounded-md text-sm">
            {error}
          </div>
        )}

        {actions.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-muted-foreground">
                No pending actions. The agent hasn&apos;t drafted anything yet.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="flex gap-6">
            {/* Action list */}
            <div className="w-1/2 space-y-2">
              {actions.map((action, index) => (
                <Card
                  key={action.id}
                  className={`cursor-pointer transition-colors ${
                    index === selectedIndex
                      ? "border-primary ring-1 ring-primary"
                      : "hover:border-muted-foreground/30"
                  }`}
                  onClick={() => {
                    setSelectedIndex(index);
                    setSelectedAction(action);
                  }}
                >
                  <CardHeader className="py-3 px-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge variant={getKindVariant(action.kind)}>
                          {action.kind}
                        </Badge>
                        <span className="text-sm font-medium">
                          {action.ticket_id}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {new Date(action.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                      {action.rationale}
                    </p>
                  </CardHeader>
                </Card>
              ))}
            </div>

            {/* Review pane */}
            <div className="w-1/2">
              {selectedAction ? (
                <ReviewPane
                  action={selectedAction}
                  onApprove={() => handleApprove(selectedAction)}
                  onReject={() => handleReject(selectedAction)}
                />
              ) : (
                <Card>
                  <CardContent className="py-12 text-center">
                    <p className="text-muted-foreground">
                      Select an action to review
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function ReviewPane({
  action,
  onApprove,
  onReject,
}: {
  action: Action;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{action.kind}</CardTitle>
          <Badge variant={getKindVariant(action.kind)}>{action.state}</Badge>
        </div>
        <CardDescription>Ticket: {action.ticket_id}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Rationale */}
        <div>
          <h4 className="text-sm font-medium mb-1">Agent Rationale</h4>
          <p className="text-sm text-muted-foreground bg-muted p-3 rounded-md">
            {action.rationale}
          </p>
        </div>

        {/* Payload — the before/after diff */}
        <div>
          <h4 className="text-sm font-medium mb-1">
            Proposed Action (Payload)
          </h4>
          <p className="text-xs text-muted-foreground mb-2">
            Editing this payload invalidates the current approval.
          </p>
          <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-48">
            {JSON.stringify(action.payload, null, 2)}
          </pre>
        </div>

        {/* Evidence */}
        {action.evidence.length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-1">Evidence</h4>
            <div className="space-y-1">
              {action.evidence.map((ev, i) => (
                <div
                  key={i}
                  className="text-xs bg-muted p-2 rounded-md"
                >
                  <span className="font-medium">
                    {(ev as Record<string, unknown>).type as string}
                  </span>{" "}
                  from{" "}
                  {(ev as Record<string, unknown>).source as string}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Policy result */}
        <div>
          <h4 className="text-sm font-medium mb-1">Policy</h4>
          <div className="text-xs bg-muted p-2 rounded-md">
            Requires {action.policy_result.required_approvers || 1} approver(s)
            {action.policy_result.auto_approve && " (auto-approve eligible)"}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <Button onClick={onApprove} size="sm" className="flex-1">
            Approve (a)
          </Button>
          <Button
            onClick={onReject}
            variant="destructive"
            size="sm"
            className="flex-1"
          >
            Reject (r)
          </Button>
        </div>

        <p className="text-xs text-center text-muted-foreground">
          Payload hash: {action.payload_hash.slice(0, 16)}...
        </p>
      </CardContent>
    </Card>
  );
}

function getKindVariant(kind: string) {
  switch (kind) {
    case "jira.comment":
      return "secondary" as const;
    case "jira.transition":
      return "default" as const;
    case "slack.post":
      return "outline" as const;
    case "payments.refund":
      return "warning" as const;
    default:
      return "secondary" as const;
  }
}
