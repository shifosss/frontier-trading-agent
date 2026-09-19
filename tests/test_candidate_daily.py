import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from frontier import candidate_daily as candidate


def test_sample_audit_purges_all_horizons_and_retains_actual_identities():
    n = 40
    features = dict(
        eligible=np.ones((n, 120), bool),
        benchmark_known=np.ones(n, bool),
        labels=np.ones((n, 120, 6)),
        label_end=np.arange(n)[:, None] + np.array([2, 4, 6]),
    )
    sessions = [f"session-{i}" for i in range(n)]
    symbols = [f"stock-{i}" for i in range(120)]
    rows, cols, audit = candidate._sample_audit(features, sessions, symbols, 0, 19, 20, 1729)
    assert rows.max() == 13
    assert len(rows) == 14 * 96
    assert audit["purged_rows"] == 6 * 120
    assert audit["latest_target_session"] == "session-19"
    assert audit["exclusive_boundary"] == "session-20"
    assert audit["row_identities"] == [[sessions[r], symbols[c]] for r, c in zip(rows, cols)]
    assert candidate._sample_audit(features, sessions, symbols, 0, 19, 20, 1729)[2] == audit


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizon": 2},
        {"strategy": "winner"},
        {"budget": 0},
        {"budget": float("inf")},
        {"budget": float("-inf")},
        {"cost_bps": float("nan")},
        {"cost_bps": 20000},
    ],
)
def test_bad_requests_fail_before_source_load(tmp_path, kwargs):
    with pytest.raises(ValueError):
        candidate.build_candidate(tmp_path, "bad-id", **kwargs)
    paths = list(tmp_path.glob("artifacts/daily-candidates/*/attempt.json"))
    assert len(paths) == 1
    attempt = json.loads(paths[0].read_text())
    assert attempt["status"] == "failed"
    assert attempt["error_type"] == "ValueError"
    expected = dict(
        workspace=str(tmp_path.resolve()),
        capture_run_id="bad-id",
        signal_session=None,
        budget=2000,
        cost_bps=40,
        horizon=5,
        strategy="calibrated_ensemble",
    )
    expected.update(kwargs)
    expected = {
        k: str(v) if isinstance(v, float) and not np.isfinite(v) else v for k, v in expected.items()
    }
    assert attempt["request"] == expected
    json.dumps(attempt, allow_nan=False)


@pytest.fixture
def preview(monkeypatch):
    n, m = 1009, 4
    sessions = pd.bdate_range("2020-01-01", periods=n).strftime("%Y-%m-%d").tolist()
    symbols = ["A", "B", "C", "SPY"]
    universe = [dict(symbol=s, asset_type="etf" if s == "SPY" else "stock") for s in symbols]
    market = dict(
        sessions=sessions,
        symbols=symbols,
        close=np.full((n, m), 20.0),
        atr=np.full((n, m), 1.0),
        adjusted=np.full((n, m), 20.0),
        turnover=np.ones((n, m)),
        dollar_volume=np.ones((n, m)),
    )
    eligible = np.tile([True, True, True, False], (n, 1))
    features = dict(
        X=np.ones((n, m, 2)),
        labels=np.ones((n, m, 6)),
        eligible=eligible,
        benchmark_known=np.ones(n, bool),
        label_end=np.arange(n)[:, None] + [2, 4, 6],
        feature_names=["a", "b"],
        label_names=["return_1", "return_3", "return_5", "downside_1", "downside_3", "downside_5"],
    )
    monkeypatch.setattr(
        candidate,
        "load_saved_history",
        lambda *a: (
            pd.DataFrame(),
            universe,
            pd.Timestamp("2025-01-01", tz="UTC"),
            {"source_hashes": ["frozen"]},
        ),
    )
    monkeypatch.setattr(
        candidate, "_prepare", lambda f, u, c, b: (f, {r["symbol"]: r for r in u}, c, b)
    )
    monkeypatch.setattr(candidate, "_build_market", lambda *a, **k: market.copy())
    monkeypatch.setattr(candidate, "build_features", lambda *a, **k: features)
    bundle = SimpleNamespace(audit={"test_double": True})
    monkeypatch.setattr(candidate, "fit_heads", lambda *a, **k: bundle)

    def predictions(bundle, X):
        return {
            "calibrated_ensemble": np.tile([0.02, 0.02, 0.02, 0.001, 0.001, 0.001], (len(X), 1))
        }

    monkeypatch.setattr(candidate, "predict_heads", predictions)

    def save(bundle, path, metadata):
        path.mkdir()
        return {"payload_sha256": "stable-model", "metadata": metadata}

    monkeypatch.setattr(candidate, "save_heads", save)
    monkeypatch.setattr(candidate, "load_heads", lambda p: (bundle, {}))
    return features


def test_preview_identity_immutable_reports_complete_ranking_and_cutoffs(tmp_path, preview):
    first = candidate.build_candidate(tmp_path, "frozen")
    second = candidate.build_candidate(tmp_path, "frozen")
    assert first["intents"] == second["intents"]
    assert first["artifact_path"] != second["artifact_path"]
    assert first["prediction_reload_exact"] is True
    assert first["status"] == "unqualified"
    assert first["eligible_count"] == 3
    assert len(first["rankings"]) + len(first["rejections"]) == 4
    assert first["rejections"] == [{"symbol": "SPY", "reason": "not_stock"}]
    assert all(i["quantity"] == 5 for i in first["intents"])
    meta = first["metadata"]
    assert meta["fit_sample"]["latest_target_session"] < meta["calibration_start"]
    assert meta["calibration_sample"]["latest_target_session"] < meta["signal_session"]
    json.dumps(first, allow_nan=False)
    changed = candidate.build_candidate(tmp_path, "frozen", budget=1000)
    assert first["account_id"] != changed["account_id"]
    assert first["intents"][0]["intent_id"] != changed["intents"][0]["intent_id"]


def test_no_eligible_signal_is_valid_empty_preview(tmp_path, preview):
    preview["eligible"][-1] = False
    report = candidate.build_candidate(tmp_path, "frozen")
    assert report["intents"] == []
    assert report["rankings"] == []
    assert len(report["rejections"]) == 4


def test_prediction_reload_mismatch_fails(tmp_path, preview, monkeypatch):
    calls = []

    def predict(bundle, X):
        calls.append(1)
        return {"calibrated_ensemble": np.full((len(X), 6), len(calls))}

    monkeypatch.setattr(candidate, "predict_heads", predict)
    with pytest.raises(ValueError, match="predictions differ"):
        candidate.build_candidate(tmp_path, "frozen")
    attempts = list(tmp_path.glob("artifacts/daily-candidates/*/attempt.json"))
    assert len(attempts) == 1
    attempt = json.loads(attempts[0].read_text())
    assert attempt["status"] == "failed"
    assert attempt["error_type"] == "ValueError"
    assert "predictions differ" in attempt["error"]


@pytest.fixture
def captured(monkeypatch):
    spec = {"symbol": "A", "currency": "USD", "asset_type": "stock"}
    record = {"symbol": "A", "spec": spec, "sha256": "original-raw"}
    definition = {
        "frozen_at": "2026-09-18T23:00:00+00:00",
        "requested_start": "2000-01-01",
        "instruments": [spec],
        "source_reuse": {
            "run_id": "original",
            "definition_sha256": "definition",
            "capture_index_sha256": "index",
        },
    }
    evidence = {"definition_sha256": "definition", "capture_index_sha256": "index"}

    def reuse(workspace, run_id):
        definition_copy = definition.copy()
        if run_id == "original":
            definition_copy.pop("source_reuse")
        return (
            definition_copy,
            [record],
            [{"symbol": "TPX", "error": "unresolved"}],
            evidence.copy(),
        )

    monkeypatch.setattr(candidate, "_reuse_source_run", reuse)
    frame = pd.DataFrame(
        {"symbol": ["A"] * 3, "session": ["2000-01-03", "2026-09-17", "2026-09-18"]}
    )
    monkeypatch.setattr(candidate, "read_history", lambda *a: frame)
    return definition


def test_frozen_load_bounds_memory_and_follows_original_source(tmp_path, captured):
    frame, _, _, data = candidate.load_saved_history(tmp_path, "reused", "2026-09-17")
    assert frame.session.tolist() == ["2026-09-17"]
    assert data["source_hashes"] == [{"symbol": "A", "sha256": "original-raw"}]
    assert data["source_failures"][0]["symbol"] == "TPX"
    assert data["original_source"]["capture_index_sha256"] == "index"
    assert data["requested_usd_instruments"] == data["usable_usd_histories"] == 1


@pytest.mark.parametrize("session", ["2026-09-19", "2026-09-20", "2000-01-04"])
def test_frozen_load_rejects_future_non_session_and_insufficient_history(
    tmp_path, captured, session
):
    with pytest.raises(ValueError):
        candidate.load_saved_history(tmp_path, "reused", session)


def test_frozen_reuse_digest_mismatch_rejected(tmp_path, captured):
    captured["source_reuse"]["capture_index_sha256"] = "tampered"
    with pytest.raises(ValueError, match="identity changed"):
        candidate.load_saved_history(tmp_path, "reused")


def test_raw_hash_failure_is_not_silently_skipped(tmp_path, captured, monkeypatch):
    def corrupt(*args):
        raise ValueError("Historical source bytes changed")

    monkeypatch.setattr(candidate, "read_history", corrupt)
    with pytest.raises(ValueError, match="source bytes changed"):
        candidate.load_saved_history(tmp_path, "reused")
