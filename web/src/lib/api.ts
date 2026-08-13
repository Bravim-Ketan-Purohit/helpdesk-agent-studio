/**
 * API client for the Helpdesk Agent Studio backend.
 *
 * Server components fetch with the operator's session;
 * the browser receives rendered state, never credentials.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7701";

export interface Action {
  id: string;
  ticket_id: string;
  kind: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  rationale: string;
  evidence: Record<string, unknown>[];
  state: string;
  policy_result: Record<string, unknown>;
  idempotency_key: string;
  created_at: string;
}

export interface AuditEntry {
  seq: number;
  at: string;
  actor: string;
  event: string;
  action_id: string | null;
  detail: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ApprovalMetrics {
  total_actions: number;
  approved_unmodified: number;
  approved_with_edits: number;
  rejected: number;
  approval_rate_unmodified: number;
  approval_rate_with_edits: number;
  rejection_rate: number;
  median_edit_distance: number | null;
  median_decision_latency_ms: number | null;
}

export interface ApprovalResponse {
  approval_id: string;
  action_id: string;
  decision: string;
  token: string | null;
  message: string;
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error ${res.status}: ${error}`);
  }

  return res.json();
}

export async function getActions(state?: string): Promise<Action[]> {
  const params = state ? `?state=${state}` : "";
  return fetchAPI<Action[]>(`/api/actions${params}`);
}

export async function getAction(id: string): Promise<Action> {
  return fetchAPI<Action>(`/api/actions/${id}`);
}

export async function approveAction(
  actionId: string,
  approverId: string
): Promise<ApprovalResponse> {
  return fetchAPI<ApprovalResponse>("/api/approvals/approve", {
    method: "POST",
    body: JSON.stringify({ action_id: actionId, approver_id: approverId }),
  });
}

export async function rejectAction(
  actionId: string,
  approverId: string,
  reason: string
): Promise<ApprovalResponse> {
  return fetchAPI<ApprovalResponse>("/api/approvals/reject", {
    method: "POST",
    body: JSON.stringify({
      action_id: actionId,
      approver_id: approverId,
      reason,
    }),
  });
}

export async function executeAction(
  actionId: string,
  token: string
): Promise<{ success: boolean; message: string }> {
  return fetchAPI("/api/approvals/execute", {
    method: "POST",
    body: JSON.stringify({ action_id: actionId, approval_token: token }),
  });
}

export async function getAuditLog(actionId?: string): Promise<AuditEntry[]> {
  const params = actionId ? `?action_id=${actionId}` : "";
  return fetchAPI<AuditEntry[]>(`/api/audit${params}`);
}

export async function verifyAuditChain(): Promise<{
  valid: boolean;
  reason: string;
  entry_count: number;
}> {
  return fetchAPI("/api/audit/verify");
}

export async function getMetrics(): Promise<ApprovalMetrics> {
  return fetchAPI<ApprovalMetrics>("/api/metrics");
}
