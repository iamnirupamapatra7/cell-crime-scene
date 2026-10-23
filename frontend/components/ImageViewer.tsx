"use client";

import { useEffect, useState } from "react";
import { fileUrl } from "@/lib/api";
import CompareSlider from "./CompareSlider";

export type Layer = { key: string; label: string; url?: string | null };

function LayerSelect({ layers, value, onChange }: { layers: Layer[]; value: string; onChange: (k: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Layer">
      {layers.map((l) => (
        <option key={l.key} value={l.key}>
          {l.label}
        </option>
      ))}
    </select>
  );
}

function Pane({ layer, layers, onChange }: { layer?: Layer; layers: Layer[]; onChange: (k: string) => void }) {
  return (
    <figure>
      {layer?.url ? <img src={fileUrl(layer.url)} alt={layer.label} /> : <div className="muted">No image</div>}
      <figcaption>
        <LayerSelect layers={layers} value={layer?.key ?? ""} onChange={onChange} />
      </figcaption>
    </figure>
  );
}

/** Compare any two layers (original, baseline, attempts, change map, reference) side by side or with a slider. */
export default function ImageViewer({ layers, left, right }: { layers: Layer[]; left: string; right: string }) {
  const [a, setA] = useState(left);
  const [b, setB] = useState(right);
  const [mode, setMode] = useState<"slider" | "side">("slider");
  // Follow the defaults as new attempts arrive, until the user picks something else.
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!touched) {
      setA(left);
      setB(right);
    }
  }, [left, right, touched]);

  const available = layers.filter((l) => l.url);
  const la = available.find((l) => l.key === a) ?? available[0];
  const lb = available.find((l) => l.key === b) ?? available[available.length - 1];
  const pickA = (k: string) => (setTouched(true), setA(k));
  const pickB = (k: string) => (setTouched(true), setB(k));

  return (
    <div className="stack" style={{ gap: "0.6rem" }}>
      <div className="segmented" role="tablist">
        <button role="tab" aria-selected={mode === "slider"} onClick={() => setMode("slider")}>
          Before / after slider
        </button>
        <button role="tab" aria-selected={mode === "side"} onClick={() => setMode("side")}>
          Side by side
        </button>
      </div>
      {mode === "slider" && la?.url && lb?.url ? (
        <>
          <CompareSlider before={fileUrl(la.url)!} after={fileUrl(lb.url)!} beforeLabel={la.label} afterLabel={lb.label} />
          <div className="viewer">
            <LayerSelect layers={available} value={la.key} onChange={pickA} />
            <LayerSelect layers={available} value={lb.key} onChange={pickB} />
          </div>
        </>
      ) : (
        <div className="viewer">
          <Pane layer={la} layers={available} onChange={pickA} />
          <Pane layer={lb} layers={available} onChange={pickB} />
        </div>
      )}
    </div>
  );
}
