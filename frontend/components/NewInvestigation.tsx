"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API, api, type Sample } from "@/lib/api";

export default function NewInvestigation() {
  const router = useRouter();
  const [samples, setSamples] = useState<Sample[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.samples().then(setSamples).catch((e) => setError(e.message));
  }, []);

  async function start(fn: () => Promise<{ _id: string }>, key: string) {
    setBusy(key);
    setError(null);
    try {
      const c = await fn();
      router.push(`/cases/${c._id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  function onUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const ref = form.get("reference_mask") as File | null;
    if (ref && !ref.name) form.delete("reference_mask");
    start(() => api.upload(form), "upload");
  }

  return (
    <div className="stack">
      <section className="panel">
        <h2>Open a sample case</h2>
        <div className="grid grid-cards">
          {samples.map((s) => (
            <div key={s.id} className="sample-card">
              <img src={`${API}${s.preview}`} alt={s.title} />
              <strong>{s.title}</strong>
              <span className="muted small">{s.notes}</span>
              <span className="small">
                Reference {s.reference_count} nuclei · baseline found {s.baseline_count}
              </span>
              <button className="btn btn-primary" disabled={!!busy} onClick={() => start(() => api.fromSample(s.id), s.id)}>
                {busy === s.id ? "Opening…" : "Investigate"}
              </button>
            </div>
          ))}
          {!samples.length && !error && <p className="muted">Loading samples…</p>}
        </div>
      </section>

      <section className="panel">
        <h2>Upload your own</h2>
        <form onSubmit={onUpload} className="grid grid-2">
          <div>
            <label>
              Microscopy image (PNG/TIFF) *
              <input type="file" name="image" accept=".png,.tif,.tiff,.jpg,.jpeg" required />
            </label>
            <label>
              Existing segmentation mask *
              <input type="file" name="baseline_mask" accept=".png,.tif,.tiff" required />
            </label>
            <label>
              Reference mask (optional — enables independent verification)
              <input type="file" name="reference_mask" accept=".png,.tif,.tiff" />
            </label>
          </div>
          <div>
            <label>
              Title
              <input name="title" placeholder="e.g. Plate 3, well B4" />
            </label>
            <label>
              Researcher
              <input name="researcher" />
            </label>
            <label>
              Experiment notes / analysis settings
              <textarea name="notes" rows={3} />
            </label>
            <button className="btn btn-primary" disabled={!!busy}>
              {busy === "upload" ? "Uploading…" : "Upload and investigate"}
            </button>
          </div>
        </form>
      </section>
      {error && <p className="error-box">Backend error: {error}. Is the API running at {API}?</p>}
    </div>
  );
}
