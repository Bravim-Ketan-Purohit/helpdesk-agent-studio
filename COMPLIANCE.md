# COMPLIANCE.md — Control Boundary Documentation

**Designed against** the SOC 2 Trust Services Criteria and HIPAA Security Rule control boundaries.

---

> **This document describes the controls implemented. It does not claim SOC 2 or HIPAA compliance.**
> Those are audit outcomes requiring a formal assessment period, an independent auditor, and organizational
> policies that extend beyond code. Asserting compliance without an audit is a misrepresentation.

---

## 1. Data Classification

| Classification | Examples | Handling |
| --- | --- | --- |
| **Sensitive credentials** | OAuth tokens, refresh tokens, KMS keys | Encrypted at rest (envelope encryption via AWS KMS); never logged, never in span attributes, never returned in API responses |
| **Customer identifiers** | Customer IDs, email addresses | Stored only as references for ticket association; never in logs or traces |
| **Action payloads** | Jira comments, Slack messages, refund amounts | Stored in Postgres; hashed for approval binding; never in span attributes |
| **Audit trail** | Who approved what, when | Append-only, hash-chained, retained indefinitely; tamper-evident |
| **System metadata** | Action IDs, state transitions, timestamps | Standard handling; appears in logs and traces |

### What enters the system

- Ticket content from Slack events and Jira webhooks (text, metadata)
- Operator identity from IdP (subject ID, roles, session claims)
- Provider responses (confirmation IDs, timestamps)

### What NEVER enters the system

- Payment card data (PCI scope — explicitly out of scope; refunds reference transaction IDs only)
- Customer health records (no PHI flows through this system)
- Biometric data
- Real financial credentials (all payment operations go to a mock provider)

## 2. Encryption

### In transit

- All external API calls over TLS 1.2+
- Internal cluster communication over mTLS (Kubernetes service mesh or Nginx)
- Ingress terminates TLS at the Nginx controller

### At rest

- OAuth tokens: envelope encryption with per-record data keys via AWS KMS
- Data keys: generated via `GenerateDataKey`; plaintext zeroed after use, never persisted
- Database: Postgres with encrypted storage volumes
- Audit archives: S3 with SSE-KMS
- Key rotation: enabled on the CMK; re-wrap path documented and tested

## 3. The Audit Trail

- **Append-only**: No UPDATE or DELETE operations exist on the audit_log table
- **Hash-chained**: Each entry includes the SHA-256 hash of the previous entry; chain verified on read
- **Tamper-evident**: Any deletion or modification breaks the chain, detectable by `studio.audit.verify`
- **Retained indefinitely**: No TTL; archived to S3 Glacier after 90 days
- **Content**: actor, event, action_id, detail, timestamp, hash — NEVER tokens or customer PII

## 4. Access Control and Least Privilege

### Credential separation (the core control)

| Component | Credentials | Can do |
| --- | --- | --- |
| Agent | Read-only OAuth tokens | Search, read, list |
| Executor | Write-capable OAuth tokens | Mutate (post, transition, refund) |
| Dashboard | Operator session (via IdP) | View, approve, reject |

The agent process **structurally cannot write** — not by convention, by type system and network policy:
- Type system: `ReadOnlyProvider` has no mutating methods
- Import graph: agent module cannot import `WriteProvider` or `studio.executor`
- Infrastructure: NetworkPolicy prevents agent pods from reaching write endpoints
- Credentials: agent environment has no write tokens

### Identity and authorization

- Operators authenticate via Keycloak (OIDC or SAML 2.0)
- Roles: `approver`, `senior_approver`, `auditor`, `admin`
- Approval tokens bind the IdP subject ID — two-approver rules require two distinct identities
- High-value approvals (>$200) require step-up re-authentication
- Sessions: short-lived access tokens with refresh rotation

### Kubernetes RBAC

- Separate ServiceAccounts for agent, executor, and web
- ServiceAccount tokens scoped to minimum required API access
- No shared credentials between components

## 5. The Approval Boundary as Change Control

Every mutation goes through:
1. **Policy evaluation** — declarative rules from policy.yaml
2. **Operator review** — human sees exactly what will change (live diff)
3. **Approval token issuance** — HMAC-bound to payload hash, approver ID, nonce, expiry
4. **Execution-time re-verification** — hash recomputed, nonce checked, policy re-evaluated
5. **Audit recording** — full trail of who approved what

Controls:
- No bypass flag, no `--force`, no dev shortcut
- Editing a payload invalidates approval (hash changes)
- Tokens expire (5 min default), are single-use (nonce)
- Idempotency keys prevent double-execution

## 6. Secret Management

- Secrets in `.env` only; `.env.example` committed empty
- Production: AWS Secrets Manager via ExternalSecrets operator
- No secrets in `values.yaml`, Helm charts, or Terraform state
- No secrets in logs, error responses, span attributes, or API responses
- OAuth tokens encrypted at rest with envelope encryption
- KMS data keys zeroed after use

## 7. Known Gaps — What Would Be Required for Actual Certification

### For SOC 2 Type II

- [ ] Formal audit period (6–12 months of evidence collection)
- [ ] Independent auditor engagement (CPA firm)
- [ ] Organizational policies: information security policy, acceptable use, incident response,
      business continuity, vendor management
- [ ] Formal risk assessment
- [ ] Employee security awareness training program
- [ ] Penetration testing by an independent firm
- [ ] Formal change management process beyond the approval boundary
- [ ] Monitoring and alerting with defined SLOs

### For HIPAA

- [ ] Business Associate Agreement (BAA) with all subprocessors
- [ ] Formal risk analysis (45 CFR 164.308(a)(1))
- [ ] Workforce training specific to PHI handling
- [ ] Physical safeguard documentation
- [ ] Breach notification procedures
- [ ] Designated Privacy Officer and Security Officer
- [ ] No PHI currently flows through this system; HIPAA applicability is hypothetical

### General

- [ ] Formal incident response plan and tabletop exercises
- [ ] Disaster recovery testing
- [ ] Formal vendor security assessments
- [ ] Regular access reviews
- [ ] Security information and event management (SIEM)

---

## Framing Note

This document describes controls *implemented in code and infrastructure*. The difference between
"designed against SOC 2 control boundaries" and "SOC 2 compliant" is an audit, a period of
evidence collection, organizational policies, and an independent assessor's opinion. Knowing that
gap — and stating it explicitly — is the signal that we understand what compliance means, rather
than treating it as a checkbox.
