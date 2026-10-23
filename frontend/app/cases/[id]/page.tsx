"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ImageViewer, { type Layer } from "@/components/ImageViewer";
import InvestigationTimeline from "@/components/InvestigationTimeline";
import { AttemptsTable, MetricsComparison, ProxyComparison } from "@/components/MetricsComparison";
import ReviewPanel from "@/components/ReviewPanel";
import { ActorChip, StatusBadge } from "@/components/StatusBadge";
import { api, fileUrl, isRunning, type CaseDetail } from "@/lib/api";

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.caseDetail(id).then(setDetail).catch((e) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);
  const running = isRunning(detail?.case.status);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 1200);
    return () => clearInterval(t);
  }, [running, load]);

  if (error)
    return (
      <div className="stack">
        <p className="error-box">
          {error === "Not Found" ? "This case doesn't exist in the current database." : error}
        </p>
        <Link href="/" className="small">
          ← All investigations
        </Link>
      </div>
    );
  if (!detail) return <p className="muted">Loading…</p>;

  const { case: c, steps, runs, reviews, similar } = detail;
  const best = c.best_attempt;
  const baselineRun = runs.find((r) => r.attempt === 0);
  const attemptRuns = runs.filter((r) => r.attempt > 0);
  const layers: Layer[] = [
    { key: "original", label: "Original image", url: c.assets?.original ?? `/files/cases/${c._id}/derived/original.png` },
    { key: "baseline", label: "Baseline segmentation (red = suspicious)", url: baselineRun?.overlay_url },
    ...attemptRuns.map((r) => ({
      key: `a${r.attempt}`,
      label: `Attempt ${r.attempt}: ${r.tool}${r.attempt === best?.attempt ? " ★ best" : ""}`,
      url: r.overlay_url,
    })),
    { key: "reference", label: "Reference (ground truth)", url: c.assets?.reference_overlay },
  ];
  const latest = attemptRuns.at(-1);
  const rightDefault = best ? `a${best.attempt}` : latest ? `a${latest.attempt}` : "original";
  const plannerActor = steps.find((s) => s.kind === "decision")?.actor ?? c.planner;
  const rerun = () => {
    setRerunning(true);
    setRerunError(null);
    api
      .rerun(c._id)
      .catch((e) => {
        // "already running" just means another click got there first; anything else is shown.
        if (!/already running/i.test(e.message)) setRerunError(e.message);
      })
      .finally(() => {
        setRerunning(false);
        load();
      });
  };

  return (
    <div className="stack">
      <div>
        <Link href="/" className="small">
          ← All investigations
        </Link>
        <div className="row spread" style={{ marginTop: "0.5rem" }}>
          <div>
            <h1>{c.title}</h1>
            <div className="row small">
              <StatusBadge status={c.status} />
              {plannerActor && (
                <>
                  <span className="muted">lead investigator</span> <ActorChip actor={plannerActor} />
                </>
              )}
              {c.researcher && <span className="muted">· {c.researcher}</span>}
              {!c.has_reference && <span className="tag">no reference mask — proxy checks only</span>}
              {c.tags?.map((t) => (
                <span key={t} className="tag">
                  {t}
                </span>
              ))}
            </div>
          </div>
          {!running && (
            <button className="btn" onClick={rerun} disabled={rerunning}>
              {rerunning ? "Starting…" : "Re-run investigation"}
            </button>
          )}
        </div>
        {rerunError && <p className="error-box small">{rerunError}</p>}
        {c.notes && <p className="muted small">Notes: {c.notes}</p>}
        {c.error && <p className="error-box small">{c.error}</p>}
      </div>

      <div className="case-layout">
        <div className="stack">
          <section className="panel">
            <h2>Evidence board</h2>
            <ImageViewer layers={layers} left="baseline" right={rightDefault} />
          </section>

          <section className="panel">
            <h2>Verification</h2>
            {c.baseline_metrics ? (
              <>
                {best?.metrics && (
                  <div className="hero-metric">
                    <div>
                      <span className="muted small">Instance F1</span>
                      <strong>
                        {c.baseline_metrics.f1.toFixed(2)} → <span className="up">{best.metrics.f1.toFixed(2)}</span>
                      </strong>
                    </div>
                    <div>
                      <span className="muted small">Cell count (ref {best.metrics.ref_count})</span>
                      <strong>
                        {c.baseline_metrics.pred_count} → {best.metrics.pred_count}
                      </strong>
                    </div>
                    <div>
                      <span className="muted small">Merged objects</span>
                      <strong>
                        {c.baseline_metrics.merged_objects} → {best.metrics.merged_objects}
                      </strong>
                    </div>
                  </div>
                )}
                <MetricsComparison before={c.baseline_metrics} after={best?.metrics} refCount={c.baseline_metrics.ref_count} />
              </>
            ) : c.baseline_summary ? (
              <ProxyComparison before={c.baseline_summary} after={best?.mask_summary} />
            ) : (
              <p className="muted">Waiting for baseline measurements…</p>
            )}
            <h3 style={{ marginTop: "1rem" }}>Attempts</h3>
            <AttemptsTable runs={runs} best={best?.attempt} />
            {best?.mask_url && (
              <p className="small">
                <a href={fileUrl(best.mask_url)}>Download repaired label mask (TIFF)</a>
              </p>
            )}
          </section>

          {c.report && (
            <section className="panel">
              <h2>Investigation report</h2>
              <p>{c.report.summary}</p>
              {c.hypothesis && (
                <p className="small">
                  <span className="muted">Final hypothesis:</span> {c.hypothesis}
                </p>
              )}
              <div className="grid grid-2">
                {[
                  ["What changed", c.report.what_changed],
                  ["Improvements (measured)", c.report.improvements],
                  ["Remaining uncertainty", c.report.uncertainties],
                ].map(([title, items]) =>
                  (items as string[]).length ? (
                    <div key={title as string}>
                      <h3>{title as string}</h3>
                      <ul className="small" style={{ paddingLeft: "1.1rem", margin: 0 }}>
                        {(items as string[]).map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null,
                )}
              </div>
              {c.report.recommendation && <p className="small muted">Recommendation: {c.report.recommendation}</p>}
            </section>
          )}
        </div>

        <div className="stack">
          <section className="panel">
            <h2>Human review</h2>
            <ReviewPanel c={c} reviews={reviews} onDone={load} />
          </section>
          <section className="panel">
            <h2>Investigation timeline</h2>
            <InvestigationTimeline steps={steps} running={running} />
          </section>
          {similar.length > 0 && (
            <section className="panel">
              <h2>Similar past investigations</h2>
              <p className="muted small">
                Matched on failure tags and image/mask fingerprint
                {similar[0].via ? ` · ${similar[0].via}` : ""}
              </p>
              {similar.map((s) => (
                <div key={s.case_id} className="row small" style={{ marginBottom: "0.4rem" }}>
                  <Link href={`/cases/${s.case_id}`}>{s.title}</Link>
                  <span className="muted">fixed with {s.successful_tool}</span>
                  <span className={`badge s-${s.status}`}>{s.status.replace("_", " ")}</span>
                </div>
              ))}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
