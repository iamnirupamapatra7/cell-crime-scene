"""Independent verification. Pass/fail is computed here from measurements, never from the agent's explanation."""
import numpy as np
from skimage.segmentation import relabel_sequential

from tools.inspect_image import analyze_mask

ACCEPTANCE_POLICY = {
    "iou_match_threshold": 0.5,
    "min_f1_gain": 0.02,
    "max_foreground_iou_drop": 0.02,
    "min_foreground_overlap_with_baseline": 0.85,
}


def _overlaps(pred, ref):
    np_, nr = int(pred.max()) + 1, int(ref.max()) + 1
    counts = np.bincount(pred.ravel().astype(np.int64) * nr + ref.ravel(),
                         minlength=np_ * nr).reshape(np_, nr)
    return counts[1:, 1:], counts.sum(axis=1)[1:], counts.sum(axis=0)[1:]


def instance_metrics(pred: np.ndarray, ref: np.ndarray) -> dict:
    pred = relabel_sequential(pred)[0]
    ref = relabel_sequential(ref)[0]
    n_pred, n_ref = int(pred.max()), int(ref.max())
    fg_union = np.logical_or(pred > 0, ref > 0).sum()
    fg_iou = float(np.logical_and(pred > 0, ref > 0).sum() / fg_union) if fg_union else 1.0
    result = {"pred_count": n_pred, "ref_count": n_ref, "count_error": n_pred - n_ref,
              "abs_count_error": abs(n_pred - n_ref), "foreground_iou": fg_iou}
    if n_pred == 0 or n_ref == 0:
        return result | {"tp": 0, "fp": n_pred, "fn": n_ref, "precision": 0.0, "recall": 0.0, "f1": 0.0,
                         "mean_matched_iou": 0.0, "merged_objects": 0, "split_objects": 0}
    inter, area_p, area_r = _overlaps(pred, ref)
    union = area_p[:, None] + area_r[None, :] - inter
    iou = np.where(union > 0, inter / np.maximum(union, 1), 0)
    matches = iou > ACCEPTANCE_POLICY["iou_match_threshold"]  # unique at IoU > 0.5
    tp = int(matches.sum())
    precision, recall = tp / n_pred, tp / n_ref
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    # A predicted object that covers most of 2+ reference nuclei is a merge; the reverse is a split.
    covers_ref = (inter / area_r[None, :]) > 0.5
    covers_pred = (inter / area_p[:, None]) > 0.5
    merged = int((covers_ref.sum(axis=1) >= 2).sum())
    split = int((covers_pred.sum(axis=0) >= 2).sum())
    return result | {
        "tp": tp, "fp": n_pred - tp, "fn": n_ref - tp,
        "precision": precision, "recall": recall, "f1": f1,
        "mean_matched_iou": float(iou[matches].mean()) if tp else 0.0,
        "merged_objects": merged, "split_objects": split,
    }


def integrity_checks(baseline, candidate, image_checksum_ok: bool, tool: str) -> list[dict]:
    checks = [
        {"name": "original image unchanged", "passed": image_checksum_ok,
         "detail": "SHA-256 of the uploaded image matches the recorded checksum"},
        {"name": "mask shape matches image", "passed": candidate.shape == baseline.shape,
         "detail": f"{list(candidate.shape)} vs {list(baseline.shape)}"},
        {"name": "mask not empty", "passed": bool(candidate.max() > 0), "detail": f"{int(candidate.max())} objects"},
    ]
    n_base, n_cand = int(baseline.max()), int(candidate.max())
    checks.append({"name": "object count plausible", "passed": n_cand <= 3 * n_base + 5,
                   "detail": f"{n_cand} objects vs {n_base} in baseline"})
    if tool == "resegment_threshold":
        checks.append({"name": "foreground preserved", "passed": True,
                       "detail": "skipped: re-segmentation is expected to change the foreground"})
    else:
        union = np.logical_or(baseline > 0, candidate > 0).sum()
        overlap = np.logical_and(baseline > 0, candidate > 0).sum() / max(union, 1)
        limit = ACCEPTANCE_POLICY["min_foreground_overlap_with_baseline"]
        checks.append({"name": "foreground preserved", "passed": bool(overlap >= limit),
                       "detail": f"foreground overlap with baseline {overlap:.3f} (min {limit})"})
    return checks


def evaluate_candidate(baseline_metrics: dict | None, candidate_metrics: dict | None,
                       integrity: list[dict], suspicious_before: int, suspicious_after: int) -> dict:
    """Apply the acceptance policy. Without a reference mask the result can only be 'unverified'."""
    checks = list(integrity)
    if baseline_metrics is None or candidate_metrics is None:
        improved = suspicious_after < suspicious_before and all(c["passed"] for c in checks)
        checks.append({"name": "suspicious regions reduced (proxy)", "passed": suspicious_after < suspicious_before,
                       "detail": f"{suspicious_before} -> {suspicious_after}"})
        return {"mode": "reference_free", "passed": False, "unverified_improvement": improved, "checks": checks}

    p = ACCEPTANCE_POLICY
    f1_gain = candidate_metrics["f1"] - baseline_metrics["f1"]
    fg_drop = baseline_metrics["foreground_iou"] - candidate_metrics["foreground_iou"]
    checks += [
        {"name": "instance F1 improved", "passed": f1_gain >= p["min_f1_gain"],
         "detail": f"{baseline_metrics['f1']:.3f} -> {candidate_metrics['f1']:.3f} (need +{p['min_f1_gain']})"},
        {"name": "no material foreground IoU decline", "passed": fg_drop <= p["max_foreground_iou_drop"],
         "detail": f"{baseline_metrics['foreground_iou']:.3f} -> {candidate_metrics['foreground_iou']:.3f}"},
        {"name": "count error not worse", "passed":
            candidate_metrics["abs_count_error"] <= baseline_metrics["abs_count_error"],
         "detail": f"{baseline_metrics['count_error']:+d} -> {candidate_metrics['count_error']:+d}"},
    ]
    return {"mode": "reference", "passed": all(c["passed"] for c in checks), "checks": checks}


def mask_summary(labels, typical_area, suspicious) -> dict:
    return analyze_mask(labels) | {"suspicious_regions": len(suspicious), "typical_area": typical_area}
