"use client";

import { useState } from "react";
import { api, type Case, type Review } from "@/lib/api";

export default function ReviewPanel({ c, reviews, onDone }: { c: Case; reviews: Review[]; onDone: () => void }) {
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = ["awaiting_review", "unresolved", "no_issue_found"].includes(c.status);
  const canApprove = c.status === "awaiting_review";

  async function submit(decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await api.review(c._id, { decision, reviewer: reviewer.trim(), comment });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {reviews.map((r) => (
        <div key={r._id} className="row small" style={{ marginBottom: "0.5rem" }}>
          <span className={r.decision === "approve" ? "up" : "down"}>{r.decision === "approve" ? "Approved" : "Rejected"}</span>
          <span>by {r.reviewer}</span>
          {r.comment && <span className="muted">— “{r.comment}”</span>}
        </div>
      ))}
      {open && (
        <>
          {c.best_attempt && !c.best_attempt.verified && (
            <p className="small" style={{ color: "var(--warn)" }}>
              No reference mask was supplied, so this repair is unverified. Approve only if the overlay is visibly correct.
            </p>
          )}
          <label>
            Reviewer name
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="e.g. Dr A. Researcher" />
          </label>
          <label>
            Comment
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="row">
            <button className="btn btn-good" disabled={busy || !reviewer.trim() || !canApprove} onClick={() => submit("approve")}>
              Approve repaired mask
            </button>
            <button className="btn btn-bad" disabled={busy || !reviewer.trim()} onClick={() => submit("reject")}>
              Reject
            </button>
          </div>
          {error && <p className="error-box small">{error}</p>}
        </>
      )}
      {!open && !reviews.length && <p className="muted small">Review opens when the investigation finishes.</p>}
    </div>
  );
}
