"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AuditEntry } from "@/lib/api";

/**
 * Audit Log view — full timeline per action, global log,
 * and hash-chain verification status.
 */
export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [chainValid, setChainValid] = useState<boolean | null>(null);
  const [chainReason, setChainReason] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [auditRes, verifyRes] = await Promise.all([
          fetch("/api/audit"),
          fetch("/api/audit/verify"),
        ]);
        const auditData = await auditRes.json();
        const verifyData = await verifyRes.json();
        setEntries(auditData);
        setChainValid(verifyData.valid);
        setChainReason(verifyData.reason);
      } catch {
        setChainReason("Failed to load audit data");
      }
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <main className="min-h-screen p-8">
        <div className="max-w-6xl mx-auto">
          <p className="text-muted-foreground">Loading audit log...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Audit Log</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Append-only, hash-chained. No UPDATE, no DELETE, ever.
          </p>
        </header>

        {/* Chain verification status */}
        <Card className="mb-6">
          <CardHeader className="py-3 px-4">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  chainValid === true
                    ? "bg-green-500"
                    : chainValid === false
                    ? "bg-red-500"
                    : "bg-yellow-500"
                }`}
              />
              <div>
                <CardTitle className="text-base">
                  Hash Chain{" "}
                  {chainValid === true
                    ? "Verified"
                    : chainValid === false
                    ? "BROKEN"
                    : "Unknown"}
                </CardTitle>
                <CardDescription>{chainReason}</CardDescription>
              </div>
            </div>
          </CardHeader>
        </Card>

        {/* Entry list */}
        <div className="space-y-2">
          {entries.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-muted-foreground">No audit entries yet.</p>
              </CardContent>
            </Card>
          ) : (
            entries.map((entry) => (
              <Card key={entry.seq} className="overflow-hidden">
                <CardHeader className="py-2 px-4 bg-muted/30">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={getEventVariant(entry.event)}
                        className="text-xs"
                      >
                        {entry.event}
                      </Badge>
                      <span className="text-xs text-muted-foreground font-mono">
                        #{entry.seq}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground">
                        {entry.actor}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(entry.at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="py-2 px-4">
                  <div className="flex items-start justify-between gap-4">
                    <pre className="text-xs text-muted-foreground overflow-auto flex-1">
                      {JSON.stringify(entry.detail, null, 2)}
                    </pre>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-mono text-muted-foreground">
                        {entry.hash.slice(0, 12)}...
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>
    </main>
  );
}

function getEventVariant(event: string) {
  if (event.includes("approved")) return "success" as const;
  if (event.includes("rejected") || event.includes("failed"))
    return "destructive" as const;
  if (event.includes("executed")) return "default" as const;
  return "secondary" as const;
}
