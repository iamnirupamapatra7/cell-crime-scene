"""Read-only inspection: image quality statistics and suspicious-region detection."""
import numpy as np
from skimage import filters, measure, restoration


def inspect_image(img: np.ndarray) -> dict:
    otsu = float(filters.threshold_otsu(img))
    fg = img > otsu
    noise = float(restoration.estimate_sigma(img))
    fg_mean = float(img[fg].mean()) if fg.any() else 0.0
    bg_mean = float(img[~fg].mean()) if (~fg).any() else 0.0
    return {
        "shape": list(img.shape),
        "mean": float(img.mean()),
        "std": float(img.std()),
        "otsu_threshold": otsu,
        "foreground_fraction": float(fg.mean()),
        "noise_sigma": noise,
        "contrast": fg_mean - bg_mean,
        "snr": (fg_mean - bg_mean) / max(noise, 1e-6),
    }


def analyze_mask(labels: np.ndarray) -> dict:
    props = measure.regionprops(labels)
    if not props:
        return {"object_count": 0, "median_area": 0.0, "mean_area": 0.0, "area_cv": 0.0,
                "mean_solidity": 0.0, "foreground_fraction": 0.0}
    areas = np.array([p.area for p in props], dtype=float)
    return {
        "object_count": len(props),
        "median_area": float(np.median(areas)),
        "mean_area": float(areas.mean()),
        "area_cv": float(areas.std() / areas.mean()),
        "mean_solidity": float(np.mean([p.solidity for p in props])),
        "foreground_fraction": float((labels > 0).mean()),
    }


def find_suspicious_regions(labels: np.ndarray, typical_area: float | None = None,
                            area_factor: float = 1.6, solidity_threshold: float = 0.9) -> list[dict]:
    """Flag objects that look like merged nuclei: unusually large or with concave outlines.

    `typical_area` lets later attempts be judged against the baseline's nucleus size rather
    than their own (which shifts as merges are split).
    """
    props = measure.regionprops(labels)
    if not props:
        return []
    median = typical_area or float(np.median([p.area for p in props]))
    found = []
    for p in props:
        reasons = []
        if p.area > area_factor * median:
            reasons.append(f"area {int(p.area)} px is {p.area / median:.1f}x the typical nucleus")
        if p.solidity < solidity_threshold and p.area > 0.8 * median:
            reasons.append(f"concave outline (solidity {p.solidity:.2f})")
        if reasons:
            minr, minc, maxr, maxc = p.bbox
            found.append({
                "label": int(p.label),
                "bbox": [int(minr), int(minc), int(maxr), int(maxc)],
                "centroid": [round(float(c), 1) for c in p.centroid],
                "area": int(p.area),
                "solidity": round(float(p.solidity), 3),
                "eccentricity": round(float(p.eccentricity), 3),
                "estimated_nuclei": max(2, int(round(p.area / median))),
                "reasons": reasons,
            })
    return sorted(found, key=lambda r: -r["area"])
