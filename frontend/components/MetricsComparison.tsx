import type { MaskSummary, Metrics, Run } from "@/lib/api";

type Row = { label: string; get: (m: Metrics) => number; fmt?: (v: number) => string; better: "up" | "down" | "zero" };

const fixed3 = (v: number) => v.toFixed(3);
const signed = (v: number) => (v > 0 ? `+${v}` : `${v}`);

const ROWS: Row[] = [
  { label: "Instance F1 (IoU > 0.5)", get: (m) => m.f1, fmt: fixed3, better: "up" },
  { label: "Precision", get: (m) => m.precision, fmt: fixed3, better: "up" },
  { label: "Recall", get: (m) => m.recall, fmt: fixed3, better: "up" },
  { label: "Cell count", get: (m) => m.pred_count, better: "zero" },
  { label: "Count error vs reference", get: (m) => m.count_error, fmt: signed, better: "zero" },
  { label: "Merged objects", get: (m) => m.merged_objects, better: "down" },
  { label: "Over-split nuclei", get: (m) => m.split_objects, better: "down" },
  { label: "Foreground IoU", get: (m) => m.foreground_iou, fmt: fixed3, better: "up" },
  { label: "Mean matched IoU", get: (m) => m.mean_matched_iou, fmt: fixed3, better: "up" },
];

function delta(row: Row, before: Metrics, after: Metrics) {
  const b = row.get(before);
  const a = row.get(after);
  const d = a - b;
  if (row.label === "Cell count") return { text: signed(d), cls: "" };
  if (Math.abs(d) < 1e-9) return { text: "—", cls: "muted" };
  const good = row.better === "up" ? d > 0 : row.better === "down" ? d < 0 : Math.abs(a) < Math.abs(b);
  const text = row.fmt === fixed3 ? (d > 0 ? "+" : "") + d.toFixed(3) : signed(d);
  return { text, cls: good ? "up" : "down" };
}

export function MetricsComparison({ before, after, refCount }: { before: Metrics; after?: Metrics | null; refCount: number }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Metric (reference: {refCount} nuclei)</th>
            <th className="num">Baseline</th>
            <th className="num">Repaired</th>
            <th className="num">Change</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const fmt = r.fmt ?? String;
            const d = after ? delta(r, before, after) : null;
            return (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">{fmt(r.get(before))}</td>
                <td className="num">{after ? fmt(r.get(after)) : "—"}</td>
                <td className={`num ${d?.cls ?? ""}`}>{d?.text ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ProxyComparison({ before, after }: { before: MaskSummary; after?: MaskSummary }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Proxy measure (no reference mask)</th>
          <th className="num">Baseline</th>
          <th className="num">Repaired</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Objects</td>
          <td className="num">{before.object_count}</td>
          <td className="num">{after?.object_count ?? "—"}</td>
        </tr>
        <tr>
          <td>Suspicious (merged-looking) regions</td>
          <td className="num">{before.suspicious_regions}</td>
          <td className="num">{after?.suspicious_regions ?? "—"}</td>
        </tr>
        <tr>
          <td>Mean solidity</td>
          <td className="num">{before.mean_solidity.toFixed(3)}</td>
          <td className="num">{after ? after.mean_solidity.toFixed(3) : "—"}</td>
        </tr>
      </tbody>
    </table>
  );
}

export function AttemptsTable({ runs, best }: { runs: Run[]; best?: number }) {
  const attempts = runs.filter((r) => r.attempt > 0);
  if (!attempts.length) return <p className="muted">No repair attempts yet.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Tool</th>
            <th>Parameters</th>
            <th className="num">F1</th>
            <th className="num">Count err</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map((r) => (
            <tr key={r._id}>
              <td>
                {r.attempt}
                {r.attempt === best && " ★"}
              </td>
              <td>
                {r.tool}
                <div className="muted small">on {r.base} mask</div>
              </td>
              <td>
                <code>
                  {Object.entries(r.params)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(" ")}
                </code>
              </td>
              <td className="num">{r.metrics ? r.metrics.f1.toFixed(3) : "—"}</td>
              <td className="num">{r.metrics ? signed(r.metrics.count_error) : "—"}</td>
              <td>
                {r.verdict?.passed ? (
                  <span className="up">passed</span>
                ) : r.verdict?.unverified_improvement ? (
                  <span style={{ color: "var(--warn)" }}>unverified</span>
                ) : (
                  <span className="down">failed</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
