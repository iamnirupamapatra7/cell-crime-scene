import numpy as np
import pytest
from skimage.draw import disk

from tools import registry
from tools.inspect_image import find_suspicious_regions
from tools.repair_mask import erosion_split, watershed_split
from tools.verify_result import evaluate_candidate, instance_metrics, integrity_checks


def two_touching_discs():
    ref = np.zeros((80, 120), np.int32)
    ref[disk((40, 40), 15)] = 1
    ref[disk((40, 68), 15)] = 2
    ref[disk((40, 100), 10)] = 3
    merged = (ref > 0).astype(np.int32)
    merged[ref == 2] = 1
    merged[ref == 3] = 2
    img = (ref > 0).astype(np.float32)
    return img, ref, merged


def test_metrics_detect_merge():
    _, ref, merged = two_touching_discs()
    m = instance_metrics(merged, ref)
    assert m["pred_count"] == 2 and m["ref_count"] == 3
    assert m["merged_objects"] == 1
    assert m["tp"] == 2  # the overwriting disc still matches at IoU > 0.5
    assert m["foreground_iou"] == pytest.approx(1.0)
    assert instance_metrics(ref, ref)["f1"] == pytest.approx(1.0)


def test_suspicious_region_flags_merge():
    _, _, merged = two_touching_discs()
    found = find_suspicious_regions(merged, typical_area=np.pi * 15 ** 2)
    assert [r["label"] for r in found] == [1]


@pytest.mark.parametrize("tool", [watershed_split, erosion_split])
def test_split_repairs_merge_and_passes_policy(tool):
    img, ref, merged = two_touching_discs()
    kwargs = {"min_distance": 8} if tool is watershed_split else {"radius": 6}
    fixed, summary = tool(img, merged, suspicious_labels=[1], **kwargs)
    assert summary["regions_split"] == 1
    before, after = instance_metrics(merged, ref), instance_metrics(fixed, ref)
    assert after["f1"] == pytest.approx(1.0)
    verdict = evaluate_candidate(before, after, integrity_checks(merged, fixed, True, "x"), 1, 0)
    assert verdict["passed"]
    assert merged.max() == 2  # input not mutated


def test_policy_rejects_when_image_changed():
    img, ref, merged = two_touching_discs()
    fixed, _ = watershed_split(img, merged, min_distance=8, suspicious_labels=[1])
    verdict = evaluate_candidate(instance_metrics(merged, ref), instance_metrics(fixed, ref),
                                 integrity_checks(merged, fixed, False, "watershed_split"), 1, 0)
    assert not verdict["passed"]


def test_without_reference_never_passes():
    img, _, merged = two_touching_discs()
    fixed, _ = watershed_split(img, merged, min_distance=8, suspicious_labels=[1])
    verdict = evaluate_candidate(None, None, integrity_checks(merged, fixed, True, "x"), 1, 0)
    assert verdict["passed"] is False and verdict["unverified_improvement"] is True


def test_registry_clamps_and_rejects():
    params, notes = registry.validate_params("watershed_split", {"min_distance": 999, "landscape": "evil"})
    assert params["min_distance"] == 25 and params["landscape"] == "distance"
    assert len(notes) == 2
    with pytest.raises(ValueError):
        registry.validate_params("os.system", {})


def test_hybrid_search_ranks_similar_fingerprint_first(tmp_path):
    from services.atlas import LocalRepository

    repo = LocalRepository(tmp_path)
    repo.insert("cases", {"_id": "near", "title": "near", "tags": ["merged nuclei"], "fingerprint": [0.4, -0.2, 0.1]})
    repo.insert("cases", {"_id": "far", "title": "far", "tags": ["merged nuclei"], "fingerprint": [-0.4, 0.3, -0.1]})
    repo.insert("cases", {"_id": "other", "title": "other", "tags": ["noisy"], "fingerprint": [0.4, -0.2, 0.1]})
    vec, _ = repo.vector_search([0.4, -0.2, 0.1], 3)
    assert vec[-1]["_id"] == "far"
    hybrid, mode = repo.hybrid_search("merged nuclei", [0.4, -0.2, 0.1], 3)
    assert hybrid[0]["_id"] == "near" and mode.startswith("local-hybrid")


def test_suspect_verdicts_against_reference():
    import numpy as np
    from tools.suspects import suspect_verdicts

    ref = np.zeros((20, 40), np.int32)
    ref[5:15, 2:12], ref[5:15, 12:22] = 1, 2          # two touching nuclei
    ref[5:15, 28:36] = 3                               # one genuinely single nucleus
    baseline = np.zeros_like(ref)
    baseline[5:15, 2:22], baseline[5:15, 28:36] = 1, 2  # merged pair + single
    repaired = baseline.copy()
    repaired[5:15, 12:22] = 3                          # pair split correctly
    regions = [{"label": 1, "bbox": [5, 2, 15, 22], "area": 200, "solidity": 1.0, "estimated_nuclei": 2,
                "reasons": []},
               {"label": 2, "bbox": [5, 28, 15, 36], "area": 80, "solidity": 1.0, "estimated_nuclei": 1,
                "reasons": []}]
    v = suspect_verdicts(baseline, repaired, ref, regions)
    assert [s["verdict"] for s in v] == ["solved", "correctly left whole"]
    assert suspect_verdicts(baseline, baseline, ref, regions)[0]["verdict"] == "still merged"
