"""Focused offline checks for the conditional experiment orchestration."""
import importlib.util
import runpy
from pathlib import Path
from unittest.mock import patch

import numpy as np

SPEC = importlib.util.spec_from_file_location("conditional_runner", Path(__file__).with_name("run_study.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_prediction_population_does_not_depend_on_labels():
    context = {"eligible": np.array([[True, False], [True, True], [False, True]])}
    features = {"labels": np.full((3, 2, 6), np.nan)}
    X = np.array([[1.0], [np.nan], [np.inf]])
    with patch.object(runner, "gather_rows", return_value=X), patch.object(
        runner, "predict_conditional", side_effect=lambda bundle, x: {
            "raw": np.ones((len(x), 6)), "corrected": np.ones((len(x), 6)) * 2
        }
    ):
        result = runner.forecast_candidates(None, features, context, 1, 2)
    assert list(zip(result["rows"], result["columns"])) == [(1, 0), (1, 1), (2, 1)]
    assert np.array_equal(result["invalid_feature"], [False, False, True])
    assert np.isfinite(result["corrected"][:2]).all()
    assert np.isnan(result["corrected"][2]).all()


def test_setup_means_use_only_fit_memberships_and_preserve_overlap():
    X = np.zeros((3, 37)); X[:, 27:30] = [[1, 0, 0], [1, 1, 0], [0, 1, 0]]
    sample = {"X": X, "y": np.tile([1., 3., 8.], (6, 1)).T}
    means, counts = runner.setup_means(sample)
    assert counts == [2, 2, 0]
    assert np.allclose(means[:, 0], [2, 5.5, 4])
    memberships = np.array([[True, True, False], [False, False, True]])
    assert np.allclose(runner.setup_baseline(memberships, means)[:, 0], [3.75, 4])


def test_reliability_edges_come_from_calibration_and_denominators_are_per_head():
    cal = np.tile(np.arange(10.)[:, None], (1, 6))
    predictions = {"raw": cal[:3], "corrected": cal[:3] + 1}
    y = cal[:3].copy(); y[1, 0] = np.nan
    before = runner.forecast_diagnostics(predictions, y, np.ones_like(y), {"raw": cal, "corrected": cal + 1})
    y[:, 1] += 1000
    after = runner.forecast_diagnostics(predictions, y, np.ones_like(y), {"raw": cal, "corrected": cal + 1})
    assert before["raw"][0]["calibration_edges"] == after["raw"][0]["calibration_edges"]
    assert before["raw"][1]["calibration_edges"] == after["raw"][1]["calibration_edges"]
    assert before["raw"][0]["missing_target"] == 1
    assert before["raw"][0]["paired_count"] == 2
    assert sum(x["paired_count"] for x in before["raw"][0]["bins"]) == 2


def test_saved_forecast_assembly_preserves_precision_and_absent_rows(tmp_path):
    directory = tmp_path / "block"; directory.mkdir()
    np.savez(directory / "forecasts.npz", rows=np.array([1]), columns=np.array([0]), corrected=np.arange(6.)[None, :] + 1e-11)
    block = {"files": {"block/forecasts.npz": runner.sha(directory / "forecasts.npz")}, "forecast_path": "block/forecasts.npz"}
    path, identity = runner.assemble_forecasts(tmp_path, [block], (3, 2, 6), "definition")
    result = np.load(path, mmap_mode="r")
    assert np.array_equal(result[1, 0], np.arange(6.) + 1e-11)
    assert np.isnan(result[0]).all() and np.isnan(result[2]).all()
    assert identity == runner.sha(path)
    assert runner.assemble_forecasts(tmp_path, [block], (3, 2, 6), "definition") == (path, identity)


def test_full_account_keeps_held_positions_when_new_block_forecasts_switch(tmp_path):
    helpers = runpy.run_path("tests/test_short_horizon_study.py")
    market = helpers["market"](n=11, count=3)
    ranking = np.tile([0, 1], (11, 1)); ranking[3] = [1, 0]
    counts = np.zeros(11, dtype=int); counts[[0, 3]] = 1
    forecast = np.full((11, 3, 6), np.nan)
    forecast[:3, 0] = [0.1, 0.1, 0.1, 0, 0, 0]
    forecast[3:, 0] = [-0.1, -0.1, -0.1, 0, 0, 0]
    forecast[3:, 1] = [0.1, 0.1, 0.1, 0, 0, 0]
    request = {"holding_sessions": [1, 3, 5], "capital_usd": 2000, "round_trip_bps": 40}
    with patch.object(runner, "ROOT", tmp_path), patch.object(runner, "_simulate_daily", wraps=runner._simulate_daily) as engine:
        report = runner.evaluate_account(market, ranking, counts, forecast, "full-period", request, "definition", 0, 10,
                                         "conditional_net_dollars", 5, "proportional")
    assert engine.call_count == 1
    assert report["status"] == "complete"
    trades = report["trade_records"]
    assert len(trades) == 2
    assert [r["exit_session"] for r in trades] == [market["sessions"][6], market["sessions"][9]]
    assert trades[0]["entry_session"] < market["sessions"][3] < trades[0]["exit_session"]
    assert report["forecast_identity"] == "full-period"


def test_failed_accounts_remain_explicit_and_are_not_silently_retried(tmp_path):
    request = {"holding_sessions": [1, 3, 5], "capital_usd": 2000, "round_trip_bps": 40}
    with patch.object(runner, "ROOT", tmp_path), patch.object(runner, "_simulate_daily", side_effect=ValueError("missing held price")) as engine:
        first = runner.evaluate_account({}, None, None, None, "forecasts", request, "definition", 0, 10, "static_setup_rank", 1, "proportional")
        second = runner.evaluate_account({}, None, None, None, "forecasts", request, "definition", 0, 10, "static_setup_rank", 1, "proportional")
    assert engine.call_count == 1
    assert first == second
    assert first["status"] == "failed" and first["total_return"] is None
    assert "missing held price" in first["error"]
    assert first["fill_convention"] == "original unconditional next-close fill sizing"
