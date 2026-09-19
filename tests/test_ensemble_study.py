import json
import runpy

import numpy as np
import pytest

from frontier import ensemble_study as study
from frontier.ensemble_models import MODEL_NAMES
from frontier.short_horizon_study import _diversified, _simulate_daily, _summarize


def test_sampling_is_purged_reproducible_and_not_selected_on_test_outcomes():
    n, m = 40, 200
    features = {
        "eligible": np.ones((n, m), dtype=bool),
        "benchmark_known": np.ones(n, dtype=bool),
        "labels": np.zeros((n, m, 6)),
        "label_end": np.arange(n)[:, None] + 1 + np.array([1, 3, 5]),
    }
    features["labels"][2, 0] = np.nan
    rows, columns, audit = study._sample_rows(features, 0, 19, 20, 1729)
    assert rows.max() == 13
    assert len(rows) == 14 * 96
    assert audit["purged_rows"] == 6 * m
    assert audit["excluded_label_rows"] == 1
    assert not np.any((rows == 2) & (columns == 0))
    features["labels"][20:] = 999
    again = study._sample_rows(features, 0, 19, 20, 1729)
    np.testing.assert_array_equal(rows, again[0])
    np.testing.assert_array_equal(columns, again[1])
    assert audit == again[2]


def test_custom_rankings_preserve_engine_and_missing_signal_invalidates():
    data = runpy.run_path("tests/test_short_horizon_study.py")["market"]()
    data["counts"]["momentum"][:] = 5
    ordinary = _simulate_daily(data, "momentum", 3, 2000, 40, 0, 19, audit=True)
    kwargs = {
        "signal_ranking": data["ranking"]["momentum"],
        "signal_counts": data["counts"]["momentum"],
    }
    custom = _simulate_daily(data, "ridge", 3, 2000, 40, 0, 19, audit=True, **kwargs)
    for key in ("equity", "cash", "settled_cash", "unsettled_cash"):
        np.testing.assert_array_equal(ordinary[key], custom[key])
    assert ordinary["trade_records"] == custom["trade_records"]
    known = np.ones(20, dtype=bool)
    known[0] = False
    failed = _simulate_daily(data, "ridge", 3, 2000, 40, 0, 19, signal_known=known, **kwargs)
    report = _summarize(failed, data["sessions"], 2000)
    assert report["status"] == "incomplete"
    assert report["total_return"] is None
    assert report["missing"] == [f"SPY:{data['sessions'][0]}:signal_input"]


def test_correlation_uses_only_past_and_rejects_unknown_pair_risk():
    rng = np.random.default_rng(4)
    one = rng.normal(0, 0.01, 120)
    independent = rng.normal(0, 0.01, 120)
    prices = 10 * np.cumprod(1 + np.column_stack((one, one, independent)), axis=0)
    assert not _diversified(prices, 70, 0, [1], 0.85)
    assert _diversified(prices, 70, 0, [2], 0.85)
    assert not _diversified(prices, 20, 0, [2], 0.85)
    prices[71:, 2] = prices[71:, 0]
    assert _diversified(prices, 70, 0, [2], 0.85)


def test_fold_predicts_stocks_without_future_labels_and_purges_both_boundaries(monkeypatch):
    n, m = 970, 2
    features = {
        "X": np.zeros((n, m, 2), dtype=np.float32),
        "eligible": np.ones((n, m), dtype=bool),
        "benchmark_known": np.ones(n, dtype=bool),
        "labels": np.zeros((n, m, 6)),
        "label_end": np.arange(n)[:, None] + 1 + np.array([1, 3, 5]),
    }
    features["X"][:, :, 0] = np.arange(n)[:, None]
    features["labels"][956:] = np.nan

    def fit(X_train, y_train, X_cal, y_cal, X_test, **kwargs):
        assert X_train[:, 0].min() == 200
        assert X_train[:, 0].max() == 697
        assert X_cal[:, 0].min() == 704
        assert X_cal[:, 0].max() == 949
        assert len(X_test) == 28
        assert X_test[:, 0].min() == 956
        return {"predictions": {"ridge": np.zeros((len(X_test), 6))}, "warnings": []}

    monkeypatch.setattr(study, "fit_predict_heads", fit)
    predictions, indices, diagnostic = study._fold_forecasts(
        features, 956, 969, 0, "USD", [str(i) for i in range(n)], None
    )
    assert predictions["ridge"].shape == (28, 6)
    assert len(indices[0]) == 28
    assert diagnostic["fit_sample"]["purged_rows"] == 12
    assert diagnostic["calibration_sample"]["purged_rows"] == 12


def test_end_to_end_study_preserves_all_attempts_and_cash_across_folds(monkeypatch):
    frame, universe, as_of = runpy.run_path("tests/test_historical_study.py")["_history"](1230)

    def forecasts(X_train, y_train, X_cal, y_cal, X_test, **kwargs):
        prediction = np.tile([0.05, 0.06, 0.07, 0.001, 0.002, 0.003], (len(X_test), 1))
        return {
            "predictions": {name: prediction.copy() for name in MODEL_NAMES},
            "warnings": [],
            "calibration": {},
        }

    monkeypatch.setattr(study, "fit_predict_heads", forecasts)
    report = study.evaluate_ensemble(frame, universe, as_of=as_of, budgets=(2000,))
    assert len(report["methodology"]["attempts"]) == 60
    assert len(report["portfolios"]) == 180
    assert len(report["model_diagnostics"]) == 2
    for row in report["portfolios"]:
        assert row["status"] == "complete"
        assert len(row["folds"]) == 2
        assert row["folds"][1]["starting_equity"] == row["folds"][0]["ending_equity"]
        if row["audit_retained"]:
            assert row["ending_equity"] - 2000 == pytest.approx(
                sum(trade["net_pnl"] for trade in row.get("trade_records", []))
            )
        else:
            assert "trade_records" not in row
        assert all(point["settled_cash"] >= 0 for point in row["equity_curve"])
        assert all(
            trade["holding_sessions"] == row["horizon"] for trade in row.get("trade_records", [])
        )
    assert report["latest_candidates"]
    json.dumps(report, allow_nan=False)


def test_forecast_score_matches_entry_and_exit_notional_fee_basis():
    predictions = np.array([[0.004001, 0.02, 0.03, 0, 0.01, 0.02]])
    assert study._forecast_score(predictions, 0, 40)[0] < 0
    assert study._forecast_score(predictions, 1, 100)[0] == pytest.approx(
        0.02 * 0.995 - 0.01 - 0.005
    )
