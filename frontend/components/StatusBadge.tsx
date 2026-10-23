import type { CaseStatus } from "@/lib/api";

const LABELS: Record<CaseStatus, string> = {
  created: "queued",
  investigating: "investigating",
  awaiting_review: "awaiting review",
  unresolved: "unresolved",
  no_issue_found: "no issue found",
  approved: "approved",
  rejected: "rejected",
  failed: "failed",
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  const running = status === "created" || status === "investigating";
  return <span className={`badge s-${status} ${running ? "pulse" : ""}`}>{LABELS[status] ?? status}</span>;
}

export function ActorChip({ actor }: { actor: string }) {
  const label = actor === "heuristic" ? "heuristic (offline)" : actor;
  return <span className={`actor actor-${actor}`}>{label}</span>;
}
