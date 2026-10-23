"use client";

import { useEffect, useState } from "react";
import { fileUrl } from "@/lib/api";

export type Layer = { key: string; label: string; url?: string | null };

function Pane({ layers, value, onChange }: { layers: Layer[]; value: string; onChange: (k: string) => void }) {
  const layer = layers.find((l) => l.key === value) ?? layers[0];
  return (
    <figure>
      {layer?.url ? <img src={fileUrl(layer.url)} alt={layer.label} /> : <div className="muted">No image</div>}
      <figcaption>
        <select value={layer?.key} onChange={(e) => onChange(e.target.value)} aria-label="Layer">
          {layers.map((l) => (
            <option key={l.key} value={l.key}>
              {l.label}
            </option>
          ))}
        </select>
      </figcaption>
    </figure>
  );
}

/** Side-by-side comparison of any two layers (original, baseline, attempts, reference). */
export default function ImageViewer({ layers, left, right }: { layers: Layer[]; left: string; right: string }) {
  const [a, setA] = useState(left);
  const [b, setB] = useState(right);
  // Follow the defaults as new attempts arrive, until the user picks something else.
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!touched) {
      setA(left);
      setB(right);
    }
  }, [left, right, touched]);

  const available = layers.filter((l) => l.url);
  return (
    <div className="viewer">
      <Pane layers={available} value={a} onChange={(k) => (setTouched(true), setA(k))} />
      <Pane layers={available} value={b} onChange={(k) => (setTouched(true), setB(k))} />
    </div>
  );
}
