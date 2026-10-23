import { fileUrl, type Suspect } from "@/lib/api";

/** Square crop around a region, cut from a full overlay with CSS so no extra files are needed. */
function Crop({ url, bbox, shape, label }: { url?: string | null; bbox: Suspect["bbox"]; shape: [number, number]; label: string }) {
  if (!url) return null;
  const [H, W] = shape;
  const [r0, c0, r1, c1] = bbox;
  const size = Math.min(Math.max(r1 - r0, c1 - c0) * 1.6 + 8, H, W);
  const top = Math.min(Math.max((r0 + r1) / 2 - size / 2, 0), H - size);
  const left = Math.min(Math.max((c0 + c1) / 2 - size / 2, 0), W - size);
  const pct = (offset: number, full: number) => (full - size > 0 ? (offset / (full - size)) * 100 : 0);
  return (
    <figure className="crop">
      <div
        role="img"
        aria-label={label}
        style={{
          backgroundImage: `url(${fileUrl(url)})`,
          backgroundSize: `${(W / size) * 100}% ${(H / size) * 100}%`,
          backgroundPosition: `${pct(left, W)}% ${pct(top, H)}%`,
        }}
      />
      <figcaption>{label}</figcaption>
    </figure>
  );
}

const ICON: Record<Suspect["outcome"], string> = { good: "✓", partial: "◐", bad: "✗", unverified: "?" };

export default function Suspects({
  suspects,
  shape,
  baselineUrl,
  repairedUrl,
  referenceUrl,
}: {
  suspects: Suspect[];
  shape: [number, number];
  baselineUrl?: string | null;
  repairedUrl?: string | null;
  referenceUrl?: string | null;
}) {
  const good = suspects.filter((s) => s.outcome === "good").length;
  return (
    <>
      {suspects.some((s) => s.ref_nuclei !== null) && (
        <p className="muted small" style={{ marginTop: 0 }}>
          {good} of {suspects.length} flagged regions resolved correctly, judged against the reference annotation.
        </p>
      )}
      <div className="suspects">
        {suspects.map((s) => (
          <article key={s.label} className={`suspect o-${s.outcome}`}>
            <header className="row spread">
              <strong>Suspect #{s.rank}</strong>
              <span className={`chip chip-${s.outcome === "good" ? "good" : s.outcome === "bad" ? "bad" : "warn"}`}>
                {ICON[s.outcome]} {s.verdict}
              </span>
            </header>
            <div className="crops">
              <Crop url={baselineUrl} bbox={s.bbox} shape={shape} label="before" />
              <Crop url={repairedUrl} bbox={s.bbox} shape={shape} label="after" />
              <Crop url={referenceUrl} bbox={s.bbox} shape={shape} label="truth" />
            </div>
            <div className="small muted">
              {s.area} px · solidity {s.solidity} ·{" "}
              {s.ref_nuclei !== null ? `truth: ${s.ref_nuclei} nuclei` : `~${s.estimated_nuclei} nuclei by size`} · after:{" "}
              {s.pieces_after} {s.pieces_after === 1 ? "object" : "objects"}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
