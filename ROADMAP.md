# Roadmap — Enterprise Helpdesk Agent Studio

Build the approval boundary before the agent. If the agent exists first, it will have write credentials
"temporarily," and that temporary state is how the invariant dies.

## M1 — Proposal model and the credential split

- [ ] Data model: proposal (type, payload, target, rationale, status, timestamps)
- [ ] Status machine: `drafted → approved | denied | edited+approved → executed | failed`
- [ ] **Two separate API clients**: read-only (agent) and write-capable (executor)
- [ ] Executor rejects any proposal not in an approved state
- [ ] Immutable snapshot of exactly what the operator approved
- [ ] Audit log: who, what, when, and the approved payload verbatim
- [ ] Test: agent code path cannot write, even if it tries

## M2 — Integrations, read side first

- [ ] Slack OAuth (minimum scopes; document why each is needed)
- [ ] Jira OAuth (same)
- [ ] Read clients: fetch tickets, threads, user context
- [ ] Token storage encrypted, refresh handled
- [ ] Test: expired token → clean re-auth, not a 500

## M3 — Operator dashboard

- [ ] Next.js + shadcn/ui
- [ ] Proposal queue with filters
- [ ] Detail view showing the ticket, the retrieved context, and the drafted action side by side
- [ ] **Editable** proposals — operators will want to tweak before approving, and the edits are signal
- [ ] Approve / deny with a required reason on deny
- [ ] Audit trail view
- [ ] This is demo surface for an FDE interview — make it genuinely good, not adequate

## M4 — The agent

- [ ] Ticket classification
- [ ] Context retrieval (past tickets, docs, customer record)
- [ ] Action drafting with **structured output** matching the proposal schema
- [ ] Rationale attached to every proposal — operators need to know *why* to review efficiently
- [ ] Confidence signal, and a rule for when to draft nothing rather than guess

## M5 — Execution

- [ ] Slack write actions (post, reply, update)
- [ ] Jira write actions (transition, comment, field update)
- [ ] Idempotency keys — an approval clicked twice must not execute twice
- [ ] Failure handling: execution fails → proposal returns to a visible failed state, never silent
- [ ] Test: double-click approve, network retry mid-execution, API 500 on the third of five actions

## M6 — Instrument the missing metric

- [ ] Build a realistic ticket set (synthetic is fine; document that it is)
- [ ] Track **approval rate**: approved unedited / edited then approved / denied
- [ ] Track edit distance on edited proposals
- [ ] Track time-per-ticket vs. a manual baseline
- [ ] **Add the chosen number to the resume bullet** — it's the only one of the eight without one

## M7 — Demo-ready

- [ ] Seeded demo data so the dashboard is never empty
- [ ] A scripted 3-minute walkthrough: ticket arrives → agent drafts → operator edits → approves →
      executes → audit log
- [ ] Screenshots or a short recording in the README
- [ ] CI green
- [ ] Flip repo public, then uncomment `Bravim_Purohit_FDE.tex:134`

## Gate before the resume link goes live

The invariant enforced structurally and tested · a measured approval-rate number added to the bullet ·
dashboard good enough to screen-share in an interview · audit log answers "who approved what" exactly.
