"""Research resumes immutable inputs and never mutates the active paper journal."""

import hashlib
import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from frontier import forward_study, research_universe, strategy_study
from frontier import research_lab as lab
from frontier.web import create_app


@pytest.fixture
def lab_inputs(tmp_path, monkeypatch):
    universe = [
        {"symbol": "SPY", "currency": "USD", "calendar": "XNYS", "asset_type": "etf", "group": "us"}
    ]
    monkeypatch.setattr(
        research_universe,
        "load_snapshot",
        lambda workspace: {"snapshot_id": "fixture", "instruments": universe},
    )
    monkeypatch.setattr(lab, "_now", lambda: "2026-09-18T19:00:00+00:00")
    monkeypatch.setattr(lab, "_identity", lambda: "frozen-source")
    frame = pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "session": "2026-09-17",
                "available_at": pd.Timestamp("2026-09-17T20:01:00Z"),
                "close": 100.0,
                "adjusted_close": 100.0,
                "high": 101.0,
                "low": 99.0,
                "volume": 100000,
            }
        ]
    )
    monkeypatch.setattr(lab, "normalize_chart", lambda payload, spec, captured: frame.copy())
    calls = []

    def capture(workspace, batch):
        calls.append(batch)
        content = b'{"prices":"fixture"}'
        digest = hashlib.sha256(content).hexdigest()
        relative = f"data/scanner/raw/SPY.{digest}.json"
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        record = {
            "symbol": "SPY",
            "path": relative,
            "sha256": digest,
            "captured_at": "2026-09-18T19:00:00Z",
            "last_session": "2026-09-17",
            "rows": 1,
        }
        return {"captures": [record]}, False

    monkeypatch.setattr(lab, "capture_universe", capture)

    def evaluate(frame, universe, **kwargs):
        return {
            "attempts": [],
            "summaries": [],
            "cohorts": [],
            "latest_candidates": [],
            "as_of": kwargs["as_of"],
        }

    monkeypatch.setattr(strategy_study, "evaluate_strategies", evaluate)
    monkeypatch.setattr(
        forward_study,
        "record_forward_study",
        lambda *args: {"status": "recorded", "pending_count": 0},
    )
    return tmp_path, calls


def test_resume_reuses_verified_sources_and_preserves_paper(lab_inputs):
    workspace, calls = lab_inputs
    paper = workspace / "data/operator.sqlite"
    paper.parent.mkdir(parents=True)
    paper.write_bytes(b"existing paper journal")
    first = lab.run_research_lab(workspace)
    second = lab.run_research_lab(workspace)
    assert len(calls) == 1
    assert first["capture"]["usable"] == second["capture"]["usable"] == 1
    assert second["as_of"] == "2026-09-18T19:00:00+00:00"
    assert paper.read_bytes() == b"existing paper journal"
    assert lab.research_status(workspace)["status"] == "completed"
    assert lab.research_result(workspace, first["run_id"])["capture"]["rows"] == 1


def test_tampered_raw_cache_fails_without_overwriting_last_result(lab_inputs):
    workspace, _ = lab_inputs
    first = lab.run_research_lab(workspace)
    raw = next((workspace / "data/research/capture-workspace/data/scanner/raw").glob("*.json"))
    raw.write_bytes(b"changed prices")
    with pytest.raises(ValueError, match="source bytes changed"):
        lab.run_research_lab(workspace)
    status = lab.research_status(workspace)
    assert status["status"] == "failed"
    assert status["latest"]["run_id"] == first["run_id"]


def test_source_edit_during_capture_keeps_cache_but_blocks_publication(lab_inputs, monkeypatch):
    workspace, calls = lab_inputs
    identities = iter(["old-source", "new-source"])
    monkeypatch.setattr(lab, "_identity", lambda: next(identities))
    with pytest.raises(RuntimeError, match="changed during capture"):
        lab.run_research_lab(workspace)
    assert len(calls) == 1
    assert (workspace / "data/research/history-index.json").exists()
    assert lab.research_status(workspace)["latest"] is None


def test_worker_lock_not_reused_pid_controls_status_and_duplicate_start(tmp_path, monkeypatch):
    root = tmp_path / "data/research"
    root.mkdir(parents=True)
    lock = sqlite3.connect(root / "worker.lock.sqlite")
    lab._save(tmp_path / "artifacts/research-lab/status.json", {"status": "running", "pid": 1})
    assert lab.research_status(tmp_path)["status"] == "interrupted"
    lock.execute("BEGIN EXCLUSIVE")
    assert lab.research_status(tmp_path)["status"] == "running"
    from frontier import processes

    monkeypatch.setattr(processes, "start_background", lambda *args: pytest.fail("duplicate child"))
    assert lab.start_research_job(tmp_path)["status"] == "running"
    with pytest.raises(RuntimeError, match="already running"):
        lab.run_research_lab(tmp_path)
    lock.rollback()
    lock.close()


def test_lab_http_is_read_only_until_explicit_same_origin_start(tmp_path, monkeypatch):
    from frontier import processes

    calls = []
    monkeypatch.setattr(processes, "start_background", lambda *args: calls.append(args) or 123)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/research-lab/status").json()["status"] == "idle"
        assert not calls
        assert (
            client.post(
                "/api/research-lab/start", json={}, headers={"origin": "https://elsewhere.example"}
            ).status_code
            == 403
        )
        assert client.post("/api/research-lab/start", json={"max_symbols": 1}).status_code == 422
        assert client.post("/api/research-lab/start", json={}).json()["pid"] == 123
        assert len(calls) == 1
        assert client.get("/api/research-lab/runs/not-a-run").status_code == 404
        run_id = "a" * 32
        lab._save(
            tmp_path / "artifacts/research-lab/runs" / run_id / "result.json",
            {"summaries": [], "cohorts": [{"audit": True}]},
        )
        assert "cohorts" not in client.get(f"/api/research-lab/runs/{run_id}").json()
        assert client.get(f"/api/research-lab/runs/{run_id}/download").json()["cohorts"]
