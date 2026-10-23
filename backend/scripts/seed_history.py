"""Build the agent's investigation memory by running every sample case through the full loop.

Cases go to the configured store (Atlas when MONGODB_URI is set), so later investigations can retrieve
similar past cases with hybrid search. Uses the offline heuristic planner unless --gemini is given;
every step is labelled with the planner that made it.

    python backend/scripts/seed_history.py
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.heuristic_planner import HeuristicPlanner  # noqa: E402
from agents.investigator import make_planner, run_investigation  # noqa: E402
from main import _create_case, repo, settings  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini", action="store_true")
    args = ap.parse_args()
    planner = make_planner(settings) if args.gemini else HeuristicPlanner()

    for d in sorted(settings.sample_dir.glob("*/meta.json")):
        meta = json.loads(d.read_text())
        files = {"image": d.parent / "image.png", "baseline_mask": d.parent / "baseline_mask.tif"}
        if (d.parent / "reference_mask.tif").exists():
            files["reference_mask"] = d.parent / "reference_mask.tif"
        case = _create_case(meta["title"], meta.get("researcher", ""), meta.get("notes", ""), files, d.parent.name)
        run_investigation(case["_id"], repo, settings, planner)
        c = repo.get("cases", case["_id"])
        print(f"{d.parent.name:22} {c['status']:16} tags={', '.join(c.get('tags', []))}")
    print(f"\nstored in {repo.backend}")


if __name__ == "__main__":
    main()
