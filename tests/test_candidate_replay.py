"""Persistence checks use real engine/order lifecycle with deterministic forecasts."""

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from frontier import candidate_replay as replay
from frontier.cli import app


@pytest.fixture
def rehearsal(monkeypatch):
    n, m = 25, 3
    sessions = pd.bdate_range("2025-01-02", periods=n).strftime("%Y-%m-%d").tolist()
    close = np.tile(np.arange(n)[:, None] * 0.15 + 20, (1, m))
    market = dict(
        sessions=sessions,
        symbols=["A", "B", "C"],
        close=close,
        adjusted=close.copy(),
        atr=np.ones((n, m)),
        settlement_index=np.arange(n) + 2,
        dates=np.array(sessions, dtype="datetime64[D]"),
        benchmark_symbol="SPY",
    )
    metadata = dict(
        account={"nav": 2000},
        policy={"strategy": "calibrated_ensemble", "horizon": 3},
        data_id="data",
        account_id="account",
        policy_id="policy",
        signal_session=sessions[0],
    )
    prepared = dict(
        market=market,
        metadata=metadata,
        manifest={"payload_sha256": "model"},
        start=0,
        end=n - 1,
        ranking=np.tile(np.arange(m), (n, 1)),
        counts=np.full(n, m),
        known=np.ones(n, bool),
        forecasts={i: {"session": sessions[i], "rankings": []} for i in range(n)},
    )
    monkeypatch.setattr(replay, "_prepare_replay", lambda *a: prepared)
    return prepared


def test_durable_restart_matches_one_shot_with_real_orders(tmp_path, rehearsal):
    whole = replay.replay_candidate(tmp_path, "a" * 32, chunk_sessions=100)
    partial = replay.replay_candidate(tmp_path, "a" * 32, chunk_sessions=2, max_chunks=1)
    assert partial["status"] == "paused"
    assert partial["state"]["held"]
    resumed = replay.replay_candidate(
        tmp_path, "a" * 32, replay_id=partial["replay_id"], chunk_sessions=3
    )
    assert resumed["status"] == "complete"
    assert resumed["trades"] > 0
    assert resumed["state"] == whole["state"]
    assert resumed["curves"] == whole["curves"]
    assert resumed["trade_records"] == whole["trade_records"]
    assert resumed["activity"] == whole["activity"]
    assert resumed["fees"] == pytest.approx(whole["fees"], abs=1e-12)
    again = replay.replay_candidate(tmp_path, "a" * 32, replay_id=partial["replay_id"])
    assert again == resumed
    assert not (tmp_path / "operator.sqlite").exists()


def test_failure_after_chunk_commit_recovers_last_committed_state(tmp_path, rehearsal, monkeypatch):
    partial = replay.replay_candidate(tmp_path, "a" * 32, chunk_sessions=2, max_chunks=1)
    root = tmp_path / "artifacts/candidate-replays" / partial["replay_id"]
    original = replay._commit_chunk

    def fail(connection, first, last, previous, chunk):
        # Failure after commit preserves the chunk even when the report is stale.
        with connection:
            original(connection, first, last, previous, chunk)
        raise OSError("simulated process failure after durable commit")

    monkeypatch.setattr(replay, "_commit_chunk", fail)
    with pytest.raises(OSError):
        replay.replay_candidate(tmp_path, "a" * 32, replay_id=root.name, chunk_sessions=2)
    monkeypatch.setattr(replay, "_commit_chunk", original)
    recovered = replay.replay_candidate(tmp_path, "a" * 32, replay_id=root.name, chunk_sessions=2)
    whole = replay.replay_candidate(tmp_path, "a" * 32, chunk_sessions=100)
    assert recovered["curves"] == whole["curves"]
    assert recovered["trade_records"] == whole["trade_records"]
    with sqlite3.connect(root / "journal.sqlite") as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM attempts WHERE status='failed'").fetchone()[0]
            == 1
        )


def test_resume_changed_identity_rejected(tmp_path, rehearsal):
    partial = replay.replay_candidate(tmp_path, "a" * 32, max_chunks=1, chunk_sessions=1)
    with pytest.raises(ValueError, match="identity changed"):
        replay.replay_candidate(tmp_path, "b" * 32, replay_id=partial["replay_id"])
    with pytest.raises(ValueError, match="identity changed"):
        replay.replay_candidate(
            tmp_path, "a" * 32, replay_id=partial["replay_id"], round_trip_bps=80
        )


@pytest.mark.parametrize("package", ["pandas", "exchange-calendars"])
def test_resume_changed_runtime_rejected(tmp_path, rehearsal, monkeypatch, package):
    partial = replay.replay_candidate(tmp_path, "a" * 32, max_chunks=1, chunk_sessions=1)
    original = replay.version
    monkeypatch.setattr(
        replay, "version", lambda name: "changed" if name == package else original(name)
    )
    with pytest.raises(ValueError, match="identity changed"):
        replay.replay_candidate(tmp_path, "a" * 32, replay_id=partial["replay_id"])
    journal = tmp_path / "artifacts/candidate-replays" / partial["replay_id"] / "journal.sqlite"
    with sqlite3.connect(journal) as connection:
        assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM attempts WHERE status='failed'").fetchone()[0]
            == 1
        )


def test_resume_changed_settlements_rejected(tmp_path, rehearsal):
    partial = replay.replay_candidate(tmp_path, "a" * 32, max_chunks=1, chunk_sessions=1)
    rehearsal["market"]["settlement_index"][1] += 1
    with pytest.raises(ValueError, match="identity changed"):
        replay.replay_candidate(tmp_path, "a" * 32, replay_id=partial["replay_id"])
    journal = tmp_path / "artifacts/candidate-replays" / partial["replay_id"] / "journal.sqlite"
    with sqlite3.connect(journal) as connection:
        assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1


def test_actual_sqlite_writer_lock_excludes_second_connection(tmp_path):
    with replay._writer_lock(tmp_path):
        with pytest.raises(RuntimeError, match="active writer"):
            with replay._writer_lock(tmp_path):
                pytest.fail("two simultaneous writers")
    with replay._writer_lock(tmp_path):
        pass


def test_duplicate_out_of_order_and_tampered_journal_rejected(tmp_path):
    connection = replay._connect(tmp_path)
    first = {"simulation": {"state": {"next_session_index": 2}}}
    replay._commit_chunk(connection, 0, 1, None, first)
    with pytest.raises(ValueError, match="out-of-order"):
        replay._commit_chunk(connection, 0, 1, None, first)
    with pytest.raises(ValueError, match="out-of-order"):
        replay._commit_chunk(
            connection,
            3,
            3,
            first["simulation"]["state"],
            {"simulation": {"state": {"next_session_index": 4}}},
        )
    connection.execute("UPDATE chunks SET payload='{}'")
    connection.commit()
    with pytest.raises(ValueError, match="integrity"):
        replay._read_chunks(connection, 0)
    connection.close()


def test_training_targets_at_signal_rejected_before_any_source_access():
    metadata = dict(
        signal_session="2025-01-02",
        fit_sample={"latest_target_session": "2025-01-02", "exclusive_boundary": "2025-01-03"},
    )
    with pytest.raises(ValueError, match="precede first replay signal"):
        replay._validate_metadata(metadata)


def test_saved_code_change_rejected():
    metadata = dict(
        signal_session="2025-01-02", implementation_sha256={"candidate_replay.py": "bad"}
    )
    for key in ("fit_sample", "calibration_sample"):
        metadata[key] = {"latest_target_session": "2024-12-30", "exclusive_boundary": "2025-01-01"}
    with pytest.raises(ValueError, match="code compatibility"):
        replay._validate_metadata(metadata)


@pytest.mark.parametrize("identifier", ["../outside", "/absolute", "z" * 32, "a" * 31])
def test_artifact_path_rejected(tmp_path, identifier):
    with pytest.raises(ValueError, match="Artifact id"):
        replay._artifact(tmp_path, identifier)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"round_trip_bps": float("nan")},
        {"cost_profile": "invalid"},
        {"chunk_sessions": 0},
        {"max_chunks": 0},
    ],
)
def test_failed_request_arguments_retained(tmp_path, kwargs):
    with pytest.raises(ValueError):
        replay.replay_candidate(tmp_path, "a" * 32, **kwargs)
    journals = list(tmp_path.glob("artifacts/candidate-replays/*/journal.sqlite"))
    assert len(journals) == 1
    with sqlite3.connect(journals[0]) as connection:
        status, request_json = connection.execute("SELECT status,request FROM attempts").fetchone()
    assert status == "failed"
    request = json.loads(request_json)
    assert request["candidate_id"] == "a" * 32
    assert request["workspace"] == str(tmp_path.resolve())
    for key, value in kwargs.items():
        assert request[key] == ("nan" if isinstance(value, float) and np.isnan(value) else value)
    assert set(request) == {
        "workspace",
        "candidate_id",
        "end_session",
        "cost_profile",
        "round_trip_bps",
        "chunk_sessions",
        "max_chunks",
        "replay_id",
    }


def test_preparation_normalizes_once_preserving_original_warmup(tmp_path, monkeypatch):
    sessions = ["2025-01-02", "2025-01-03", "2025-01-06"]
    evidence = dict(
        run_id="c" * 32,
        signal_session=sessions[1],
        window_start=sessions[0],
        normalization=[{"symbol": "A", "raw_hash": "frozen"}],
    )
    metadata = dict(
        data=evidence,
        signal_session=sessions[1],
        account={"nav": 2000},
        policy={"strategy": "calibrated_ensemble", "horizon": 1},
        feature_names=["causal"],
    )
    monkeypatch.setattr(replay, "load_heads", lambda path: (object(), {"metadata": metadata}))
    monkeypatch.setattr(replay, "_validate_metadata", lambda value: None)
    calls = []
    frame = pd.DataFrame({"session": sessions})
    universe = [{"symbol": "A", "asset_type": "stock"}]

    def load(workspace, source, end, *, window_start):
        calls.append((source, end, window_start))
        return frame, universe, "current", {**evidence, "signal_session": sessions[2]}

    monkeypatch.setattr(replay, "load_saved_history", load)
    monkeypatch.setattr(replay, "_prepare", lambda *a: (None, {"A": universe[0]}, "current", None))
    market = dict(
        sessions=sessions, symbols=["A"], turnover=np.ones((3, 1)), dollar_volume=np.ones((3, 1))
    )

    def build(actual, *args, **kwargs):
        assert actual is frame
        return market

    monkeypatch.setattr(replay, "_build_market", build)
    monkeypatch.setattr(
        replay,
        "build_features",
        lambda *a, **kw: dict(
            feature_names=["causal"],
            X=np.ones((3, 1, 1)),
            eligible=np.ones((3, 1), bool),
            benchmark_known=np.ones(3, bool),
        ),
    )
    monkeypatch.setattr(replay, "build_settlement_indices", lambda *a: np.arange(3) + 1)
    monkeypatch.setattr(
        replay,
        "predict_heads",
        lambda *a: {"calibrated_ensemble": np.array([[0.02, 0.02, 0.02, 0.001, 0.001, 0.001]])},
    )
    prepared = replay._prepare_replay(
        tmp_path, "a" * 32, sessions[2], replay.get_cost_profile("proportional")
    )
    assert calls == [("c" * 32, sessions[2], sessions[0])]
    assert prepared["start"] == 1
    assert prepared["end"] == 2
    assert prepared["counts"].tolist() == [0, 1, 1]


@pytest.mark.parametrize("cli_first", [False, True])
@pytest.mark.parametrize("profile", ["proportional", "wealthsimple_usd", "moomoo_ca_us"])
def test_resume_between_api_and_cli_preserves_orders(tmp_path, rehearsal, cli_first, profile):
    runner = CliRunner()
    args = ["--workspace", str(tmp_path), "candidate-replay", "a" * 32, "--cost-profile", profile]
    if cli_first:
        result = runner.invoke(app, args + ["--chunk-sessions", "2", "--max-chunks", "1"])
        assert result.exit_code == 0, result.exception
        partial = json.loads(result.stdout)
    else:
        partial = replay.replay_candidate(
            tmp_path, "a" * 32, cost_profile=profile, chunk_sessions=2, max_chunks=1
        )
    assert partial["status"] == "paused"
    if cli_first:
        resumed = replay.replay_candidate(
            tmp_path, "a" * 32, cost_profile=profile, replay_id=partial["replay_id"]
        )
    else:
        result = runner.invoke(app, args + ["--replay-id", partial["replay_id"]])
        assert result.exit_code == 0, result.exception
        resumed = json.loads(
            (
                tmp_path / "artifacts/candidate-replays" / partial["replay_id"] / "report.json"
            ).read_text(encoding="utf-8")
        )
    whole = replay.replay_candidate(tmp_path, "a" * 32, cost_profile=profile, chunk_sessions=100)
    assert resumed["status"] == "complete"
    assert resumed["trades"] > 0
    assert resumed["state"] == whole["state"]
    assert resumed["curves"] == whole["curves"]
    assert resumed["trade_records"] == whole["trade_records"]
    assert resumed["fees"] == pytest.approx(whole["fees"], abs=1e-12)
