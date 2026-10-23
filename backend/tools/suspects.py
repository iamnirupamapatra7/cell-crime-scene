"""Per-region verdicts for the suspect lineup: what happened to each flagged region after repair."""
import numpy as np


def _pieces(labels, region, min_share=0.1):
    """Distinct labels covering at least min_share of the region."""
    vals, counts = np.unique(labels[region], return_counts=True)
    keep = (vals > 0) & (counts >= min_share * region.sum())
    return int(keep.sum())


def _ref_nuclei(ref, region):
    """Reference nuclei with most of their area inside the region."""
    vals, counts = np.unique(ref[region], return_counts=True)
    n = 0
    for v, c in zip(vals, counts):
        if v and c > 0.5 * (ref == v).sum():
            n += 1
    return n


def suspect_verdicts(baseline, repaired, ref, suspicious, limit=8) -> list[dict]:
    out = []
    for i, r in enumerate(suspicious[:limit], 1):
        region = baseline == r["label"]
        after = _pieces(repaired, region) if repaired is not None else 1
        entry = {"rank": i, "label": r["label"], "bbox": r["bbox"], "area": r["area"], "solidity": r["solidity"],
                 "estimated_nuclei": r["estimated_nuclei"], "reasons": r["reasons"], "pieces_after": after}
        if ref is None:
            entry |= {"ref_nuclei": None, "verdict": "split (unverified)" if after > 1 else "unchanged",
                      "outcome": "unverified"}
        else:
            n = _ref_nuclei(ref, region)
            if n >= 2:
                verdict, outcome = (("solved", "good") if after == n else
                                    ("over-split", "bad") if after > n else
                                    ("partly split", "partial") if after > 1 else ("still merged", "bad"))
            else:
                verdict, outcome = ("correctly left whole", "good") if after <= 1 else ("wrongly split", "bad")
            entry |= {"ref_nuclei": n, "verdict": verdict, "outcome": outcome}
        out.append(entry)
    return out
