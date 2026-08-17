# Enterprise Helpdesk Agent Studio

Action-taking helpdesk agent with **OAuth across Slack and Jira** and **human-in-the-loop approval**: the
agent drafts actions (ticket updates, refunds) that operators review and confirm from a Next.js
dashboard before execution.

**Stack:** Next.js · shadcn/ui · Python · Slack + Jira APIs
**Resume target:** `Bravim_Purohit_FDE.tex` → Projects & Publications
**Role:** Forward Deployed Engineer

---

## The claim this repo must prove

> Action-taking helpdesk agent with OAuth across Slack and Jira and human-in-the-loop approval: the
> agent drafts actions (ticket updates, refunds) that operators review and confirm from a Next.js
> dashboard before execution.

**This is the one project of the eight with no metric in the resume bullet.** That's a gap worth closing
— see below.

## The missing metric

Every other project bullet ends in a number. This one is purely qualitative, which makes it the weakest
of the eight on a page full of quantified claims. Candidates worth measuring once the thing works:

- **Approval rate** — what fraction of drafted actions an operator confirms unedited. This is the real
  quality signal for a draft-and-approve agent, and it's the number a forward-deployed interviewer will
  find most interesting.
- **Edit distance** on the actions operators do modify — how close were the near-misses?
- **Time per ticket** vs. handling it manually.
- **Action coverage** — what share of a realistic ticket set the agent can draft *any* valid action for.

Pick one, instrument it, and add it to the resume bullet. Approval rate is the recommendation.

| Metric | Resume placeholder | Measured | Method |
| --- | --- | --- | --- |
| Draft approval rate | *(not yet in resume)* | — | TBD |

**Do not uncomment** the GitHub link at `Bravim_Purohit_FDE.tex:134` until the repo is public and
presentable.

## Architecture

```
 Slack event / ticket created
        │
        ▼
 ┌─────────────── Python backend ───────────────┐
 │  ingest ─► classify ─► retrieve context      │
 │                            │                 │
 │                            ▼                 │
 │                   ┌─────────────────┐        │
 │                   │ agent drafts an │        │
 │                   │ ACTION PROPOSAL │        │
 │                   └────────┬────────┘        │
 │                            │  persisted,     │
 │                            │  NOT executed   │
 └────────────────────────────┼─────────────────┘
                              ▼
              ┌───────────────────────────────┐
              │  Next.js operator dashboard   │
              │  review · edit · approve/deny │
              └───────────────┬───────────────┘
                              │  explicit approval
                              ▼
              ┌───────────────────────────────┐
              │  executor: Slack / Jira write │
              │  idempotent · audit-logged    │
              └───────────────────────────────┘
```

## The one invariant that matters

**Nothing reaches Slack or Jira without an operator's explicit approval.** The agent produces proposals;
only the executor writes, and only when handed an approved proposal.

Enforce this structurally, not by convention: the agent code path should have **no credentials capable
of writing**. Separate the read-only agent client from the write-capable executor client. Then "the
agent can't act unilaterally" is a property of the architecture rather than a promise in a README —
which is exactly how you'd have to justify it to an enterprise security review.

Proposals must be **immutable once approved** — capture what the operator saw and approved, so the
audit log answers "who approved what, exactly" rather than "who approved something like this."

## Why this project fits the FDE role

Forward-deployed work is: sit with a customer's actual workflow, automate the parts that are safe to
automate, and keep a human in the loop where the blast radius is real. Refunds are a good example on
purpose — nobody sane lets an LLM issue refunds unsupervised, and building the approval boundary well
*is* the engineering.

The demo matters more here than in the other seven. An FDE interview is partly a demo. Budget real time
for the dashboard being genuinely good — shadcn/ui is in the stack for a reason.

## Getting started

```bash
# backend
python -m venv .venv && source .venv/bin/activate   # needs Python 3.11+
pip install -r api/requirements.txt
cp .env.example .env                                # Slack + Jira OAuth creds
uvicorn api.main:app --reload

# frontend
cd web && npm install && npm run dev
```

Slack and Jira both need OAuth apps registered. See `docs/SETUP.md` (to be written) for scopes — request
the **minimum** scopes needed, and be able to explain each one.

## Layout

```
api/           FastAPI backend, agent, proposal store
api/executor/  the ONLY write-capable path; separate credentials
web/           Next.js + shadcn/ui operator dashboard
integrations/  Slack + Jira OAuth, read clients
audit/         immutable approval + execution log
docs/STUDY.md  notes from langgenius/dify
```

## Documents

| File | What it's for |
| --- | --- |
| [SPEC.md](SPEC.md) | **Authoritative** technical specification — what to build, the data model, the measurement protocol, and the honest-claims register |
| [ROADMAP.md](ROADMAP.md) | Build order, milestone by milestone |
| [CLAUDE.md](CLAUDE.md) | Operating rules for a coding session here: environment, ports, conventions, when to stop and ask |
| [docs/STUDY.md](docs/STUDY.md) | What to read in the reference implementations before writing code |

Where `SPEC.md` and any other document disagree, `SPEC.md` wins.

## Status

Scaffold — specified, not yet implemented. This repo reserves ports **7700–7799**; up to eight sibling
projects may run at the same time, so nothing here binds outside that block.
