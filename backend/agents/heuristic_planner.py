"""Deterministic offline planner. Used when no Gemini key is configured, or as a per-step fallback
when a Gemini call fails. Every step it takes is labelled 'heuristic' in the audit trail."""
import math

from agents.schemas import Decision, Report, ToolParams


def _key(tool, params, base=None):
    return tool, params.get("landscape"), params.get("target"), base or "baseline"


class HeuristicPlanner:
    name = "heuristic"

    def decide(self, state: dict, images=None) -> Decision:
        mask = state["baseline"]["mask"]
        attempts = state["attempts"]
        radius = math.sqrt(max(mask["typical_area"], 1) / math.pi)
        md = max(3, round(0.7 * radius))
        obs = [f"Baseline has {mask['object_count']} objects, {mask['suspicious_regions']} flagged as suspicious "
               f"(typical nucleus area {mask['typical_area']:.0f} px, radius ~{radius:.1f} px)."]

        if not attempts and mask["suspicious_regions"] == 0:
            return Decision(observations=obs, hypothesis="No evidence of merged nuclei in this mask.",
                            action="abstain", rationale="Nothing is oversized or concave; repair would be guesswork.",
                            confidence=0.7)

        if attempts:
            last = attempts[-1]
            v = last["verdict"]
            m = last.get("metrics") or {}
            refined = any(a.get("base") == "best" for a in attempts)
            if v["passed"] and m.get("merged_objects", 0) > 0 and state["remaining_attempts"] > 1 and not refined:
                return Decision(
                    observations=obs + [f"Attempt {last['attempt']} passed but {m['merged_objects']} merged objects "
                                        "remain."],
                    hypothesis="Remaining merges have a weak shape cue; the intensity seam may separate them.",
                    action="watershed_split",
                    params=ToolParams(base="best", min_distance=md, sigma=1.5, landscape="intensity",
                                      target="suspicious"),
                    rationale="Refine the best attempt on its remaining suspicious regions only.", confidence=0.55)
            if v["passed"] or v.get("unverified_improvement"):
                return Decision(observations=obs + [f"Attempt {last['attempt']} passed verification."],
                                hypothesis=state.get("hypothesis") or "Adjacent nuclei were merged.",
                                action="accept", rationale="Independent verification passed; send for human review.",
                                confidence=0.8)
            if state.get("best_attempt"):
                return Decision(observations=obs + [f"Attempt {last['attempt']} did not beat verified attempt "
                                                    f"{state['best_attempt']}."],
                                hypothesis=state.get("hypothesis") or "Adjacent nuclei were merged.",
                                action="accept", rationale="Further retries are not improving on the verified "
                                                           "attempt; send it for human review.", confidence=0.7)
            base_m = state["baseline"].get("metrics") or {}
            if last["tool"] == "watershed_split" and (
                    m.get("split_objects", 0) > base_m.get("split_objects", 0) or m.get("count_error", 0) > 0):
                p = dict(last["params"], min_distance=last["params"]["min_distance"] + 3)
                return Decision(
                    observations=obs + [f"Attempt {last['attempt']} over-split: count error {m.get('count_error'):+d},"
                                        f" split objects {m.get('split_objects')}."],
                    hypothesis="Merges are real but the watershed seeds are too dense.",
                    action="watershed_split", params=ToolParams(**p),
                    rationale="Raise min_distance to suppress spurious seeds.", confidence=0.6)

        plan = [
            ("watershed_split", {"min_distance": md, "sigma": 1.0, "landscape": "distance", "target": "suspicious"},
             "Merged nuclei are round; the distance transform should have one peak per nucleus."),
            ("watershed_split", {"min_distance": md, "sigma": 1.5, "landscape": "intensity", "target": "suspicious"},
             "Shape alone is ambiguous; use the dim seam in intensity between nuclei."),
            ("erosion_split", {"radius": max(2, round(radius / 3)), "target": "suspicious"},
             "Nuclei may be joined by thin bridges that erosion can break."),
            ("watershed_split", {"min_distance": max(3, round(0.6 * radius)), "sigma": 1.0,
                                 "landscape": "distance", "target": "all"},
             "Suspicious-region detection may have missed merges; apply to every object."),
        ]
        tried = {_key(a["tool"], a["params"], a.get("base")) for a in attempts}
        for tool, params, why in plan:
            if _key(tool, params) not in tried:
                return Decision(observations=obs, hypothesis="Adjacent nuclei were merged by global thresholding "
                                                             "(under-segmentation).",
                                action=tool, params=ToolParams(**params), rationale=why, confidence=0.6)

        if state.get("best_attempt"):
            return Decision(observations=obs, hypothesis="Adjacent nuclei were merged.", action="accept",
                            rationale="Strategies exhausted; best verified attempt goes to review.", confidence=0.5)
        return Decision(observations=obs, hypothesis="Merges could not be repaired with the allowed tools.",
                        action="abstain", rationale="No attempt passed verification.", confidence=0.6)

    def write_report(self, final_state: dict) -> Report:
        best = final_state.get("best_attempt")
        base = final_state["baseline"]
        if not best and final_state["status"] == "no_issue_found":
            return Report(summary="No oversized or concave objects were found; the baseline mask was left unchanged.",
                          uncertainties=["Merges between very small nuclei may fall below the detection thresholds."],
                          recommendation="Confirm by spot-checking the overlay.")
        if not best:
            return Report(summary="No repair passed independent verification; the case is flagged for manual review.",
                          uncertainties=["The failure may need a tool outside the current allowlist."],
                          recommendation="Inspect the flagged regions manually.")
        bm, am = base.get("metrics"), best.get("metrics")
        improvements, changed = [], [f"Applied {best['tool']} with {best['params']} (attempt {best['attempt']})."]
        if bm and am:
            improvements = [
                f"Instance F1 {bm['f1']:.3f} -> {am['f1']:.3f}",
                f"Cell count {bm['pred_count']} -> {am['pred_count']} (reference {am['ref_count']})",
                f"Merged objects {bm['merged_objects']} -> {am['merged_objects']}",
                f"Foreground IoU {bm['foreground_iou']:.3f} -> {am['foreground_iou']:.3f}",
            ]
        uncertainties = ["Verified on this image only; performance on other images is not established."]
        if not (bm and am):
            uncertainties.insert(0, "No reference mask: the improvement is a proxy (fewer suspicious regions), "
                                    "not a verified result.")
        elif am["merged_objects"]:
            uncertainties.append(f"{am['merged_objects']} merged objects remain.")
        return Report(summary=f"Repair with {best['tool']} " +
                              ("passed independent verification." if best.get("verified") else
                               "reduced suspicious regions but is unverified."),
                      what_changed=changed, improvements=improvements, uncertainties=uncertainties,
                      recommendation="Review the before/after overlay and approve or reject.")
