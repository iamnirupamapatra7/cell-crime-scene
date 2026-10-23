import type { Round, RoundEntry } from "@/lib/api";

function result(e: RoundEntry) {
  if (e.passed) return <span className="chip chip-good">passed</span>;
  if (e.unverified_improvement) return <span className="chip chip-warn">unverified</span>;
  return (
    <span className="chip chip-bad" title={e.failed_checks.join(", ")}>
      failed
    </span>
  );
}

/** One leaderboard per round: competing hypotheses, each independently verified, ranked by instance F1. */
export default function Tournament({ rounds, best, baselineF1 }: { rounds: Round[]; best?: number; baselineF1?: number }) {
  if (!rounds.length) return <p className="muted">No tournament rounds yet.</p>;
  return (
    <div className="stack" style={{ gap: "0.75rem" }}>
      {rounds.map((r) => (
        <div key={r.round} className="round">
          <div className="row spread">
            <h3 style={{ margin: 0 }}>Round {r.round}</h3>
            <span className="muted small">
              {r.entries.length} competing hypotheses ·{" "}
              {r.winner ? `winner: attempt ${r.winner}` : "no candidate passed"}
            </span>
          </div>
          {r.entries.map((e, i) => {
            const f1 = e.f1 ?? 0;
            return (
              <div key={e.attempt} className={`entry ${e.attempt === r.winner ? "entry-winner" : ""}`}>
                <div className="entry-rank">{e.attempt === r.winner ? "🏆" : `#${i + 1}`}</div>
                <div className="entry-body">
                  <div className="row">
                    <strong>{e.candidate}</strong>
                    {result(e)}
                    {e.attempt === best && <span className="chip chip-best">★ overall best</span>}
                    <code className="muted">
                      {e.tool}
                      {e.base === "best" ? " (on winner)" : ""}
                    </code>
                  </div>
                  <div className="muted small">{e.hypothesis}</div>
                  {e.f1 !== null && (
                    <div className="bar-row">
                      <div className="bar">
                        <div className={`bar-fill ${e.passed ? "good" : "bad"}`} style={{ width: `${f1 * 100}%` }} />
                        {baselineF1 !== undefined && <div className="bar-base" style={{ left: `${baselineF1 * 100}%` }} />}
                      </div>
                      <span className="small num">F1 {f1.toFixed(3)}</span>
                      <span className="small muted">
                        count err {e.count_error! > 0 ? "+" : ""}
                        {e.count_error} · merged {e.merged_objects}
                      </span>
                    </div>
                  )}
                  {e.f1 === null && <div className="small muted">{e.suspicious_after} suspicious regions left</div>}
                </div>
              </div>
            );
          })}
        </div>
      ))}
      {baselineF1 !== undefined && (
        <p className="muted small" style={{ margin: 0 }}>
          Grey tick = baseline F1 ({baselineF1.toFixed(3)}). Pass/fail comes from the independent verifier, not the agent.
        </p>
      )}
    </div>
  );
}
