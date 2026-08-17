# CLAUDE.md — Enterprise Helpdesk Agent Studio

Operating instructions for a Claude Code session in this repo. Read `SPEC.md` before writing code —
especially §4 (the approval boundary, which is the whole project) and §9 (how the missing metric gets
made). `ROADMAP.md` has the order.

## What this is

A helpdesk agent that drafts real Slack/Jira actions and an operator console that reviews and confirms them
before anything executes. The interesting engineering is the trust boundary, not the agent. It exists to
prove one resume bullet, quoted in `SPEC.md` §1 — the only one of the eight with no metric yet, which is why
`SPEC.md` §9 exists.

## Hard rules

1. **Stay inside this directory.** Independent git repo; the parent is deliberately not a repo and seven
   sibling projects sit beside it. Never read, write, or `git` above `helpdesk-agent-studio/`.
2. **The agent process can never hold write credentials.** Not in env, not in config, not through a shared
   client factory, not "temporarily for testing". If you find yourself needing it, the design is being
   violated — stop and ask.
3. **No real money, ever.** Refunds go to the mock provider. Do not add a Stripe/PayPal/Adyen key to this
   repo in any mode. A live test-mode key on a real account is still a real account.
4. **Nothing executes without a valid, unexpired, single-use approval token bound to the payload hash.**
   Editing a draft invalidates its approval. No bypass flag, no `--force`, no dev shortcut that skips it —
   a dev shortcut around an approval gate is how the gate ends up bypassed in the demo.
5. **Never auto-approve by default.** Auto-approval is opt-in per action type in `policy.yaml`.
6. **Audit log is append-only.** No `UPDATE`, no `DELETE`, ever. Maintain the hash chain.
7. **Never invent a measurement.** The approval-rate number comes from a committed graded run in
   `eval/results/` against a rubric that was written *before* the drafts were seen.
8. **Never touch the resume.** Different repo. Don't edit the `.tex`, don't uncomment the GitHub link, and
   don't draft resume wording for the new metric — report numbers, let the user write the bullet.
9. **Secrets in `.env` only**, `.env.example` committed empty. OAuth tokens encrypted at rest. Never log a
   token or an access code, never include one in an error response, never commit a fixture containing one.
10. **Verify inbound webhooks.** Slack signature + timestamp window, Jira verification. An unverified
    webhook endpoint on a project about trust boundaries is self-defeating.

## Environment (this machine: arm64 macOS, 11 cores, 18 GB)

`python3` on the PATH is **3.8.10 and unusable here**. Use `uv` (0.12 installed):

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Frontend: Node 22 / npm 10 installed. Next.js App Router + Tailwind + shadcn/ui (`npx shadcn@latest init`).

Services:

```bash
docker compose -f docker-compose.dev.yml up -d      # Postgres
alembic upgrade head
python -m studio.providers.fakes --port 7704        # fake Slack + Jira, no accounts needed
```

**Default to the fakes.** Real OAuth needs a public HTTPS callback, which means a tunnel:

```bash
cloudflared tunnel --url http://localhost:7701      # or ngrok http 7701
```

Register the tunnel URL as the redirect URI in the Slack app and Atlassian app. Real-workspace work is M7
smoke-testing; everything before it runs against the fakes, which keeps development offline and CI green.

Accounts needed eventually (both free): a personal Slack workspace, a Jira Cloud free site.

## Ports — this project owns 7700–7799

Up to eight sibling projects may run at once. Never bind outside this block; never bind :3000, :5432,
:8000.

| Port | Use |
| --- | --- |
| 7700 | `web/` Next.js dashboard (`next dev -p 7700`) |
| 7701 | API (FastAPI) — also the tunnel target for OAuth callbacks |
| 7702 | Postgres (→ 5432) |
| 7703 | reserved |
| 7704 | fake Slack + Jira provider server |

## Commands

```bash
uvicorn studio.api.app:app --reload --port 7701
cd web && npm run dev -- -p 7700
python -m studio.providers.fakes --port 7704
python -m eval.run --suite eval/tickets --rubric eval/rubric.yaml     # drafts, then grade
python -m studio.audit.verify                                         # hash-chain check
pytest -q ; pytest -q -m integration      # integration runs against the fakes
pytest -q -m boundary                     # the tests that prove the agent can't write
```

## Conventions

- Python 3.12, full type hints, `mypy --strict` on `studio/approval`, `studio/executor`, `studio/agent`,
  `studio/audit`. Ruff for lint + format.
- The read/write split is expressed in the **type system**: `ReadOnlyProvider` has no mutating methods;
  `WriteProvider` lives in `studio/executor` and is never imported from `studio/agent`. Add an import-graph
  test so a future refactor can't quietly break it.
- Pydantic v2 for action payloads, one model per action kind, with a discriminated union on `kind`. Payload
  hashing uses canonical JSON (sorted keys, no whitespace) — an unstable hash breaks approval binding in a
  way that looks random.
- Every provider call goes through the rate limiter and honours `Retry-After`.
- Frontend: server components for reads, server actions or explicit route handlers for mutations. shadcn/ui
  components, not ad-hoc markup — it's on the resume line. Keyboard-first inbox.
- Structured logs with `action_id`, `ticket_id`, `actor`, `state`. Never a token, never a full customer
  record.
- Tests: pytest. `boundary`-marked tests are the ones that matter most; they must be green before any
  execution path is written.
- Commits: imperative, ≤ 72 chars, scoped — `approval: bind token to canonical payload hash`.
- Git identity is already set for this repo (`bravimpurohit1305@gmail.com`). Leave it.

## Definition of done, and when to stop

Milestones per `SPEC.md` §10. CI green on push; the integration suite runs against the fakes in CI (no
secrets required).

**Stop and ask the user** when:

- It's time to set up real Slack/Jira apps and a tunnel (M7) — that's account creation under the user's
  identity, so ask.
- The measurement needs independent reviewers (`SPEC.md` §9) — recruiting 2–3 people for a 30-ticket sample
  is the user's call, and it's the difference between a credible number and a self-graded one.
- The measured approval rate is low. That's a real finding about the agent, reportable as-is; don't loosen
  the rubric after seeing results, and don't regrade to a better number.
- A `SPEC.md` requirement looks wrong, or you want a dependency it doesn't name.

Report honestly with the conditions attached: "64 tickets, 71 % approved unmodified, 20 % approved with
edits (median edit distance 14 chars), 9 % rejected, 6/7 traps correctly refused; single reviewer against a
pre-registered rubric" is the deliverable. A bare percentage is not.
