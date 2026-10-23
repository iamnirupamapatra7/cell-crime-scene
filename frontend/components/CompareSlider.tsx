"use client";

import { useState } from "react";

/** Drag the divider to reveal `after` over `before`. Both images must have the same aspect ratio. */
export default function CompareSlider({
  before,
  after,
  beforeLabel,
  afterLabel,
}: {
  before: string;
  after: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const [pos, setPos] = useState(50);
  return (
    <div className="compare">
      <img src={before} alt={beforeLabel} />
      <img src={after} alt={afterLabel} className="compare-top" style={{ clipPath: `inset(0 0 0 ${pos}%)` }} />
      <div className="compare-line" style={{ left: `${pos}%` }} />
      <span className="compare-label left">{beforeLabel}</span>
      <span className="compare-label right">{afterLabel}</span>
      <input
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        aria-label="Reveal the repaired segmentation"
      />
    </div>
  );
}
