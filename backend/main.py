"""Cell Crime Scene API."""
import json
import shutil
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.investigator import run_investigation
from config import get_settings
from services.atlas import make_repository, new_id, similar_cases
from tools.io import load_image, load_labels, sha256

settings = get_settings()
repo = make_repository(settings)
cases_dir = settings.storage_dir / "cases"
cases_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cell Crime Scene")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",  # dev server may move ports
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/files/cases", StaticFiles(directory=cases_dir), name="files")

ALLOWED_SUFFIXES = {".png", ".tif", ".tiff", ".jpg", ".jpeg"}


def _register_inputs(case_id: str, files: dict[str, Path]) -> None:
    """Copy inputs into the case folder (read-only originals), validate them and record checksums."""
    inputs = cases_dir / case_id / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    stored = {}
    for role, src in files.items():
        dest = inputs / f"{role}{src.suffix.lower()}"
        shutil.copyfile(src, dest)
        stored[role] = dest
    try:
        shape = load_image(stored["image"]).shape
        for role in ("baseline_mask", "reference_mask"):
            if role in stored and load_labels(stored[role]).shape != shape:
                raise ValueError(f"{role} is {load_labels(stored[role]).shape}, image is {shape}")
    except Exception as exc:
        shutil.rmtree(cases_dir / case_id, ignore_errors=True)
        raise HTTPException(400, f"Could not read inputs: {exc}")
    for role, path in stored.items():
        repo.insert("assets", {"case_id": case_id, "role": role, "path": f"inputs/{path.name}",
                               "url": f"/files/cases/{case_id}/inputs/{path.name}", "sha256": sha256(path),
                               "version": 1, "source": "upload"})


def _create_case(title, researcher, notes, files, sample_id=None):
    case_id = new_id()
    _register_inputs(case_id, files)
    return repo.insert("cases", {"_id": case_id, "title": title, "researcher": researcher, "notes": notes,
                                 "sample_id": sample_id, "has_reference": "reference_mask" in files,
                                 "status": "created", "tags": []})


@app.get("/api/health")
def health():
    return {"ok": True, "storage": repo.backend,
            "planner": "gemini" if settings.gemini_api_key else "heuristic (offline)",
            "model": settings.gemini_model if settings.gemini_api_key else None,
            "max_attempts": settings.max_attempts}


@app.get("/api/samples")
def list_samples():
    out = []
    for d in sorted(settings.sample_dir.glob("*/meta.json")):
        meta = json.loads(d.read_text())
        out.append(meta | {"id": d.parent.name, "preview": f"/api/samples/{d.parent.name}/image"})
    return out


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str):
    from fastapi.responses import FileResponse

    path = settings.sample_dir / Path(sample_id).name / "image.png"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.post("/api/cases/sample/{sample_id}")
def create_from_sample(sample_id: str, background: BackgroundTasks, start: bool = True):
    d = settings.sample_dir / Path(sample_id).name
    if not (d / "meta.json").exists():
        raise HTTPException(404, "unknown sample")
    meta = json.loads((d / "meta.json").read_text())
    files = {"image": d / "image.png", "baseline_mask": d / "baseline_mask.tif"}
    if (d / "reference_mask.tif").exists():
        files["reference_mask"] = d / "reference_mask.tif"
    case = _create_case(meta["title"], meta.get("researcher", ""), meta.get("notes", ""), files, sample_id)
    if start:
        background.add_task(run_investigation, case["_id"], repo, settings)
    return case


@app.post("/api/cases")
async def create_case(background: BackgroundTasks,
                      image: UploadFile = File(...), baseline_mask: UploadFile = File(...),
                      reference_mask: Optional[UploadFile] = File(None),
                      title: str = Form("Untitled investigation"), researcher: str = Form(""),
                      notes: str = Form(""), start: bool = Form(True)):
    tmp = settings.storage_dir / "uploads" / new_id()
    tmp.mkdir(parents=True, exist_ok=True)
    files = {}
    try:
        for role, upload in (("image", image), ("baseline_mask", baseline_mask), ("reference_mask", reference_mask)):
            if upload is None or not upload.filename:
                continue
            suffix = Path(upload.filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                raise HTTPException(400, f"{role}: unsupported file type {suffix}")
            dest = tmp / f"{role}{suffix}"
            dest.write_bytes(await upload.read())
            files[role] = dest
        case = _create_case(title, researcher, notes, files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if start:
        background.add_task(run_investigation, case["_id"], repo, settings)
    return case


@app.post("/api/cases/{case_id}/investigate")
def investigate(case_id: str, background: BackgroundTasks):
    case = repo.get("cases", case_id)
    if not case:
        raise HTTPException(404)
    if case["status"] == "investigating":
        raise HTTPException(409, "investigation already running")
    repo.update("cases", case_id, {"status": "investigating"})  # block a second click before the task starts
    background.add_task(run_investigation, case_id, repo, settings)
    return {"started": True}


@app.get("/api/cases")
def list_cases(limit: int = 50):
    return repo.find("cases", sort="created_at", descending=True, limit=limit)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    case = repo.get("cases", case_id)
    if not case:
        raise HTTPException(404)
    q = {"case_id": case_id}
    return {
        "case": case,
        "steps": repo.find("agent_steps", q, sort="index"),
        "runs": repo.find("analysis_runs", q, sort="attempt"),
        "evidence": repo.find("evidence", q),
        "reviews": repo.find("reviews", q),
        "assets": repo.find("assets", q),
        "similar": similar_cases(repo, case) if case.get("tags") else [],
    }


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str
    comment: str = ""


@app.post("/api/cases/{case_id}/review")
def review(case_id: str, body: ReviewIn):
    case = repo.get("cases", case_id)
    if not case:
        raise HTTPException(404)
    if body.decision == "approve" and case["status"] != "awaiting_review":
        raise HTTPException(409, "only a case awaiting review with a verified repair can be approved")
    if case["status"] not in ("awaiting_review", "unresolved", "no_issue_found"):
        raise HTTPException(409, f"case is {case['status']}")
    doc = repo.insert("reviews", {"case_id": case_id, **body.model_dump(),
                                  "attempt": (case.get("best_attempt") or {}).get("attempt")})
    status = "approved" if body.decision == "approve" else "rejected"
    repo.update("cases", case_id, {"status": status, "reviewed_by": body.reviewer})
    steps = repo.find("agent_steps", {"case_id": case_id})
    repo.insert("agent_steps", {"case_id": case_id, "index": len(steps) + 1, "kind": "review", "actor": "human",
                                "title": f"{body.reviewer} {status} the result", "detail": body.comment, "data": {}})
    return doc


@app.get("/api/search")
def search(q: str, limit: int = 20):
    results, mode = repo.search_cases(q, limit)
    return {"mode": mode, "results": results}
