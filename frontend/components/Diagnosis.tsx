import type { RootCause } from "@/lib/api";

export default function Diagnosis({ causes }: { causes: RootCause[] }) {
  return (
    <ol className="causes">
      {causes.map((c, i) => (
        <li key={i}>
          <div className="row">
            <strong>{c.cause}</strong>
            <span className={`chip lk-${c.likelihood}`}>{c.likelihood}</span>
          </div>
          <div className="muted small">Evidence: {c.evidence}</div>
        </li>
      ))}
    </ol>
  );
}
