# Study notes — Enterprise Helpdesk Agent Studio

Reference material, carried over from `projects-ref.md`.

## Reference

### [`langgenius/dify`](https://github.com/langgenius/dify)

A masterclass in building a beautiful, client-facing AI application. Next.js frontend, Python/FastAPI
backend — the same split as this repo.

**What to study:**

1. Their **Next.js components** — how they build interactive chat interfaces. Particularly the streaming
   message rendering and how state is organized so the UI stays responsive during long operations.
2. **More importantly: how their frontend authenticates with their backend API to trigger workflows.**
   That auth boundary is the thing to get right here, since this repo's whole premise is that only an
   authenticated operator can authorize an action.

Also worth studying in dify: how they structure a **workflow/node editor** UI. Not needed for v1, but if
this project grows into a "studio" where operators configure agent behavior rather than just approve
actions, that's the reference implementation.

And note their empty states, loading states, and error states. Dify feels polished because those are
handled everywhere — which is exactly the difference between a demo that lands and one that doesn't.
For an FDE interview where you screen-share this, that polish is not cosmetic; it's the deliverable.

## Also worth reading

- **Slack API** — OAuth scopes, Block Kit for rich messages, Events API vs. Socket Mode. Know the
  minimum scope set and why each one is needed; an enterprise security reviewer will ask.
- **Jira REST API** — transitions (moving a ticket between statuses is not a simple field write),
  and the permission model.
- **OAuth 2.0 token handling** — refresh flows, encrypted storage at rest, and what happens on revocation.
- **Human-in-the-loop design patterns** — the useful framing is *reversibility*: automate freely where
  actions are cheap to undo, gate hard where they aren't. A Jira comment is reversible; a refund is not.

## Questions to answer before coding

1. What structurally prevents the agent from writing to Slack or Jira without approval? Not "what does
   the code currently do" — what makes it *impossible*?
2. An operator edits a proposal before approving. What's recorded in the audit log — the original, the
   edit, or both? (Both. Why?)
3. Approve is clicked twice, or the request retries. What stops double execution?
4. A proposal contains five actions and the third fails. What state is the system in, and what does the
   operator see?
5. Which scopes does each integration actually need, and can you defend every one?
6. What does the agent do when it isn't confident — draft a bad proposal, or draft nothing? Which is
   worse for operator trust?

## The framing that matters for FDE

The engineering value here isn't the agent. It's the **approval boundary** — an enterprise customer will
not let an LLM touch their ticketing system or issue refunds unsupervised, and building the trust
boundary that makes automation acceptable *is* forward-deployed work. Lead with that in interviews, not
with the model.

## Deliberate divergences from the reference

| Area | dify does | This repo does | Why |
| --- | --- | --- | --- |
| | | | |
