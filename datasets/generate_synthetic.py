"""Generate synthetic fluorescence-nucleus images with exact reference masks.

Each case has touching nuclei clusters and a baseline mask from a global-Otsu pipeline, which reproducibly
merges touching nuclei (under-segmentation). Demo cases go to sample_cases/; a separate held-out set goes to
datasets/heldout/ for evaluation.

    python datasets/generate_synthetic.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tools.io import save_labels  # noqa: E402
from tools.segment_cells import threshold_segment  # noqa: E402


def make_field(seed, size=384, n_single=14, n_clusters=6, max_cluster=3, contrast=1.0, noise=0.025,
               radius=(9, 14)):
    rng = np.random.default_rng(seed)
    nuclei = []  # (cy, cx, a, b, theta, cluster_id)

    def fits(cy, cx, r, cluster, mates_ok):
        if not (r + 4 < cy < size - r - 4 and r + 4 < cx < size - r - 4):
            return False
        for (y, x, a, b, _, cl) in nuclei:
            d = np.hypot(cy - y, cx - x)
            if cl == cluster and mates_ok:
                if d < 0.7 * (r + max(a, b)):
                    return False
            elif d < r + max(a, b) + 6:
                return False
        return True

    for c in range(n_clusters):
        for _ in range(200):
            a, b = rng.uniform(*radius), rng.uniform(*radius)
            cy, cx = rng.uniform(0, size, 2)
            if fits(cy, cx, max(a, b) * 2.5, c, False):
                nuclei.append((cy, cx, a, b, rng.uniform(0, np.pi), c))
                break
        members = rng.integers(2, max_cluster + 1)
        for _ in range(members - 1):
            for _ in range(100):
                y0, x0, a0, b0, _, _ = nuclei[rng.choice([i for i, n in enumerate(nuclei) if n[5] == c])]
                a, b = rng.uniform(*radius), rng.uniform(*radius)
                ang = rng.uniform(0, 2 * np.pi)
                d = (max(a0, b0) + max(a, b)) * rng.uniform(0.72, 0.85)
                cy, cx = y0 + d * np.sin(ang), x0 + d * np.cos(ang)
                if fits(cy, cx, max(a, b), c, True):
                    nuclei.append((cy, cx, a, b, rng.uniform(0, np.pi), c))
                    break
    for i in range(n_single):
        for _ in range(200):
            a, b = rng.uniform(*radius), rng.uniform(*radius)
            cy, cx = rng.uniform(0, size, 2)
            if fits(cy, cx, max(a, b), 1000 + i, False):
                nuclei.append((cy, cx, a, b, rng.uniform(0, np.pi), 1000 + i))
                break

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    labels = np.zeros((size, size), np.int32)
    best = np.full((size, size), np.inf, np.float32)
    signal = np.zeros((size, size), np.float32)
    for k, (cy, cx, a, b, th, _) in enumerate(nuclei, 1):
        dy, dx = yy - cy, xx - cx
        u = dx * np.cos(th) + dy * np.sin(th)
        v = -dx * np.sin(th) + dy * np.cos(th)
        rn2 = (u / a) ** 2 + (v / b) ** 2
        inside = rn2 <= 1
        claim = inside & (rn2 < best)
        labels[claim] = k
        best[claim] = rn2[claim]
        peak = rng.uniform(0.6, 1.0)
        signal = np.maximum(signal, np.where(inside, peak * (1 - 0.45 * rn2), 0))
    texture = 1 + 0.15 * ndi.gaussian_filter(rng.normal(size=(size, size)), 2) * 4
    img = 0.06 + contrast * signal * texture
    img = ndi.gaussian_filter(img, 1.5) + rng.normal(0, noise, (size, size))
    img = np.clip(img, 0, 1)
    baseline = threshold_segment(img.astype(np.float32), method="otsu", sigma=1.0, min_size=20)
    return (img * 255).astype(np.uint8), labels, baseline


def write_case(out_dir: Path, seed: int, meta: dict, **kw):
    out_dir.mkdir(parents=True, exist_ok=True)
    img, ref, baseline = make_field(seed, **kw)
    Image.fromarray(img).save(out_dir / "image.png")
    save_labels(out_dir / "reference_mask.tif", ref)
    save_labels(out_dir / "baseline_mask.tif", baseline)
    meta = meta | {"seed": seed, "reference_count": int(ref.max()), "baseline_count": int(baseline.max()),
                   "source": "synthetic (generate_synthetic.py)", "params": kw}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"{out_dir.name}: reference {ref.max()} nuclei, baseline {baseline.max()} objects")


SAMPLES = [
    ("merged_nuclei_demo", 7, dict(n_single=12, n_clusters=7),
     "Merged nuclei in a DAPI field",
     "Global Otsu pipeline. Expected ~one label per nucleus; adjacent nuclei appear merged."),
    ("dense_clusters", 21, dict(n_single=8, n_clusters=10, max_cluster=3),
     "Dense nuclear clusters",
     "High-density field with many 3-nucleus clusters; counts look low compared with manual counts."),
    ("low_contrast", 33, dict(n_single=12, n_clusters=6, contrast=0.55, noise=0.04),
     "Low-contrast noisy acquisition",
     "Dim staining and higher camera noise; segmentation settings tuned on brighter images."),
    ("clean_control", 45, dict(n_single=18, n_clusters=0),
     "Control field without touching nuclei",
     "Well-separated nuclei. Used to check the agent does not 'repair' a correct mask."),
]

if __name__ == "__main__":
    for sid, seed, kw, title, notes in SAMPLES:
        write_case(ROOT / "sample_cases" / sid, seed, {"title": title, "notes": notes,
                                                       "researcher": "Demo researcher"}, **kw)
    rng = np.random.default_rng(2026)
    for i in range(12):
        kw = dict(n_single=int(rng.integers(6, 16)), n_clusters=int(rng.integers(3, 10)),
                  contrast=float(rng.uniform(0.5, 1.0)), noise=float(rng.uniform(0.015, 0.045)))
        write_case(ROOT / "datasets" / "heldout" / f"heldout_{i:02d}", 10_000 + i,
                   {"title": f"Held-out field {i:02d}", "notes": "held-out evaluation image"}, **kw)
