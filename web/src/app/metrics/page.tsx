"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ApprovalMetrics } from "@/lib/api";

/**
 * Metrics page — approval rate triple and decision analytics.
 *
 * This is where the resume number comes from:
 * - approved unmodified / total
 * - approved after edits / total
 * - rejected / total
 */
export default function MetricsPage() {
  const [metrics, setMetrics] = useState<ApprovalMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch("/api/metrics");
        const data = await res.json();
        setMetrics(data);
      } catch {
        // Handle error
      }
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <main className="min-h-screen p-8">
        <div className="max-w-6xl mx-auto">
          <p className="text-muted-foreground">Loading metrics...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Metrics</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Approval rate triple — the resume number
          </p>
        </header>

        {metrics && (
          <>
            {/* The Triple */}
            <div className="grid gap-4 md:grid-cols-3 mb-8">
              <MetricCard
                title="Approved Unmodified"
                value={`${(metrics.approval_rate_unmodified * 100).toFixed(1)}%`}
                count={metrics.approved_unmodified}
                total={metrics.total_actions}
                description="Drafts approved without any edits"
                variant="success"
              />
              <MetricCard
                title="Approved with Edits"
                value={`${(metrics.approval_rate_with_edits * 100).toFixed(1)}%`}
                count={metrics.approved_with_edits}
                total={metrics.total_actions}
                description="Drafts approved after operator modifications"
                variant="warning"
              />
              <MetricCard
                title="Rejected"
                value={`${(metrics.rejection_rate * 100).toFixed(1)}%`}
                count={metrics.rejected}
                total={metrics.total_actions}
                description="Drafts rejected outright"
                variant="destructive"
              />
            </div>

            {/* Supporting metrics */}
            <div className="grid gap-4 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Total Actions</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold">{metrics.total_actions}</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Median Edit Distance
                  </CardTitle>
                  <CardDescription>
                    How close were the near-misses?
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold">
                    {metrics.median_edit_distance !== null
                      ? `${metrics.median_edit_distance} chars`
                      : "N/A"}
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Methodology note */}
            <Card className="mt-8">
              <CardHeader>
                <CardTitle className="text-base">Methodology</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Approval rate computed from {metrics.total_actions} actions
                  graded against a pre-registered rubric. Single-reviewer against
                  the rubric with N stated. See eval/rubric.yaml for grading
                  criteria and eval/results/ for full breakdown.
                </p>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </main>
  );
}

function MetricCard({
  title,
  value,
  count,
  total,
  description,
  variant,
}: {
  title: string;
  value: string;
  count: number;
  total: number;
  description: string;
  variant: "success" | "warning" | "destructive";
}) {
  const colorMap = {
    success: "text-green-600 dark:text-green-400",
    warning: "text-yellow-600 dark:text-yellow-400",
    destructive: "text-red-600 dark:text-red-400",
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className={`text-3xl font-bold ${colorMap[variant]}`}>{value}</p>
        <p className="text-sm text-muted-foreground mt-1">
          {count} of {total} actions
        </p>
      </CardContent>
    </Card>
  );
}
