import type { Check, Step } from "@/lib/api";
import { ActorChip } from "./StatusBadge";

function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.name}>
          <span className={c.passed ? "up" : "down"}>{c.passed ? "✓" : "✗"}</span> {c.name}{" "}
          <span className="muted">— {c.detail}</span>
        </li>
      ))}
    </ul>
  );
}

function DecisionBody({ data }: { data: Record<string, any> }) {
  const params = Object.entries(data.params ?? {}).filter(([, v]) => v !== null && v !== undefined);
  return (
    <div className="small">
      {data.observations?.length > 0 && (
        <ul style={{ margin: "0.25rem 0", paddingLeft: "1.1rem" }}>
          {data.observations.map((o: string, i: number) => (
            <li key={i} style={{ border: 0, padding: 0, margin: 0 }} className="muted">
              {o}
            </li>
          ))}
        </ul>
      )}
      {params.length > 0 && (
        <div>
          <code>{params.map(([k, v]) => `${k}=${v}`).join("  ")}</code>
        </div>
      )}
      {typeof data.confidence === "number" && <div className="muted">confidence {data.confidence.toFixed(2)}</div>}
    </div>
  );
}

export default function InvestigationTimeline({ steps, running }: { steps: Step[]; running: boolean }) {
  return (
    <ol className="timeline">
      {steps.map((s) => (
        <li key={s._id} className={`k-${s.kind}`}>
          <div className="row">
            <span className="step-title">{s.title}</span>
            <ActorChip actor={s.actor} />
            <span className="tag">{s.kind}</span>
          </div>
          {s.detail && s.kind !== "error" && <div className="muted small">{s.detail}</div>}
          {s.kind === "decision" && s.data?.action && <DecisionBody data={s.data} />}
          {s.kind === "verify" && s.data?.checks && <Checks checks={s.data.checks} />}
          {(s.kind === "error" || Object.keys(s.data ?? {}).length > 0) && (
            <details>
              <summary>{s.kind === "error" ? "error detail" : "raw data"}</summary>
              <pre>{s.kind === "error" ? s.detail : JSON.stringify(s.data, null, 1)}</pre>
            </details>
          )}
        </li>
      ))}
      {running && (
        <li className="k-tool">
          <span className="pulse muted">Agent is working…</span>
        </li>
      )}
    </ol>
  );
}
