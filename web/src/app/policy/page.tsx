"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

/**
 * Policy page — read-only rendering of policy.yaml.
 *
 * Shows operators the rules in force so they understand
 * what the system requires for each action type.
 */

// Static policy rendering (in production, fetched from API)
const POLICY = {
  actions: {
    "jira.comment": {
      requires_approval: true,
      approvers: 1,
      auto_approve: false,
      rate_limit_per_hour: 60,
    },
    "jira.transition": {
      requires_approval: true,
      approvers: 1,
      auto_approve: false,
      rate_limit_per_hour: 30,
    },
    "slack.post": {
      requires_approval: true,
      approvers: 1,
      auto_approve: false,
      rate_limit_per_hour: 60,
    },
    "payments.refund": {
      requires_approval: true,
      approvers: 1,
      thresholds: [
        { over_usd: 50, approvers: 2 },
        { over_usd: 200, approvers: 2, step_up_auth: true },
      ],
      deny_if: ["customer.flagged", "amount_usd > 500"],
      rate_limit_per_hour: 10,
    },
  },
};

export default function PolicyPage() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Policy</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Active enforcement rules from policy.yaml. Read-only view.
          </p>
        </header>

        <div className="mb-6 p-4 bg-muted rounded-lg">
          <p className="text-sm font-medium">Default Posture</p>
          <p className="text-sm text-muted-foreground mt-1">
            Nothing auto-approves by default. Auto-approval is opt-in per action
            type and must be explicitly configured.
          </p>
        </div>

        <div className="grid gap-4">
          {Object.entries(POLICY.actions).map(([kind, config]) => (
            <Card key={kind}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-mono">{kind}</CardTitle>
                  <div className="flex gap-2">
                    {config.auto_approve ? (
                      <Badge variant="warning">Auto-approve</Badge>
                    ) : (
                      <Badge variant="secondary">Manual approval</Badge>
                    )}
                    <Badge variant="outline">
                      {config.approvers} approver{config.approvers > 1 ? "s" : ""}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Rate limit</span>
                    <span>{config.rate_limit_per_hour}/hour</span>
                  </div>

                  {"thresholds" in config && config.thresholds && (
                    <div>
                      <span className="text-muted-foreground text-xs">
                        Thresholds:
                      </span>
                      <div className="mt-1 space-y-1">
                        {(config.thresholds as Array<Record<string, unknown>>).map(
                          (t, i) => (
                            <div
                              key={i}
                              className="text-xs bg-muted p-2 rounded flex justify-between"
                            >
                              <span>Over ${t.over_usd as number}</span>
                              <span>
                                {t.approvers as number} approvers
                                {t.step_up_auth && " + step-up auth"}
                              </span>
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  {"deny_if" in config && config.deny_if && (
                    <div>
                      <span className="text-muted-foreground text-xs">
                        Deny conditions:
                      </span>
                      <div className="mt-1 space-y-1">
                        {(config.deny_if as string[]).map((condition, i) => (
                          <div
                            key={i}
                            className="text-xs bg-destructive/10 text-destructive p-2 rounded font-mono"
                          >
                            {condition}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card className="mt-8">
          <CardHeader>
            <CardTitle className="text-base">
              Safe Auto-Approval Candidates
            </CardTitle>
            <CardDescription>
              Not enabled by default. Documented for operator reference.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="text-sm space-y-2 text-muted-foreground">
              <li>
                <strong>jira.comment</strong> — Reversible, low blast radius.
                Operator can delete. Candidate for auto-approval in
                low-sensitivity workspaces.
              </li>
              <li>
                <strong>slack.post (internal channels)</strong> — Reversible via
                delete. Less risky than customer-facing channels.
              </li>
            </ul>
            <p className="text-sm text-muted-foreground mt-4 font-medium">
              NOT safe for auto-approval:
            </p>
            <ul className="text-sm space-y-2 text-muted-foreground mt-2">
              <li>
                <strong>payments.refund</strong> — Irreversible financial action.
                Always requires explicit human approval.
              </li>
              <li>
                <strong>jira.transition</strong> — May trigger downstream
                automation (webhooks, SLAs, notifications).
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
