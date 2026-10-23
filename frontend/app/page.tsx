"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import NewInvestigation from "@/components/NewInvestigation";
import { StatusBadge } from "@/components/StatusBadge";
import { api, type Case, type Health } from "@/lib/api";

function CaseRow({ c }: { c: Case }) {
  const before = c.baseline_metrics?.f1;
  const after = c.best_attempt?.metrics?.f1;
  return (
    <tr>
      <td>
        <Link href={`/cases/${c._id}`}>{c.title}</Link>
        <div className="row" style={{ marginTop: 2 }}>
          {c.tags?.slice(0, 4).map((t) => (
            <span key={t} className="tag">
              {t}
            </span>
          ))}
        </div>
      </td>
      <td>
        <StatusBadge status={c.status} />
      </td>
      <td className="num">
        {before !== undefined ? before.toFixed(2) : "—"}
        {after !== undefined && <> → <span className="up">{after.toFixed(2)}</span></>}
      </td>
      <td className="muted small">{new Date(c.created_at).toLocaleString()}</td>
    </tr>
  );
}

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ mode: string; results: Case[] } | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.cases().then(setCases).catch(() => {});
  }, []);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setResults(q.trim() ? await api.search(q.trim()) : null);
  }

  const shown = results ? results.results : cases;

  return (
    <div className="stack">
      <section>
        <h1>Who merged these nuclei?</h1>
        <p className="muted" style={{ maxWidth: 760 }}>
          Upload a microscopy image and its segmentation. The agent flags suspicious regions, forms a hypothesis, runs
          allowlisted repair tools, verifies every attempt independently against reference data, and hands you an
          auditable result to approve or reject.
        </p>
        {health && (
          <div className="row small">
            <span className="tag">planner: {health.planner}{health.model ? ` · ${health.model}` : ""}</span>
            <span className="tag">storage: {health.storage}</span>
            <span className="tag">attempt budget: {health.max_attempts}</span>
          </div>
        )}
      </section>

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <NewInvestigation />
        <section className="panel">
          <div className="row spread" style={{ marginBottom: "0.75rem" }}>
            <h2 style={{ margin: 0 }}>Investigations</h2>
            {results && <span className="tag">search: {results.mode}</span>}
          </div>
          <form onSubmit={onSearch} className="row" style={{ marginBottom: "0.75rem", flexWrap: "nowrap" }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: merged nuclei, low contrast, watershed…" />
            <button className="btn">Search</button>
          </form>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Status</th>
                  <th className="num">F1</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((c) => (
                  <CaseRow key={c._id} c={c} />
                ))}
              </tbody>
            </table>
          </div>
          {!shown.length && <p className="muted">{results ? "No matching investigations." : "No investigations yet."}</p>}
        </section>
      </div>
    </div>
  );
}
