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

---

## 12. Extended stack (added 2026-08-17)

This is the enterprise-integration project, so it owns the enterprise-integration stack. Everything here
reinforces the §4 trust boundary rather than sitting beside it.

### 12.1 MCP server — read-only tools, by construction

Expose the agent's read-only Slack and Jira capabilities as **Model Context Protocol** tools:
`slack_search_messages`, `slack_get_thread`, `jira_search_issues`, `jira_get_issue`,
`jira_get_transitions`, `kb_search`.

This is the canonical MCP use case and it *strengthens* §4: the MCP server is built on the
`ReadOnlyProvider` types, so the entire set of tools exposed to any agent is structurally incapable of
mutation. There is no `jira_transition_issue` tool to expose, because no write method exists on the type.

Hard rules: **no write tools over MCP, ever** — not gated, not flagged, not admin-only. Approval and
execution are a separate process with separate credentials, and MCP does not reach them. Tool responses are
size-capped and redacted the same way logs are. Auth on the MCP transport; an unauthenticated MCP server on
a real Slack workspace is a data-exfiltration endpoint.

Then this repo becomes usable from Claude Desktop or Claude Code as a read-only helpdesk tool, which is a
much better demo than a screenshot.

### 12.2 Enterprise identity: SSO via Keycloak

Approvers are named actors in an audit log, so *who they are* is load-bearing. Operator login moves to
proper enterprise identity:

- **Keycloak**, self-hosted in Docker, as the IdP. It speaks both **OIDC** and **SAML 2.0**, so one
  container demonstrates both protocols — and it's free and reproducible by anyone who clones the repo,
  which a hosted IdP is not.
- **OIDC** authorization-code flow with PKCE for the Next.js dashboard.
- **SAML 2.0** as a second configured client with assertion signature validation, because enterprise
  customers still ask for SAML and having wired it is the differentiator.
- **Roles/groups → policy.** `approver`, `senior_approver`, `auditor`, `admin` mapped from IdP claims. The
  §4 approver-count and threshold rules read from these, so a refund over $50 requiring two approvers means
  two *distinct authenticated identities* with the right role — not two clicks.
- Sessions: short-lived access tokens, refresh rotation, and an explicit **re-authentication requirement for
  high-value approvals** (step-up auth). Approving a $500 refund on a session opened eight hours ago is
  exactly the control an auditor asks about.
- The approval token from §4 binds the **IdP subject id**, not a local user row.

Auth0 is not used: Keycloak covers OIDC and SAML self-hosted, and a reader can run it.

### 12.3 AWS KMS — real envelope encryption

Promote the "KMS-shaped interface" in §6 to actual AWS KMS:

- A CMK per environment. Data keys generated per token record via `GenerateDataKey`; the ciphertext blob is
  stored alongside the encrypted payload; plaintext data keys are never persisted and are zeroed after use.
- `oauth_tokens.access_token_enc` uses envelope encryption with the data key, not a static app secret.
- Key rotation enabled, and a documented re-wrap path — encryption without a rotation story is theatre.
- Audit-log entries for decrypt operations, so token access is itself auditable.
- Local dev uses LocalStack KMS or an explicit `LocalKmsProvider` behind the same interface, so no AWS
  account is needed until deployment.

### 12.4 Kubernetes + Helm — the FDE deliverable

The forward-deployed story is "install this in the customer's cluster", so the deployment artefact is part
of the product, not an afterthought:

```
deploy/
  helm/helpdesk-agent-studio/
    Chart.yaml
    values.yaml              # customer-tunable: replicas, ingress host, IdP, KMS key, resources
    values-example-*.yaml    # a worked example per deployment shape
    templates/
      agent-deployment.yaml       # read-only credentials mounted
      executor-deployment.yaml    # write credentials — separate ServiceAccount
      web-deployment.yaml
      ingress.yaml                # Nginx ingress, TLS
      networkpolicy.yaml          # agent pods cannot reach provider write endpoints
      externalsecret.yaml         # or sealed-secrets; never plaintext in values
      hpa.yaml, pdb.yaml, servicemonitor.yaml
```

The important detail: **§4's credential separation becomes an infrastructure boundary too.** Agent and
executor are separate Deployments with separate ServiceAccounts, separate mounted secrets, and a
NetworkPolicy that prevents agent pods from reaching provider write endpoints at all. Defence in depth — the
type system stops the code, the network stops everything else. That's the part worth talking about.

Requirements: `helm lint` and `helm template` in CI; the chart installs on a local **kind** cluster and the
smoke suite passes against it; no secret ever in `values.yaml`; resource requests/limits set; probes wired
to `/healthz` and `/readyz`.

**Nginx** as the ingress controller, terminating TLS and enforcing the OAuth callback path — also the place
where webhook signature verification's rate limits live.

**Terraform** (`infra/`) for what surrounds the cluster: KMS CMK, IAM roles for service accounts, S3 for
audit-log archival, VPC. `fmt` + `validate` in CI.

### 12.5 Node.js middle tier, named as such

The Next.js server layer is the BFF and should be documented as one rather than being incidental: route
handlers and server actions hold session, talk to the FastAPI core over an internal-only interface, and
never expose provider tokens to the browser. Server components fetch with the operator's session; the
browser receives rendered state, never credentials. Make the trust boundary between browser → BFF → core
explicit in the README diagram.

### 12.6 COMPLIANCE.md — controls, not certifications

`COMPLIANCE.md` documenting the actual control boundary: data classification (what customer data enters the
system and what never does), encryption in transit and at rest, the audit trail and its hash chain, retention
and deletion, access control and least privilege, the approval boundary as a change-control mechanism, secret
management, and known gaps.

**Wording rule, and it matters more here than anywhere else in these eight repos:** the document is framed as
*"designed against SOC 2 and HIPAA control boundaries"* and never as *"SOC 2 compliant"* or *"HIPAA
compliant"*. Those are audit outcomes, not properties of code. Asserting them without an audit is a
misrepresentation, and in healthcare-adjacent hiring it is the kind that ends a process. The same rule
applies to any resume wording derived from this work: describe the controls you implemented, never claim a
certification.

Include a "not claimed" section listing what would be required for actual certification — a BAA, an audit
period, a pen test, formal policies. Knowing the gap is the senior signal.

### 12.7 OpenTelemetry

Spans: `ingest_event`, `agent_draft`, `retrieve`, `policy_evaluate`, `present`, `approve`, `execute`,
`provider_call`. Attributes: `action_id`, `kind`, `policy_result`, `approver_role`, provider, rate-limit
state. The `present → approve` gap gives operator decision latency for free — which is a metric §9 needs
anyway.

**Never put payload contents, tokens, or customer identifiers in span attributes.** Traces go to a
third-party collector in most deployments, and a trace attribute is as exfiltrable as a log line.

## 13. Additional milestones

- **M8 Enterprise identity.** Keycloak with OIDC + SAML clients; role mapping to the policy engine;
  step-up re-auth for high-value approvals; approval tokens bound to IdP subject; AWS KMS envelope
  encryption with a documented rotation path.
- **M9 MCP server.** Six read-only tools built on `ReadOnlyProvider`; authenticated transport; a test
  asserting no write tool can be registered; demonstrated from an external MCP client.
- **M10 Deployable.** Helm chart installing on kind with the smoke suite green; agent/executor as separate
  Deployments with separate ServiceAccounts and a NetworkPolicy blocking agent→write-endpoint traffic;
  Nginx ingress with TLS; `helm lint`/`template` in CI; Terraform `fmt`/`validate` in CI.
- **M11 Compliance + observability.** `COMPLIANCE.md` with the "not claimed" section; OTel end to end with
  the no-payload-in-attributes rule enforced by a test.

### Honest-claims additions

| Claim | Status | Backed by |
| --- | --- | --- |
| enterprise SSO (OIDC **and** SAML) | ☐ | Keycloak with both clients working; role-driven policy |
| approvers are authenticated identities | ☐ | token bound to IdP subject; two-approver rule = two identities |
| secrets encrypted with a managed KMS | ☐ | envelope encryption + rotation path |
| deployable into a customer cluster | ☐ | Helm chart installs on kind; smoke suite green |
| trust boundary enforced in infrastructure | ☐ | separate ServiceAccounts + NetworkPolicy |
| reusable read-only tooling | ☐ | MCP server queried from an external client |
| control boundary documented | ☐ | `COMPLIANCE.md`, framed as *designed against*, never *compliant* |
