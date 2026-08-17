# SPEC — Enterprise Helpdesk Agent Studio

**Authoritative technical specification.** `ROADMAP.md` gives the order; this gives the contents. Where
they disagree, this wins. If a requirement here looks wrong, say so and stop.

---

## 1. The claim

> Action-taking helpdesk agent with OAuth across Slack and Jira and human-in-the-loop approval: the agent
> drafts actions (ticket updates, refunds) that operators review and confirm from a Next.js dashboard
> before execution.

Resume stack string the build must match: *Next.js, shadcn/ui, Python, Slack + Jira APIs*
(`Bravim_Purohit_FDE.tex:131`).

### This is the only one of the eight projects with no number

Every other project on these four resumes carries a metric. On the FDE page, the project directly below
this one claims a percentage. A bullet with no measurement sitting next to bullets with measurements reads
as the one that didn't work — so the metric is part of the build, not an afterthought.

**Target metric: draft approval rate.** Reported as a triple, because the split is the interesting part:

```
approved unmodified / total drafts          ← the headline
approved after operator edits / total       ← "nearly right" — often the bigger number
rejected outright / total                   ← where the agent is unsafe or useless
```

Design the measurement before writing the agent (§9). Retrofitting it means grading drafts you've already
seen, which is not a measurement.

## 2. Non-goals

- Not a Zendesk/Intercom replacement. Slack and Jira only.
- No agent-initiated writes, ever, under any configuration. See §4 — that's the entire point.
- **No real money.** "Refunds" are executed against a mock payments provider. Never wire a live Stripe key
  into this repo, not even in test mode with a real account.
- No fine-tuning. Prompting, retrieval, and tool use.
- No multi-tenant SaaS billing. Multi-workspace OAuth, yes; billing, no.

## 3. Architecture

```
 Slack events / Jira webhooks ──► ingest ──► ticket store (Postgres :7702)
                                                │
                                     ┌──────────▼───────────┐
                                     │ agent (Python)       │
                                     │ READ-ONLY client     │◄── retrieval over past tickets + KB
                                     │ tools: search, read  │
                                     └──────────┬───────────┘
                                                │ drafts a proposed action
                                                ▼
                                        actions table (state=drafted)
                                                │
                          Next.js dashboard :7700  (shadcn/ui)
                          operator sees a live diff of what will change
                                                │
                                     approve / edit / reject
                                                ▼
                                 approval token (bound to payload hash)
                                                │
                                     ┌──────────▼───────────┐
                                     │ executor             │
                                     │ WRITE-capable client │──► Slack / Jira / mock payments
                                     │ idempotent, audited  │
                                     └──────────────────────┘
                                                │
                                        append-only audit log
```

## 4. The approval boundary — the load-bearing design decision

An agent that *could* write but is *asked not to* is one prompt injection away from writing. The boundary
must be structural.

### Credential separation

Two distinct OAuth clients, two distinct token sets, two distinct processes:

| | scopes | can call |
| --- | --- | --- |
| **agent client** | read-only (`channels:history`, `read:jira-work`, …) | search, read, list |
| **executor client** | write (`chat:write`, `write:jira-work`, …) | mutate |

The agent process has **no access to executor credentials** — not in its environment, not in its config,
not reachable through a shared client factory. Enforce it in code: the agent's transport layer takes a
`ReadOnlyClient` type that has no mutating methods to call. Then a jailbroken agent still cannot write,
because there is no code path to write with. Add a test that asserts the agent module cannot import or
construct the write client.

This is the part of the project worth talking about in an interview. Build it first (M1), not last.

### Approval tokens must bind to the payload

The naive flow has a time-of-check/time-of-use hole: operator approves action #42, then something mutates
#42's payload, then execution applies the mutated version. Prevent it structurally:

```
approval_token = HMAC(server_key, {
    action_id, payload_sha256, approver_id, nonce, issued_at, expires_at  # 5 min
})
```

The executor recomputes `payload_sha256` from the row it is about to execute and rejects on mismatch.
Editing a draft therefore **invalidates the approval and requires re-approval** — which is correct, not
inconvenient. Tokens are single-use (nonce recorded, replay rejected) and expire.

### Policy engine

Declarative, in `policy.yaml`, evaluated before a draft is presented and again before execution:

```yaml
actions:
  jira.comment:      {requires_approval: true,  approvers: 1}
  jira.transition:   {requires_approval: true,  approvers: 1}
  slack.post:        {requires_approval: true,  approvers: 1}
  payments.refund:
    requires_approval: true
    approvers: 1
    thresholds: [{over_usd: 50, approvers: 2}]
    deny_if: ["customer.flagged", "amount_usd > 500"]
```

Default posture: **nothing auto-approves.** Auto-approval is an opt-in per action type, and the README
should note which types would be safe candidates and why. Rate limits per action type per hour, so a
runaway loop can't queue 400 drafts.

## 5. Data model

```sql
CREATE TYPE action_state AS ENUM
  ('drafted','pending_approval','approved','rejected','executing','executed','failed','expired');

CREATE TABLE actions (
  id            UUID PRIMARY KEY,
  ticket_id     TEXT NOT NULL,
  kind          TEXT NOT NULL,            -- jira.comment | jira.transition | slack.post | payments.refund
  payload       JSONB NOT NULL,
  payload_hash  TEXT NOT NULL,
  rationale     TEXT NOT NULL,            -- the agent's reasoning, shown to the operator
  evidence      JSONB NOT NULL,           -- ticket/KB references the draft was based on
  preview       JSONB,                    -- computed before/after diff
  state         action_state NOT NULL DEFAULT 'drafted',
  policy_result JSONB NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE approvals (
  id UUID PRIMARY KEY,
  action_id UUID NOT NULL REFERENCES actions(id),
  approver_id TEXT NOT NULL,
  decision TEXT NOT NULL,                 -- approved | approved_with_edits | rejected
  edited_payload JSONB,
  edit_distance INT,                      -- how much the operator changed — feeds the metric
  reason TEXT,
  nonce TEXT NOT NULL UNIQUE,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  latency_ms INT                          -- time from presented to decided
);

CREATE TABLE audit_log (                  -- append-only; no UPDATE, no DELETE, ever
  seq BIGSERIAL PRIMARY KEY,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT NOT NULL,                    -- agent | operator:<id> | executor | system
  event TEXT NOT NULL,
  action_id UUID,
  detail JSONB NOT NULL,
  prev_hash TEXT, hash TEXT               -- hash chain: tamper-evident
);

CREATE TABLE oauth_tokens (
  id UUID PRIMARY KEY,
  provider TEXT NOT NULL,                 -- slack | jira
  role TEXT NOT NULL,                     -- agent_read | executor_write
  workspace_id TEXT NOT NULL,
  access_token_enc BYTEA NOT NULL,        -- encrypted at rest, never plaintext
  refresh_token_enc BYTEA,
  scopes TEXT[] NOT NULL,
  expires_at TIMESTAMPTZ,
  UNIQUE (provider, role, workspace_id)
);
```

The audit log's hash chain is cheap and makes the log tamper-evident — a good detail for a project whose
subject is trust boundaries.

## 6. Integrations

### OAuth

- **Slack**: OAuth v2 install flow, `state` parameter validated, separate app installs (or separate scope
  sets) for the read and write roles. Verify request signatures on every inbound event
  (`X-Slack-Signature` + timestamp, with a replay window). Handle URL verification and the 3-second ack
  requirement by queueing work.
- **Jira**: OAuth 2.0 3LO with refresh-token rotation. Store `cloudid`. Handle 401 → refresh → retry once.
- Tokens encrypted at rest with a key from the environment (KMS-shaped interface, envelope encryption, even
  if the local implementation is a single key). Never log a token, never return one over the API.
- Every provider call goes through a rate limiter honouring `Retry-After` — Slack tier limits and Jira cost
  budgets both matter, and a demo that gets the app rate-limited during a screen share is avoidable.

### Mock providers

A `--fake` provider mode (server on :7704) implementing the Slack and Jira surfaces the code uses, so tests
and CI run with no external accounts and the demo works offline. Payments is **only** ever a mock.

Test-suite requirement: the whole integration suite must pass against the fakes, and a smaller smoke suite
runs against real sandbox workspaces (Slack free workspace + Jira free tier).

### Idempotent execution

`idempotency_key` per action, passed to providers that support it and enforced locally by a unique index.
A retried execution must never double-post or double-refund. Test it by executing the same approved action
twice and asserting one side effect.

## 7. Dashboard (`web/`)

Next.js (App Router) + TypeScript + Tailwind + **shadcn/ui** (named on the resume — use it as the component
layer, not a stray import).

1. **Inbox.** Drafted actions queue: ticket, action kind, confidence, policy result, age. Keyboard-first
   triage (`j`/`k`, `a` approve, `e` edit, `r` reject) — operator throughput is the product.
2. **Review pane** — the core screen. The agent's rationale, the evidence it used (linked, clickable), and a
   **live before/after diff computed from current provider state**, not from the payload alone. The operator
   must see `Priority: Low → High`, `Assignee: unassigned → J. Chen`, and the exact message text that will
   be posted. Diffing the payload against stale state is how a wrong approval happens.
3. **Edit.** Inline payload editing with the re-approval requirement made visible ("editing invalidates the
   current approval").
4. **Audit.** Full timeline per action, and a global log view with hash-chain verification status.
5. **Metrics.** Approval / approved-with-edits / rejected rates over time, by action kind, with median
   decision latency and median edit distance. This is where the resume number comes from.
6. **Policy.** Read-only rendering of `policy.yaml` so an operator can see the rules in force.

## 8. Module layout

```
studio/
  agent/       drafting, retrieval, read-only tools    ← cannot construct a write client
  executor/    write clients, idempotency, retries
  approval/    token issue + verify, policy engine
  providers/   slack/, jira/, payments_mock/, fakes/
  oauth/       flows, token storage + encryption, refresh
  ingest/      Slack events, Jira webhooks, signature verification
  audit/       append-only log, hash chain, verification
  api/         FastAPI
  metrics/     approval-rate computation, exports
eval/          graded ticket suite, rubric, results/
web/           Next.js + shadcn/ui dashboard
```

## 9. Measurement protocol — how the missing number gets made

### The graded ticket suite

`eval/tickets/` — ≥ 60 realistic helpdesk tickets spanning: routine (password reset, status question),
judgement calls (ambiguous refund eligibility), multi-step (needs a Jira transition *and* a Slack reply),
missing-information (correct action is to ask, not act), and **traps** where the plausible action is wrong
(e.g. a refund request from an account outside the eligibility window). Traps are essential: an agent that
drafts confidently on every ticket will score well on a suite with no traps.

Source realistic tickets from public support corpora or write them from the shapes above, and say which in
the manifest.

### Pre-registered rubric

Write the rubric **before** running the agent, and commit it. For each ticket: the correct action kind, the
required fields, and what makes a draft acceptable / acceptable-with-minor-edits / unacceptable. Include the
correct answer for traps (usually "ask for information" or "escalate", not "act").

### Running it

1. Agent drafts for all N tickets. Drafts stored, unseen by the grader until the batch completes.
2. Grade against the pre-registered rubric. Record decision, edit distance, and decision latency.
3. Report the triple from §1, plus per-category breakdown and trap performance separately.

### Honesty about the reviewer

With one operator, "approval rate" is self-assessment, and self-assessment of your own agent's output has an
obvious bias. Mitigations, in order of strength:

1. **2–3 independent reviewers** on a ≥ 30-ticket sample; report inter-rater agreement (κ). Best option, and
   it costs a couple of hours of favours.
2. **Blind grading**: mix in drafts written by hand and by a weaker model; grade without knowing the source.
3. At minimum: pre-registered rubric, batch grading, and an explicit README statement that grading was
   single-reviewer against a pre-registered rubric with N stated.

Whichever you use, state it in the README next to the number. "78 % of drafts approved unmodified across 64
tickets, single-reviewer against a pre-registered rubric" is credible and honest. "78 % approval rate" with
nothing behind it is the kind of claim that collapses under one follow-up question.

### If the resume bullet gains a metric

The bullet currently has none. Once measured, the addition is one clause — and the user decides the wording,
not this repo. Report the numbers; don't draft resume copy into the `.tex`.

## 10. Milestone acceptance criteria

- **M1 Trust boundary.** Two clients, two credential sets; agent module structurally unable to write, with a
  test proving it. Approval-token issue/verify with payload binding, expiry, single use. Audit log with hash
  chain.
- **M2 Providers + OAuth.** Slack and Jira read paths under OAuth; signature verification on inbound; fakes
  on :7704 with the integration suite green against them; token encryption at rest.
- **M3 Draft → approve → execute.** End-to-end for `jira.comment` and `jira.transition`; idempotent
  execution proven by double-execute test; policy engine enforcing approver counts and thresholds.
- **M4 Agent quality.** Retrieval over past tickets + KB; rationale and evidence on every draft; refusal
  path for missing-information tickets; mock refunds with threshold policy.
- **M5 Dashboard.** Inbox, review pane with live before/after diff, edit-invalidates-approval flow, audit
  view, metrics page. shadcn/ui throughout.
- **M6 Measurement.** Suite ≥ 60 tickets, rubric pre-registered and committed, batch graded, triple
  reported with trap breakdown; **README Benchmarks table filled**; reviewer arrangement stated.
- **M7 Presentable.** Real Slack + Jira sandbox smoke test passing; README diagram accurate; CI green.

## 11. Honest-claims register

| Claim | Status | Backed by |
| --- | --- | --- |
| action-taking helpdesk agent | ☐ | executes real Jira/Slack mutations post-approval |
| OAuth across Slack and Jira | ☐ | both flows working against real sandbox workspaces |
| human-in-the-loop approval | ☐ | credential separation test; payload-bound approval tokens |
| agent *cannot* act unilaterally | ☐ | test asserting the agent module can't construct a write client |
| operators review and confirm from a Next.js dashboard | ☐ | shadcn/ui dashboard with live before/after diff |
| refunds | ☐ | mock provider only, stated plainly in the README |
| *(new)* draft approval rate | ☐ | `eval/results/`, pre-registered rubric, N and reviewer stated |

Any unchecked row ⇒ `Bravim_Purohit_FDE.tex:134` stays commented.
