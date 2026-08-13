import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            Helpdesk Agent Studio
          </h1>
          <p className="text-muted-foreground mt-2">
            Human-in-the-loop approval for AI-drafted helpdesk actions
          </p>
        </header>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <Link href="/inbox">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <CardTitle className="text-lg">Inbox</CardTitle>
                <CardDescription>
                  Review and approve drafted actions
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Keyboard-first triage: j/k navigate, a approve, e edit, r
                  reject
                </p>
              </CardContent>
            </Card>
          </Link>

          <Link href="/audit">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <CardTitle className="text-lg">Audit Log</CardTitle>
                <CardDescription>
                  Full timeline with hash-chain verification
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Who approved what, exactly. Tamper-evident chain.
                </p>
              </CardContent>
            </Card>
          </Link>

          <Link href="/metrics">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <CardTitle className="text-lg">Metrics</CardTitle>
                <CardDescription>
                  Approval rate triple and decision analytics
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  The resume number: approved / edited / rejected rates
                </p>
              </CardContent>
            </Card>
          </Link>

          <Link href="/policy">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <CardTitle className="text-lg">Policy</CardTitle>
                <CardDescription>
                  Active policy rules and thresholds
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Read-only view of policy.yaml enforcement rules
                </p>
              </CardContent>
            </Card>
          </Link>
        </div>

        <footer className="mt-12 pt-6 border-t">
          <p className="text-sm text-muted-foreground">
            The agent drafts. The operator decides. Nothing executes without
            explicit approval bound to a payload hash.
          </p>
        </footer>
      </div>
    </main>
  );
}
