export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const fileUrl = (path?: string | null) => (path ? `${API}${path}` : undefined);

export type Metrics = {
  pred_count: number;
  ref_count: number;
  count_error: number;
  abs_count_error: number;
  foreground_iou: number;
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
  mean_matched_iou: number;
  merged_objects: number;
  split_objects: number;
};

export type MaskSummary = {
  object_count: number;
  median_area: number;
  mean_solidity: number;
  suspicious_regions: number;
  typical_area: number;
};

export type Check = { name: string; passed: boolean; detail: string };
export type Verdict = { mode: "reference" | "reference_free"; passed: boolean; unverified_improvement?: boolean; checks: Check[] };

export type BestAttempt = {
  attempt: number;
  tool: string;
  params: Record<string, unknown>;
  metrics: Metrics | null;
  mask_summary: MaskSummary;
  overlay_url: string;
  mask_url: string;
  verified: boolean;
};

export type Report = {
  summary: string;
  what_changed: string[];
  improvements: string[];
  uncertainties: string[];
  recommendation: string;
};

export type CaseStatus =
  | "created"
  | "investigating"
  | "awaiting_review"
  | "unresolved"
  | "no_issue_found"
  | "approved"
  | "rejected"
  | "failed";

export type Case = {
  _id: string;
  title: string;
  researcher: string;
  notes: string;
  status: CaseStatus;
  created_at: string;
  planner?: string;
  has_reference: boolean;
  tags: string[];
  hypothesis?: string;
  best_attempt?: BestAttempt | null;
  baseline_metrics?: Metrics | null;
  baseline_summary?: MaskSummary;
  attempt_count?: number;
  report?: Report;
  error?: string;
  score?: number;
  assets?: { original: string; baseline_overlay: string; reference_overlay: string | null };
};

export type Step = {
  _id: string;
  index: number;
  kind: string;
  actor: string;
  title: string;
  detail: string;
  data: Record<string, any>;
  created_at: string;
};

export type Run = {
  _id: string;
  attempt: number;
  tool: string;
  params: Record<string, unknown>;
  base?: string;
  actor?: string;
  metrics: Metrics | null;
  mask_summary: MaskSummary;
  verdict: Verdict | null;
  overlay_url: string;
  mask_url?: string;
};

export type Review = { _id: string; decision: "approve" | "reject"; reviewer: string; comment: string; created_at: string };

export type Similar = {
  case_id: string;
  title: string;
  status: string;
  successful_tool: string;
  tags: string[];
  score?: number;
  via?: string;
};

export type CaseDetail = { case: Case; steps: Step[]; runs: Run[]; reviews: Review[]; similar: Similar[] };

export type Sample = { id: string; title: string; notes: string; reference_count: number; baseline_count: number; preview: string };

export type Health = { ok: boolean; storage: string; planner: string; model: string | null; max_attempts: number };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  health: () => request<Health>("/api/health"),
  samples: () => request<Sample[]>("/api/samples"),
  cases: () => request<Case[]>("/api/cases"),
  caseDetail: (id: string) => request<CaseDetail>(`/api/cases/${id}`),
  fromSample: (id: string) => request<Case>(`/api/cases/sample/${id}`, { method: "POST" }),
  upload: (form: FormData) => request<Case>("/api/cases", { method: "POST", body: form }),
  rerun: (id: string) => request<{ started: boolean }>(`/api/cases/${id}/investigate`, { method: "POST" }),
  review: (id: string, body: { decision: "approve" | "reject"; reviewer: string; comment: string }) =>
    request<Review>(`/api/cases/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  search: (q: string) => request<{ mode: string; results: Case[] }>(`/api/search?q=${encodeURIComponent(q)}`),
};

export const isRunning = (s?: CaseStatus) => s === "created" || s === "investigating";
