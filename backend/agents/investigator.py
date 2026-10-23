"""The investigation loop: inspect -> diagnose -> tournament of competing repairs -> verify -> decide -> report.

The planner (Gemini, or the heuristic fallback) only chooses among allowlisted tools; Python executes
them with clamped parameters and verifies every result independently. Every step is persisted.
"""
import io
import itertools
import traceback

from PIL import Image

from agents.heuristic_planner import HeuristicPlanner
from services.atlas import fingerprint, now, similar_cases
from tools import registry
from tools.inspect_image import analyze_mask, find_suspicious_regions, inspect_image
from tools.io import load_image, load_labels, save_labels, save_png, sha256
from tools.suspects import suspect_verdicts
from tools.render import diff_overlay, grayscale, overlay
from tools.verify_result import (ACCEPTANCE_POLICY, evaluate_candidate, instance_metrics, integrity_checks,
                                 mask_summary)


def make_planner(settings):
    if settings.gemini_api_key:
        from agents.gemini_planner import GeminiPlanner

        return GeminiPlanner(settings.gemini_api_key, settings.gemini_model, settings.gemini_thinking_level,
                             settings.gemini_timeout_s)
    return HeuristicPlanner()


def _png(array) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


def _tags(stats, suspicious, attempts, status):
    tags = []
    if suspicious:
        tags += ["merged nuclei", "under-segmentation"]
    if stats["snr"] < 8:
        tags.append("low contrast")
    if stats["noise_sigma"] > 0.04:
        tags.append("noisy")
    for a in attempts:
        tags.append(a["tool"].replace("_", " "))
        if a["tool"] == "watershed_split":
            tags.append("watershed")
    if status == "unresolved" and any(a["tool"] == "watershed_split" for a in attempts):
        tags.append("watershed failure")
    return sorted(set(tags))


class Investigation:
    def __init__(self, case_id, repo, settings, planner=None):
        self.case_id = case_id
        self.repo = repo
        self.settings = settings
        self.planner = planner or make_planner(settings)
        self.fallback = HeuristicPlanner()
        self.case_dir = settings.storage_dir / "cases" / case_id
        self._counter = itertools.count(1)

    # --- persistence helpers -------------------------------------------------------------
    def step(self, kind, actor, title, detail="", data=None):
        self.repo.insert("agent_steps", {"case_id": self.case_id, "index": next(self._counter), "kind": kind,
                                         "actor": actor, "title": title, "detail": detail, "data": data or {}})

    def url(self, rel):
        return f"/files/cases/{self.case_id}/{rel}"

    def save_asset(self, role, rel, array=None, labels=None, version=1):
        path = self.case_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if labels is not None:
            save_labels(path, labels)
        else:
            save_png(path, array)
        return self.repo.insert("assets", {"case_id": self.case_id, "role": role, "path": rel,
                                           "url": self.url(rel), "sha256": sha256(path), "version": version,
                                           "source": "derived"})

    # --- planner with per-step fallback --------------------------------------------------
    def decide(self, state, images):
        try:
            return self.planner.decide(state, images), self.planner.name
        except Exception as exc:
            if self.planner is self.fallback:
                raise
            self.step("error", self.planner.name, "Planner call failed; heuristic fallback used for this step",
                      f"{type(exc).__name__}: {exc}")
            return self.fallback.decide(state, images), self.fallback.name

    def report(self, final_state):
        try:
            return self.planner.write_report(final_state), self.planner.name
        except Exception as exc:
            if self.planner is self.fallback:
                raise
            self.step("error", self.planner.name, "Report generation failed; template report used", str(exc))
            return self.fallback.write_report(final_state), self.fallback.name

    def reset(self):
        """A re-run replaces the previous investigation; uploaded originals and their assets are kept."""
        for coll in ("agent_steps", "analysis_runs", "evidence"):
            self.repo.delete_many(coll, {"case_id": self.case_id})
        self.repo.delete_many("assets", {"case_id": self.case_id, "source": "derived"})

    # --- main loop -----------------------------------------------------------------------
    def run(self):
        repo = self.repo
        try:
            self.reset()
            repo.update("cases", self.case_id, {"status": "investigating", "started_at": now(),
                                                "planner": self.planner.name})
            self._run()
        except Exception as exc:
            self.step("error", "python", "Investigation crashed", traceback.format_exc())
            repo.update("cases", self.case_id, {"status": "failed", "error": str(exc), "finished_at": now()})

    def _run(self):
        repo, case_id = self.repo, self.case_id
        case = repo.get("cases", case_id)
        assets = {a["role"]: a for a in repo.find("assets", {"case_id": case_id}) if a["source"] == "upload"}
        image_path = self.case_dir / assets["image"]["path"]
        img = load_image(image_path)
        baseline = load_labels(self.case_dir / assets["baseline_mask"]["path"])
        ref = load_labels(self.case_dir / assets["reference_mask"]["path"]) if "reference_mask" in assets else None
        if baseline.shape != img.shape or (ref is not None and ref.shape != img.shape):
            raise ValueError("image and mask dimensions differ")

        # 1. Inspect ---------------------------------------------------------------------------------
        stats = inspect_image(img)
        typical_area = analyze_mask(baseline)["median_area"]
        suspicious = find_suspicious_regions(baseline, typical_area)
        base_summary = mask_summary(baseline, typical_area, suspicious)
        base_overlay = overlay(img, baseline, [r["bbox"] for r in suspicious])
        self.save_asset("original_display", "derived/original.png", grayscale(img))
        base_ov_asset = self.save_asset("baseline_overlay", "derived/baseline_overlay.png", base_overlay)
        if ref is not None:
            self.save_asset("reference_overlay", "derived/reference_overlay.png", overlay(img, ref))
        for r in suspicious[:20]:
            repo.insert("evidence", {"case_id": case_id, "kind": "suspicious_region", **r})
        self.step("inspect", "python", f"Baseline has {base_summary['object_count']} objects; "
                                       f"{len(suspicious)} look merged",
                  "Flagged by size relative to the typical nucleus and by outline concavity.",
                  {"image_stats": stats, "mask": base_summary, "suspicious": suspicious[:10]})

        base_metrics = instance_metrics(baseline, ref) if ref is not None else None
        repo.insert("analysis_runs", {"case_id": case_id, "attempt": 0, "tool": "baseline", "params": {},
                                      "mask_summary": base_summary, "metrics": base_metrics,
                                      "overlay_url": base_ov_asset["url"], "verdict": None})
        if base_metrics:
            self.step("verify", "python", f"Baseline vs reference: F1 {base_metrics['f1']:.3f}, "
                                          f"{base_metrics['merged_objects']} merged objects, "
                                          f"count error {base_metrics['count_error']:+d}", data=base_metrics)
        else:
            self.step("verify", "python", "No reference mask: results can only be proxy-checked",
                      "Any repair will be marked unverified and needs human judgement.")

        fp = fingerprint(stats, base_summary)
        repo.update("cases", case_id, {"fingerprint": fp})
        prior = similar_cases(repo, case | {"tags": _tags(stats, suspicious, [], ""), "fingerprint": fp})
        if prior:
            self.step("memory", "python", f"Retrieved {len(prior)} similar past investigations ({prior[0]['via']})",
                      "Ranked by matching failure tags and a similar image/mask fingerprint; "
                      "the tools that fixed them are passed to the planner.", data={"cases": prior})

        # 2. Agent loop: tournament rounds of competing hypotheses -----------------------------------
        attempts, rounds, best, best_labels, hypothesis, root_causes = [], [], None, None, None, []
        image_checksum = assets["image"]["sha256"]
        original_png = _png(grayscale(img, 1))
        current_overlay = _png(overlay(img, baseline, [r["bbox"] for r in suspicious], scale=1))
        accepted = False
        max_rounds, per_round = self.settings.max_rounds, self.settings.candidates_per_round
        n = 0

        for rnd in range(1, max_rounds + 1):
            state = {
                "case": {"title": case.get("title"), "notes": case.get("notes"), "has_reference": ref is not None},
                "image_stats": stats,
                "baseline": {"mask": base_summary, "metrics": base_metrics, "suspicious_regions": suspicious[:8]},
                "attempts": [{k: a.get(k) for k in ("attempt", "round", "candidate", "tool", "params", "base",
                                                     "mask_summary", "metrics", "verdict")} for a in attempts],
                "rounds": rounds,
                "best_attempt": best and best["attempt"],
                "hypothesis": hypothesis,
                "round": rnd,
                "remaining_rounds": max_rounds - rnd + 1,
                "candidates_per_round": per_round,
                "tools": registry.catalog(),
                "acceptance_policy": ACCEPTANCE_POLICY,
                "similar_past_cases": prior,
            }
            images = [("Microscopy image:", original_png),
                      ("Current best segmentation overlay (red boxes = suspicious):", current_overlay)]
            decision, actor = self.decide(state, images)
            hypothesis = decision.hypothesis
            if decision.root_causes and not root_causes:
                root_causes = [c.model_dump() for c in decision.root_causes]
                self.step("diagnosis", actor, f"Root-cause diagnosis: {root_causes[0]['cause']}",
                          "; ".join(f"{c['cause']} ({c['likelihood']})" for c in root_causes),
                          {"root_causes": root_causes})
            cands = decision.candidates[:per_round] if decision.action == "experiment" else []
            title = (f"Round {rnd}: {len(cands)} competing hypotheses" if cands
                     else f"{decision.action}: {decision.hypothesis}")
            self.step("decision", actor, title, decision.rationale, decision.model_dump())
            repo.insert("evidence", {"case_id": case_id, "kind": "hypothesis", "round": rnd, "actor": actor,
                                     "text": decision.hypothesis, "observations": decision.observations,
                                     "candidates": [c.model_dump() for c in cands],
                                     "confidence": decision.confidence})

            if decision.action == "accept":
                if best:
                    self.step("guardrail", "python", f"Accept confirmed: attempt {best['attempt']} "
                              + ("passed verification" if best["verified"] else "is the best unverified attempt"))
                    accepted = True
                    break
                self.step("guardrail", "python", "Accept refused: no attempt has passed independent verification")
                continue
            if decision.action == "abstain" or not cands:
                self.step("decision", "python", "Agent abstained", decision.rationale)
                break

            entries = []
            for cand in cands:
                n += 1
                raw = cand.params.model_dump(exclude_none=True)
                params, notes = registry.validate_params(cand.tool, raw)
                base_name = "best" if raw.get("base") == "best" and best_labels is not None else "baseline"
                base_labels = best_labels if base_name == "best" else baseline
                base_susp = find_suspicious_regions(base_labels, typical_area)
                if notes:
                    self.step("guardrail", "python", f"{cand.name}: parameters adjusted to allowed bounds",
                              "; ".join(notes))

                new_labels, tool_summary = registry.TOOLS[cand.tool]["fn"](
                    img, base_labels, **params, suspicious_labels=[r["label"] for r in base_susp])
                self.step("tool", "python", f"{cand.name}: ran {cand.tool} on {base_name} mask",
                          ", ".join(f"{k}={v}" for k, v in params.items()), {"params": params, **tool_summary})

                # 3. Independent verification -------------------------------------------------------
                new_susp = find_suspicious_regions(new_labels, typical_area)
                summary = mask_summary(new_labels, typical_area, new_susp)
                metrics = instance_metrics(new_labels, ref) if ref is not None else None
                integrity = integrity_checks(baseline, new_labels, sha256(image_path) == image_checksum, cand.tool)
                verdict = evaluate_candidate(base_metrics, metrics, integrity, len(suspicious), len(new_susp))
                mask_asset = self.save_asset("repaired_mask", f"derived/attempt_{n}_mask.tif", labels=new_labels,
                                             version=n + 1)
                ov = overlay(img, new_labels, [r["bbox"] for r in new_susp])
                ov_asset = self.save_asset("attempt_overlay", f"derived/attempt_{n}_overlay.png", ov, version=n + 1)
                run = repo.insert("analysis_runs", {
                    "case_id": case_id, "attempt": n, "round": rnd, "candidate": cand.name,
                    "hypothesis": cand.hypothesis, "tool": cand.tool, "params": params, "base": base_name,
                    "actor": actor, "tool_summary": tool_summary, "mask_summary": summary, "metrics": metrics,
                    "verdict": verdict, "overlay_url": ov_asset["url"], "mask_url": mask_asset["url"]})
                attempts.append(run)
                failed = [c["name"] for c in verdict["checks"] if not c["passed"]]
                if verdict["passed"]:
                    title = f"{cand.name} (attempt {n}) PASSED verification"
                elif verdict.get("unverified_improvement"):
                    title = f"{cand.name} (attempt {n}) improved proxy metrics (unverified: no reference)"
                else:
                    title = f"{cand.name} (attempt {n}) FAILED: {', '.join(failed)}"
                self.step("verify", "python", title, data=verdict | {"metrics": metrics})
                repo.insert("evidence", {"case_id": case_id, "kind": "verification", "attempt": n, "round": rnd,
                                         **verdict})

                candidate_ok = verdict["passed"] or verdict.get("unverified_improvement")
                better = best is None or (
                    metrics["f1"] > best["metrics"]["f1"] if metrics else
                    summary["suspicious_regions"] < best["mask_summary"]["suspicious_regions"])
                if candidate_ok and better:
                    best = {"attempt": n, "tool": cand.tool, "candidate": cand.name, "params": params,
                            "metrics": metrics, "mask_summary": summary, "overlay_url": ov_asset["url"],
                            "mask_url": mask_asset["url"], "verified": bool(verdict["passed"])}
                    best_labels = new_labels
                    current_overlay = _png(overlay(img, new_labels, [r["bbox"] for r in new_susp], scale=1))
                entries.append({"attempt": n, "candidate": cand.name, "hypothesis": cand.hypothesis,
                                "tool": cand.tool, "params": params, "base": base_name,
                                "passed": bool(verdict["passed"]),
                                "unverified_improvement": bool(verdict.get("unverified_improvement")),
                                "f1": metrics["f1"] if metrics else None,
                                "count_error": metrics["count_error"] if metrics else None,
                                "merged_objects": metrics["merged_objects"] if metrics else None,
                                "suspicious_after": summary["suspicious_regions"], "failed_checks": failed})

            # Leaderboard: passing candidates first, then by F1 (or fewest suspicious regions without a reference).
            entries.sort(key=lambda e: (not (e["passed"] or e["unverified_improvement"]),
                                        -(e["f1"] if e["f1"] is not None else -e["suspicious_after"])))
            winner = entries[0] if entries and (entries[0]["passed"] or entries[0]["unverified_improvement"]) else None
            rounds.append({"round": rnd, "entries": entries, "winner": winner and winner["attempt"]})
            if winner:
                score = f"F1 {winner['f1']:.3f}" if winner["f1"] is not None else \
                    f"{winner['suspicious_after']} suspicious regions left"
                self.step("tournament", "python", f"Round {rnd} leaderboard: {winner['candidate']} wins ({score})",
                          " > ".join(e["candidate"] for e in entries), {"round": rounds[-1]})
            else:
                self.step("tournament", "python", f"Round {rnd} leaderboard: no candidate passed",
                          " > ".join(e["candidate"] for e in entries), {"round": rounds[-1]})

        if best and not accepted:
            self.step("guardrail", "python", f"Round budget exhausted; best verified attempt {best['attempt']} "
                                             "selected for review")
        if best:
            status = "awaiting_review"
        elif not suspicious and not attempts:
            status = "no_issue_found"
            self.step("decision", "python", "No merged-nucleus evidence; mask left unchanged")
        else:
            status = "unresolved"
            self.step("decision", "python", "Unresolved: flagged for human investigation",
                      "No attempt passed independent verification.")

        # 4. Suspect lineup and change map ------------------------------------------------------------
        suspects = suspect_verdicts(baseline, best_labels, ref, suspicious)
        for s in suspects:
            repo.insert("evidence", {"case_id": case_id, "kind": "suspect", **s})
        diff_url = None
        if best_labels is not None:
            diff_url = self.save_asset("diff_overlay", "derived/diff.png", diff_overlay(img, baseline, best_labels))["url"]
        if suspects and ref is not None:
            solved = sum(s["outcome"] == "good" for s in suspects)
            self.step("verify", "python", f"Suspect lineup: {solved} of {len(suspects)} flagged regions resolved "
                                          "correctly", ", ".join(f"#{s['rank']} {s['verdict']}" for s in suspects),
                      {"suspects": suspects})

        # 5. Report -----------------------------------------------------------------------------------
        final_state = {"baseline": {"metrics": base_metrics, "mask": base_summary},
                       "root_causes": root_causes,
                       "attempts": [{k: a.get(k) for k in ("attempt", "round", "candidate", "tool", "params",
                                                            "metrics", "verdict")} for a in attempts],
                       "rounds": rounds, "suspects": suspects,
                       "best_attempt": best, "hypothesis": hypothesis, "status": status}
        report, actor = self.report(final_state)
        self.step("report", actor, "Investigation report written", report.summary)
        repo.update("cases", case_id, {
            "status": status, "finished_at": now(), "hypothesis": hypothesis, "best_attempt": best,
            "baseline_metrics": base_metrics, "baseline_summary": base_summary, "image_stats": stats,
            "attempt_count": len(attempts), "round_count": len(rounds), "rounds": rounds,
            "root_causes": root_causes, "suspects": suspects, "report": report.model_dump(),
            "tags": _tags(stats, suspicious, attempts, status),
            "assets": {"original": self.url("derived/original.png"), "baseline_overlay": base_ov_asset["url"],
                       "reference_overlay": self.url("derived/reference_overlay.png") if ref is not None else None,
                       "diff_overlay": diff_url},
        })

def run_investigation(case_id, repo, settings, planner=None):
    Investigation(case_id, repo, settings, planner).run()
