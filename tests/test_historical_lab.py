"""The real orchestration merges both books and never publishes a changed experiment."""

import hashlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from frontier import historical_lab as lab
from frontier import historical_study, research_universe
from frontier.web import create_app


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    universe = [
        {"symbol": "SPY", "currency": "USD", "calendar": "XNYS", "asset_type": "etf"},
        {"symbol": "XIU.TO", "currency": "CAD", "calendar": "XTSE", "asset_type": "etf"},
    ]
    monkeypatch.setattr(
        research_universe,
        "load_snapshot",
        lambda _: {"snapshot_id": "fixture", "instruments": universe},
    )
    monkeypatch.setattr(lab, "_now", lambda: "2026-09-18T19:00:00Z")
    monkeypatch.setattr(lab, "_identity", lambda: "fixed")
    calls = []

    def capture(workspace, specs, **kwargs):
        calls.append(specs)
        records = []
        for spec in specs:
            relative = f"data/scanner/raw/{spec['symbol']}.json"
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"{}")
            records.append(
                {
                    "symbol": spec["symbol"],
                    "path": relative,
                    "sha256": hashlib.sha256(b"{}").hexdigest(),
                    "captured_at": "2026-09-18T19:00:00Z",
                    "last_session": "2026-09-17",
                    "requested_start": kwargs["start"],
                }
            )
        return records

    monkeypatch.setattr(lab, "capture_histories", capture)
    monkeypatch.setattr(
        lab,
        "read_history",
        lambda workspace, record: pd.DataFrame(
            {"symbol": [record["symbol"]], "session": ["2026-09-17"]}
        ),
    )

    def evaluate(frame, specs, *, as_of, progress):
        currency = specs[0]["currency"]
        progress({"stage": "historical_features", "currency": currency})
        return {
            "methodology": {"attempts": []},
            "portfolios": [{"currency": currency}],
            "benchmarks": [{"currency": currency}],
            "walk_forward": [{"currency": currency}],
            "coverage": {"markets": [{"currency": currency}], "instruments": specs},
        }

    monkeypatch.setattr(historical_study, "evaluate_historical", evaluate)
    return tmp_path, calls


def test_resume_merges_all_currencies_and_preserves_paper(inputs):
    workspace, calls = inputs
    journal = workspace / "paper.sqlite"
    journal.write_bytes(b"original paper journal")
    first = lab.run_historical_lab(workspace)
    second = lab.run_historical_lab(workspace)
    assert len(calls) == 1
    for key in ("portfolios", "benchmarks", "walk_forward"):
        assert [row["currency"] for row in second[key]] == ["USD", "CAD"]
    assert len(second["coverage"]["instruments"]) == 2
    assert first["capture"]["rows"] == second["capture"]["rows"] == 2
    assert journal.read_bytes() == b"original paper journal"


def test_capture_only_does_not_publish_results(inputs, monkeypatch):
    workspace, _ = inputs
    monkeypatch.setattr(
        historical_study, "evaluate_historical", lambda *a, **k: pytest.fail("evaluate")
    )
    result = lab.run_historical_lab(workspace, capture_only=True)
    assert result["captured"] == 2
    assert lab.historical_status(workspace)["latest"] is None


def test_source_change_blocks_publication_and_keeps_cache(inputs, monkeypatch):
    workspace, _ = inputs
    identities = iter(["original", "changed"])
    monkeypatch.setattr(lab, "_identity", lambda: next(identities))
    with pytest.raises(RuntimeError, match="source changed"):
        lab.run_historical_lab(workspace)
    assert (workspace / "data/historical/history-index.json").exists()
    assert lab.historical_status(workspace)["latest"] is None


def test_historical_http_is_read_only_and_compact(tmp_path, monkeypatch):
    from frontier import processes

    calls = []
    monkeypatch.setattr(processes, "start_background", lambda *a: calls.append(a) or 123)
    run = "a" * 32
    report = {
        key: [{"currency": "CAD", "equity_curve": [1], "trade_batches": [2]}]
        for key in ("portfolios", "benchmarks", "walk_forward")
    }
    lab._save(tmp_path / "artifacts/historical-lab/runs" / run / "result.json", report)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/historical-lab/status").json()["status"] == "idle"
        assert not calls
        assert (
            client.post(
                "/api/historical-lab/start", json={}, headers={"origin": "https://external.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/historical-lab/runs/invalid").status_code == 404
        compact = client.get(f"/api/historical-lab/runs/{run}").json()
        assert "equity_curve" not in compact["portfolios"][0]
        assert client.get(f"/api/historical-lab/runs/{run}/download").json() == report
        assert client.post("/api/historical-lab/start", json={}).json()["pid"] == 123
        assert len(calls) == 1


def test_loaded_orchestrator_change_requires_fresh_worker(inputs, monkeypatch):
    workspace, _ = inputs
    monkeypatch.setitem(lab._LOADED_CAPTURE_IDENTITIES, "historical_lab.py", "old-loaded-code")
    monkeypatch.setattr(
        historical_study, "evaluate_historical", lambda *a, **k: pytest.fail("evaluate")
    )
    with pytest.raises(RuntimeError, match="capture code changed"):
        lab.run_historical_lab(workspace)
    assert (workspace / "data/historical/history-index.json").exists()
    assert lab.historical_status(workspace)["latest"] is None


def test_atomic_status_retries_transient_windows_reader_lock(tmp_path, monkeypatch):
    from pathlib import Path

    target = tmp_path / "status.json"
    lab._save(target, {"status": "previous"})
    original = Path.replace
    attempts = []

    def replace(source, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            assert lab._read(target) == {"status": "previous"}
            raise PermissionError("Windows reader holds destination")
        return original(source, destination)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(lab.time, "sleep", lambda _: None)
    lab._save(target, {"status": "completed"})
    assert len(attempts) == 3
    assert lab._read(target) == {"status": "completed"}
    assert not list(tmp_path.glob("*.tmp"))
