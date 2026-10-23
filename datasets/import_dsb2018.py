"""Import cases from the 2018 Data Science Bowl nuclei dataset (BBBC038) layout:

    <root>/<image_id>/images/<image_id>.png
    <root>/<image_id>/masks/*.png        (one binary PNG per nucleus)

Builds a reference label image from the per-nucleus masks and a global-Otsu baseline mask.
Only fluorescence images (grayscale, dark background) whose baseline actually merges nuclei are
kept, so every imported case reproduces the under-segmentation failure. Selected cases are split
deterministically into development cases and held-out evaluation cases.
Check the dataset's licence terms before redistributing any images.

    python datasets/import_dsb2018.py <root> --dev 6 --heldout 12
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tools.io import load_image, save_labels  # noqa: E402
from tools.segment_cells import threshold_segment  # noqa: E402
from tools.verify_result import instance_metrics  # noqa: E402


def is_fluorescence(path: Path) -> bool:
    """Fluorescence nuclei images are grayscale (R == G == B) on a dark background."""
    rgb = np.asarray(Image.open(path))[..., :3].astype(np.float32)
    if rgb.ndim != 3 or np.abs(rgb[..., 0] - rgb[..., 1]).mean() > 1 or np.abs(rgb[..., 1] - rgb[..., 2]).mean() > 1:
        return False
    gray = rgb[..., 0]
    return np.median(gray) < 0.25 * max(float(gray.max()), 1.0)


def load_case(case: Path):
    img = load_image(next((case / "images").glob("*.png")))
    ref = np.zeros(img.shape, np.int32)
    for k, m in enumerate(sorted((case / "masks").glob("*.png")), 1):
        ref[np.asarray(Image.open(m)) > 0] = k
    return img, ref, threshold_segment(img, "otsu", 1.0, 20)


def write_case(out: Path, case: Path, img, ref, baseline, metrics, title: str):
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray((img * 255).astype(np.uint8)).save(out / "image.png")
    save_labels(out / "reference_mask.tif", ref)
    save_labels(out / "baseline_mask.tif", baseline)
    (out / "meta.json").write_text(json.dumps({
        "title": title,
        "notes": "Fluorescence nuclei, global Otsu pipeline. Adjacent nuclei appear merged in the baseline.",
        "researcher": "", "source": "DSB 2018 / BBBC038 stage1_train", "image_id": case.name,
        "reference_count": int(ref.max()), "baseline_count": int(baseline.max()),
        "baseline_merged_objects": metrics["merged_objects"], "baseline_f1": round(metrics["f1"], 3)}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--dev", type=int, default=6, help="development cases written to sample_cases/")
    ap.add_argument("--heldout", type=int, default=12, help="evaluation cases written to datasets/heldout_dsb/")
    ap.add_argument("--min-merged", type=int, default=2, help="baseline must merge at least this many objects")
    ap.add_argument("--max-nuclei", type=int, default=150, help="skip very crowded fields (slow, hard to view)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cases = sorted(p for p in args.root.iterdir() if (p / "images").is_dir())
    random.Random(args.seed).shuffle(cases)
    selected, scanned = [], 0
    need = args.dev + args.heldout
    for case in cases:
        if len(selected) >= need:
            break
        scanned += 1
        if not is_fluorescence(next((case / "images").glob("*.png"))):
            continue
        img, ref, baseline = load_case(case)
        if not 5 <= ref.max() <= args.max_nuclei:
            continue
        metrics = instance_metrics(baseline, ref)
        if metrics["merged_objects"] < args.min_merged:
            continue
        selected.append((case, img, ref, baseline, metrics))
        print(f"{case.name[:10]}: reference {ref.max()}, baseline {baseline.max()}, "
              f"merged {metrics['merged_objects']}, F1 {metrics['f1']:.3f}")

    print(f"\nscanned {scanned}, selected {len(selected)}")
    for i, (case, img, ref, baseline, metrics) in enumerate(selected):
        if i < args.dev:
            write_case(ROOT / "sample_cases" / f"dsb_{case.name[:10]}", case, img, ref, baseline, metrics,
                       f"DSB2018 fluorescence field {case.name[:6]}")
        else:
            write_case(ROOT / "datasets" / "heldout_dsb" / f"dsb_{case.name[:10]}", case, img, ref, baseline,
                       metrics, f"Held-out DSB2018 field {case.name[:6]}")


if __name__ == "__main__":
    main()
