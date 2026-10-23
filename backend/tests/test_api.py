"""End-to-end: create a case from a sample, run the offline agent, review it."""
import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("MONGODB_URI", "")
    import config

    config.get_settings.cache_clear()
    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    return TestClient(main.app)


def test_full_investigation(client):
    assert client.get("/api/health").json()["storage"] == "local-json"
    samples = {s["id"] for s in client.get("/api/samples").json()}
    assert "merged_nuclei_demo" in samples

    case = client.post("/api/cases/sample/merged_nuclei_demo").json()  # background task runs inline
    detail = client.get(f"/api/cases/{case['_id']}").json()
    c = detail["case"]
    assert c["status"] == "awaiting_review", [s["title"] for s in detail["steps"]]
    assert c["best_attempt"]["verified"]
    assert c["best_attempt"]["metrics"]["f1"] > c["baseline_metrics"]["f1"]
    kinds = [s["kind"] for s in detail["steps"]]
    assert kinds[0] == "inspect" and "decision" in kinds and "verify" in kinds and kinds[-1] == "report"
    assert client.get(c["best_attempt"]["overlay_url"]).status_code == 200

    r = client.post(f"/api/cases/{c['_id']}/review", json={"decision": "approve", "reviewer": "Dr Test"})
    assert r.status_code == 200
    assert client.get(f"/api/cases/{c['_id']}").json()["case"]["status"] == "approved"
    assert client.get("/api/search", params={"q": "merged nuclei"}).json()["results"]


def test_control_case_is_not_repaired(client):
    case = client.post("/api/cases/sample/clean_control").json()
    c = client.get(f"/api/cases/{case['_id']}").json()["case"]
    assert c["status"] == "no_issue_found"
    assert c["attempt_count"] == 0
    r = client.post(f"/api/cases/{c['_id']}/review", json={"decision": "approve", "reviewer": "x"})
    assert r.status_code == 409


def test_rerun_replaces_previous_investigation(client):
    case = client.post("/api/cases/sample/merged_nuclei_demo").json()
    first = client.get(f"/api/cases/{case['_id']}").json()
    assert client.post(f"/api/cases/{case['_id']}/investigate").status_code == 200
    second = client.get(f"/api/cases/{case['_id']}").json()
    attempts = [r["attempt"] for r in second["runs"]]
    assert len(attempts) == len(set(attempts)) == len(first["runs"])
    assert len(second["steps"]) == len(first["steps"])
    assert {a["role"] for a in second["assets"] if a["source"] == "upload"} >= {"image", "baseline_mask"}


def test_second_rerun_while_running_is_refused(client, monkeypatch):
    import main

    case = client.post("/api/cases/sample/merged_nuclei_demo", params={"start": False}).json()
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda *a, **k: None)  # keep the run "in flight"
    assert client.post(f"/api/cases/{case['_id']}/investigate").status_code == 200
    assert client.post(f"/api/cases/{case['_id']}/investigate").status_code == 409


def test_tournament_diagnosis_suspects_and_report(client):
    case = client.post("/api/cases/sample/merged_nuclei_demo").json()
    detail = client.get(f"/api/cases/{case['_id']}").json()
    c = detail["case"]
    assert c["root_causes"] and c["root_causes"][0]["evidence"]
    first = c["rounds"][0]
    assert len(first["entries"]) >= 2  # competing candidates, ranked
    assert first["winner"] == first["entries"][0]["attempt"]
    assert {r["round"] for r in detail["runs"] if r["attempt"] > 0} == {r["round"] for r in c["rounds"]}
    assert c["suspects"] and all(s["verdict"] for s in c["suspects"])
    assert any(s["outcome"] == "good" for s in c["suspects"])
    assert client.get(c["assets"]["diff_overlay"]).status_code == 200
    md = client.get(f"/api/cases/{c['_id']}/report.md")
    assert md.status_code == 200
    assert "## Hypothesis tournament" in md.text and "## Suspect lineup" in md.text
