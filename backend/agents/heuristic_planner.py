"""Deterministic offline planner. Used when no Gemini key is configured, or as a per-step fallback
when a Gemini call fails. Every step it takes is labelled 'heuristic' in the audit trail.

It plays the same game as Gemini: diagnose root causes, then run tournament rounds of competing
candidates, refine the winner, and accept or abstain.
"""
import math

from agents.schemas import Candidate, Decision, Report, RootCause, ToolParams


def _key(tool, params):
    return (tool, params.get("landscape"), params.get("target"), params.get("base") or "baseline",
            params.get("min_distance"), params.get("radius"))


def diagnose(state: dict) -> list[RootCause]:
    """Evidence-linked root causes from the Python measurements."""
    stats, mask = state["image_stats"], state["baseline"]["mask"]
    regions = state["baseline"]["suspicious_regions"]
    causes = []
    if mask["suspicious_regions"]:
        big = [r for r in regions if any("typical nucleus" in x for x in r["reasons"])]
        concave = [r for r in regions if any("concave" in x for x in r["reasons"])]
        biggest = max(regions, key=lambda r: r["area"])
        causes.append(RootCause(
            cause="Global threshold merges touching nuclei (under-segmentation)",
            evidence=f"{mask['suspicious_regions']} of {mask['object_count']} objects flagged: {len(big)} oversized, "
                     f"{len(concave)} with concave outlines; largest is region {biggest['label']} at "
                     f"{biggest['area']} px (~{biggest['estimated_nuclei']} nuclei).",
            likelihood="high"))
    if stats["foreground_fraction"] > 0.25:
        causes.append(RootCause(
            cause="Crowded field: nuclei touch, so a single threshold cannot separate them",
            evidence=f"{stats['foreground_fraction']:.0%} of the image is foreground.",
            likelihood="medium"))
    if stats["snr"] < 8:
        causes.append(RootCause(
            cause="Low contrast blurs the dim seam between adjacent nuclei",
            evidence=f"Signal-to-noise ratio {stats['snr']:.1f} (below 8).",
            likelihood="medium"))
    if stats["noise_sigma"] > 0.04:
        causes.append(RootCause(
            cause="Camera noise roughens boundaries and can bridge neighbouring nuclei",
            evidence=f"Estimated noise sigma {stats['noise_sigma']:.3f}.",
            likelihood="low"))
    if not causes:
        causes.append(RootCause(cause="No segmentation failure evident",
                                evidence="No oversized or concave objects in the baseline mask.", likelihood="medium"))
    return causes


class HeuristicPlanner:
    name = "heuristic"

    def decide(self, state: dict, images=None) -> Decision:
        mask = state["baseline"]["mask"]
        attempts = state["attempts"]
        per_round = state.get("candidates_per_round", 3)
        radius = math.sqrt(max(mask["typical_area"], 1) / math.pi)
        md = max(3, round(0.7 * radius))
        causes = diagnose(state)
        obs = [f"Baseline has {mask['object_count']} objects, {mask['suspicious_regions']} flagged as suspicious "
               f"(typical nucleus area {mask['typical_area']:.0f} px, radius ~{radius:.1f} px)."]
        hypothesis = causes[0].cause
        tried = {_key(a["tool"], a["params"] | {"base": a.get("base")}) for a in attempts}

        def fresh(cands):
            out = [c for c in cands if _key(c.tool, c.params.model_dump()) not in tried]
            return out[:per_round]

        def experiment(cands, rationale, extra_obs=()):
            return Decision(observations=obs + list(extra_obs), root_causes=causes, hypothesis=hypothesis,
                            action="experiment", candidates=cands, rationale=rationale, confidence=0.6)

        if not attempts and mask["suspicious_regions"] == 0:
            return Decision(observations=obs, root_causes=causes, hypothesis="No evidence of merged nuclei.",
                            action="abstain", rationale="Nothing is oversized or concave; repair would be guesswork.",
                            confidence=0.7)

        if not attempts:
            cands = fresh([
                Candidate(name="Shape split", tool="watershed_split",
                          hypothesis="Merged nuclei are round, so the distance transform has one peak per nucleus.",
                          params=ToolParams(min_distance=md, sigma=1.0, landscape="distance", target="suspicious")),
                Candidate(name="Seam split", tool="watershed_split",
                          hypothesis="A dim intensity seam separates touching nuclei even when the outline is convex.",
                          params=ToolParams(min_distance=md, sigma=1.5, landscape="intensity", target="suspicious")),
                Candidate(name="Bridge cut", tool="erosion_split",
                          hypothesis="Nuclei are joined by thin bridges that erosion can break.",
                          params=ToolParams(radius=max(2, round(radius / 3)), target="suspicious")),
            ])
            return experiment(cands, "Three competing explanations for the merges; test all and keep what verifies.")

        best = state.get("best_attempt")
        best_run = next((a for a in attempts if a["attempt"] == best), None)
        remaining = state.get("remaining_rounds", 0)
        if best_run:
            m = best_run.get("metrics") or {}
            refined = any(a.get("base") == "best" for a in attempts)
            if m.get("merged_objects", 0) > 0 and remaining > 0 and not refined:
                p = best_run["params"]
                cands = fresh([
                    Candidate(name="Refine: seam", tool="watershed_split",
                              hypothesis="The remaining merges have a weak shape cue; the intensity seam may split them.",
                              params=ToolParams(base="best", min_distance=md, sigma=1.5, landscape="intensity",
                                                target="suspicious")),
                    Candidate(name="Refine: finer seeds", tool="watershed_split",
                              hypothesis="The winning split used seeds that were too sparse for the smallest nuclei.",
                              params=ToolParams(base="best", min_distance=max(3, (p.get("min_distance") or md) - 2),
                                                sigma=1.0, landscape="distance", target="suspicious")),
                ])
                if cands:
                    return experiment(cands, f"Attempt {best} won but {m['merged_objects']} merged objects remain; "
                                             "refine the winner on what is still flagged.",
                                      [f"Attempt {best} is the current best."])
            return Decision(observations=obs + [f"Attempt {best} is the best verified result."], root_causes=causes,
                            hypothesis=hypothesis, action="accept",
                            rationale="Independent verification passed and further rounds are not improving on it.",
                            confidence=0.8)

        # Nothing has passed yet.
        base_m = state["baseline"].get("metrics") or {}
        oversplit = any((a.get("metrics") or {}).get("split_objects", 0) > base_m.get("split_objects", 0)
                        or (a.get("metrics") or {}).get("count_error", 0) > 0 for a in attempts)
        if remaining > 0:
            cands = fresh([
                Candidate(name="Sparser seeds", tool="watershed_split",
                          hypothesis="Merges are real but the seeds were too dense and over-split nuclei.",
                          params=ToolParams(min_distance=md + 3, sigma=1.5, landscape="distance", target="suspicious")),
                Candidate(name="Sweep all objects", tool="watershed_split",
                          hypothesis="Suspicious-region detection missed merges; apply the split to every object.",
                          params=ToolParams(min_distance=max(3, round(0.6 * radius)), sigma=1.0, landscape="distance",
                                            target="all")),
                Candidate(name="Much sparser seeds", tool="watershed_split",
                          hypothesis="Nuclei are large relative to the detected peaks.",
                          params=ToolParams(min_distance=md + 6, sigma=2.0, landscape="distance", target="suspicious")),
            ] if oversplit else [
                Candidate(name="Sweep all objects", tool="watershed_split",
                          hypothesis="Suspicious-region detection missed merges; apply the split to every object.",
                          params=ToolParams(min_distance=max(3, round(0.6 * radius)), sigma=1.0, landscape="distance",
                                            target="all")),
                Candidate(name="Thicker bridges", tool="erosion_split",
                          hypothesis="The bridges between nuclei are thicker than the first erosion radius.",
                          params=ToolParams(radius=max(3, round(radius / 2)), target="suspicious")),
            ])
            if cands:
                return experiment(cands, "No candidate passed; test the next most likely explanations.",
                                  ["Previous round over-split nuclei." if oversplit else "Previous round under-split."])
        return Decision(observations=obs, root_causes=causes, hypothesis="Merges could not be repaired with the "
                                                                         "allowed tools.",
                        action="abstain", rationale="No candidate passed independent verification.", confidence=0.6)

    def write_report(self, final_state: dict) -> Report:
        best = final_state.get("best_attempt")
        base = final_state["baseline"]
        n_tried = len(final_state.get("attempts", []))
        n_rounds = len(final_state.get("rounds", []))
        if not best and final_state["status"] == "no_issue_found":
            return Report(summary="No oversized or concave objects were found; the baseline mask was left unchanged.",
                          uncertainties=["Merges between very small nuclei may fall below the detection thresholds."],
                          recommendation="Confirm by spot-checking the overlay.")
        if not best:
            return Report(summary=f"{n_tried} candidate repairs over {n_rounds} rounds; none passed independent "
                                  "verification, so the case is flagged for manual review.",
                          uncertainties=["The failure may need a tool outside the current allowlist."],
                          recommendation="Inspect the flagged regions manually.")
        bm, am = base.get("metrics"), best.get("metrics")
        improvements, changed = [], [f"Tournament winner: {best['tool']} with {best['params']} "
                                     f"(attempt {best['attempt']} of {n_tried}, {n_rounds} rounds)."]
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
                      recommendation="Review the before/after overlay and the suspect lineup, then approve or reject.")
