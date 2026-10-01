"""Independent adversarial timing checks; patches only this process's model call."""

import json
import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from frontier import ensemble_study as study
from frontier.short_horizon_study import _diversified, _simulate_daily, _summarize

n, m, start, end = 1010, 6, 956, 1009
features = {
    "X": np.stack((np.broadcast_to(np.arange(n)[:, None], (n, m)), np.broadcast_to(np.arange(m), (n, m))), axis=-1).astype(np.float32),
    "labels": np.ones((n, m, 6), dtype=np.float32),
    "label_end": np.arange(n)[:, None] + 1 + np.array([1, 3, 5]),
    "eligible": np.ones((n, m), dtype=bool),
    "benchmark_known": np.ones(n, dtype=bool),
}
features["labels"][205, 0, 5] = np.nan
features["benchmark_known"][960] = False
sessions = pd.bdate_range("2000-01-03", periods=n).strftime("%Y-%m-%d").tolist()
calls = []


def predictor(X_train, y_train, X_cal, y_cal, X_test, *, seed):
    calls.append([value.copy() for value in (X_train, y_train, X_cal, y_cal, X_test)])
    return {"predictions": {name: np.full((len(X_test), 6), 0.01) for name in study.LEARNED if name != "diversified_ensemble"}}


study.fit_predict_heads = predictor
_, indices, audit = study._fold_forecasts(features, start, end, 0, "USD", sessions, None)
assert calls[0][0][:, 0].max() == 697
assert calls[0][2][:, 0].min() == 704
assert calls[0][2][:, 0].max() == 949
assert calls[0][4][:, 0].min() == 956
assert 960 not in calls[0][4][:, 0]
assert audit["fit_sample"]["excluded_label_rows"] == 1
assert audit["fit_sample"]["purged_rows"] == audit["calibration_sample"]["purged_rows"] == 36
features["labels"][start:] = np.nan
_, changed_indices, _ = study._fold_forecasts(features, start, end, 0, "USD", sessions, None)
for old, new in zip(calls[0], calls[1]):
    np.testing.assert_array_equal(old, new)
for old, new in zip(indices, changed_indices):
    np.testing.assert_array_equal(old, new)

helpers = runpy.run_path(str(ROOT / "tests/test_short_horizon_study.py"))
market = helpers["market"](n=100, count=4)
rng = np.random.default_rng(123)
returns = rng.normal(0, 0.01, 100)
market["adjusted"][:, 0] = 10 * np.cumprod(1 + returns)
market["adjusted"][:, 1] = 20 * np.cumprod(1 + returns)
market["adjusted"][:, 2] = 30 * np.cumprod(1 - returns)
assert not _diversified(market["adjusted"], 60, 1, [0], 0.85)
assert _diversified(market["adjusted"], 60, 2, [0], 0.85)
assert not _diversified(market["adjusted"], 39, 2, [0], 0.85)
market["adjusted"][61:, :3] = rng.uniform(1, 100, (39, 3))
assert not _diversified(market["adjusted"], 60, 1, [0], 0.85)
assert _diversified(market["adjusted"], 60, 2, [0], 0.85)
ranking = np.tile(np.arange(3), (100, 1))
counts = np.ones(100, dtype=int)
known = np.ones(100, dtype=bool)
known[65] = False
result = _simulate_daily(market, "ridge", 3, 2000, 40, 60, 80, signal_ranking=ranking, signal_counts=counts, signal_known=known)
summary = _summarize(result, market["sessions"][60:81], 2000)
assert summary["status"] == "incomplete"
assert summary["trade_metrics"]["net_expectancy_native"] is None
assert summary["total_return"] is None
assert summary["period_metrics"] == {}
report = {
    "fit_signal_range": [200, 697], "calibration_signal_range": [704, 949],
    "first_test_signal": 956, "purged_rows_each_boundary": 36,
    "test_label_mutation_did_not_change_prediction_membership_or_model_inputs": True,
    "benchmark_gap_excluded_prediction_but_invalidated_trading_path": True,
    "correlation_positive_rejected_negative_allowed": True,
    "correlation_minimum_40_and_future_mutation_passed": True,
    "incomplete_profitability_aggregates_are_null": True,
}
(Path(__file__).parent / "temporal-boundaries.json").write_text(json.dumps(report, indent=2), "utf-8")
print(json.dumps(report))
