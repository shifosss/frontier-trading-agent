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
    first = lab.run_historical_lab(workspace, study_mode="legacy")
    second = lab.run_historical_lab(workspace, study_mode="legacy")
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
    result = lab.run_historical_lab(workspace, capture_only=True, study_mode="legacy")
    assert result["captured"] == 2
    assert lab.historical_status(workspace)["latest"] is None


def test_source_change_blocks_publication_and_keeps_cache(inputs, monkeypatch):
    workspace, _ = inputs
    identities = iter(["original", "changed"])
    monkeypatch.setattr(lab, "_identity", lambda: next(identities))
    with pytest.raises(RuntimeError, match="source changed"):
        lab.run_historical_lab(workspace, study_mode="legacy")
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
        assert calls[0][0][-2:] == ["--study-mode", "short_horizon"]
        assert (
            client.post("/api/historical-lab/start", json={"study_mode": "unknown"}).status_code
            == 422
        )
        assert (
            client.post("/api/historical-lab/start", json={"source_run_id": "../"}).status_code
            == 422
        )


def test_loaded_orchestrator_change_requires_fresh_worker(inputs, monkeypatch):
    workspace, _ = inputs
    monkeypatch.setitem(lab._LOADED_CAPTURE_IDENTITIES, "historical_lab.py", "old-loaded-code")
    monkeypatch.setattr(
        historical_study, "evaluate_historical", lambda *a, **k: pytest.fail("evaluate")
    )
    with pytest.raises(RuntimeError, match="capture code changed"):
        lab.run_historical_lab(workspace, study_mode="legacy")
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


def test_saved_source_replay_keeps_cutoff_membership_and_avoids_capture(inputs, monkeypatch):
    workspace, calls = inputs
    original = lab.run_historical_lab(workspace, study_mode="legacy")
    source_id = original["run_id"]
    source_root = workspace / "artifacts/historical-lab/runs" / source_id
    retained = (source_root / "summary.json").read_bytes()
    monkeypatch.setattr(lab, "_now", lambda: "2027-01-20T22:00:00Z")
    monkeypatch.setattr(lab, "capture_histories", lambda *a, **k: pytest.fail("capture"))
    monkeypatch.setattr(research_universe, "load_snapshot", lambda *a: pytest.fail("discover"))
    replay = lab.run_historical_lab(workspace, study_mode="legacy", source_run_id=source_id)
    assert len(calls) == 1
    assert replay["definition"]["frozen_at"] == original["definition"]["frozen_at"]
    assert replay["definition"]["instruments"] == original["definition"]["instruments"]
    assert replay["definition"]["source_reuse"]["run_id"] == source_id
    assert replay["capture"]["rows"] == original["capture"]["rows"]
    assert (source_root / "summary.json").read_bytes() == retained
    assert lab.historical_status(workspace)["attempted"] == 0


def test_source_replay_rejects_conflicting_membership_or_rediscovery(inputs):
    workspace, _ = inputs
    original = lab.run_historical_lab(workspace, study_mode="legacy")
    source_id = original["run_id"]
    with pytest.raises(ValueError, match="cannot rediscover"):
        lab.start_historical_job(workspace, rediscover=True, source_run_id=source_id)
    path = workspace / "artifacts/historical-lab/runs" / source_id / "capture-index.json"
    records = lab._read(path)
    records[0]["spec"]["currency"] = "changed"
    lab._save(path, records)
    with pytest.raises(ValueError, match="membership"):
        lab.run_historical_lab(workspace, source_run_id=source_id, study_mode="legacy")
    assert lab.historical_status(workspace)["latest"]["run_id"] == source_id


def test_compact_result_omits_large_audits_but_keeps_trade_statistics():
    row = {
        "trade_records": [{"net_pnl": 2}],
        "period_returns": {"weekly": [0.02]},
        "trade_metrics": {"net_expectancy": 2, "completed_trades": 1},
        "weekly": {"positive_fraction": 1},
        "audit_retained": True,
    }
    assert lab.compact_result(row) == {
        key: value for key, value in row.items() if key not in {"trade_records", "period_returns"}
    }


def test_saved_source_replay_rejects_removed_history(inputs):
    workspace, _ = inputs
    result = lab.run_historical_lab(workspace, study_mode="legacy")
    path = workspace / "artifacts/historical-lab/runs" / result["run_id"] / "capture-index.json"
    lab._save(path, lab._read(path)[1:])
    with pytest.raises(ValueError, match="capture count"):
        lab._reuse_source_run(workspace, result["run_id"])


def test_new_study_mode_routes_to_daily_engine(inputs, monkeypatch):
    from frontier import short_horizon_study

    workspace, _ = inputs
    seen = []

    def evaluate(frame, specs, **kwargs):
        seen.append(specs[0]["currency"])
        result = historical_study.evaluate_historical(frame, specs, **kwargs)
        result["methodology"]["version"] = "short-test"
        return result

    monkeypatch.setattr(short_horizon_study, "evaluate_short_horizon", evaluate)
    result = lab.run_historical_lab(workspace)
    assert seen == ["USD", "CAD"]
    assert result["definition"]["study_mode"] == "short_horizon"
    assert result["definition"]["capture_index_sha256"]
    assert result["methodology"]["version"] == "short-test"
