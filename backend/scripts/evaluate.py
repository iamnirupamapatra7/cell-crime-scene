"""Run the full investigation loop over the held-out set and report baseline vs repaired metrics.

    python backend/scripts/evaluate.py            # offline heuristic planner
    python backend/scripts/evaluate.py --gemini   # use GEMINI_API_KEY from .env
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.heuristic_planner import HeuristicPlanner  # noqa: E402
from agents.investigator import make_planner, run_investigation  # noqa: E402
from config import ROOT, get_settings  # noqa: E402
from services.atlas import LocalRepository, new_id  # noqa: E402
from tools.io import sha256  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini", action="store_true")
    ap.add_argument("--dir", type=Path, default=ROOT / "datasets" / "heldout")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    settings = get_settings().model_copy(update={"storage_dir": tmp})
    repo = LocalRepository(tmp / "db")
    planner = make_planner(settings) if args.gemini else HeuristicPlanner()
    rows = []
    for d in sorted(p for p in args.dir.iterdir() if (p / "meta.json").exists()):
        case_id = new_id()
        inputs = tmp / "cases" / case_id / "inputs"
        inputs.mkdir(parents=True)
        for role, name in (("image", "image.png"), ("baseline_mask", "baseline_mask.tif"),
                           ("reference_mask", "reference_mask.tif")):
            shutil.copyfile(d / name, inputs / name)
            repo.insert("assets", {"case_id": case_id, "role": role, "path": f"inputs/{name}", "url": "",
                                   "sha256": sha256(inputs / name), "version": 1, "source": "upload"})
        repo.insert("cases", {"_id": case_id, "title": d.name, "status": "created", "tags": []})
        run_investigation(case_id, repo, settings, planner)
        c = repo.get("cases", case_id)
        b = c["baseline_metrics"]
        a = (c.get("best_attempt") or {}).get("metrics") or b
        rows.append({"case": d.name, "status": c["status"], "attempts": c["attempt_count"],
                     "f1_before": round(b["f1"], 3), "f1_after": round(a["f1"], 3),
                     "count_err_before": b["count_error"], "count_err_after": a["count_error"],
                     "fg_iou_before": round(b["foreground_iou"], 3), "fg_iou_after": round(a["foreground_iou"], 3)})
        print(json.dumps(rows[-1]))
    n = len(rows)
    print(f"\n{n} held-out cases, planner={planner.name}")
    print(f"verified repairs: {sum(r['status'] == 'awaiting_review' for r in rows)}/{n}")
    for k in ("f1", "fg_iou"):
        print(f"mean {k}: {sum(r[k + '_before'] for r in rows) / n:.3f} -> {sum(r[k + '_after'] for r in rows) / n:.3f}")
    print(f"mean |count error|: {sum(abs(r['count_err_before']) for r in rows) / n:.1f} -> "
          f"{sum(abs(r['count_err_after']) for r in rows) / n:.1f}")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
