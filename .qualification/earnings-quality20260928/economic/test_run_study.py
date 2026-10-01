"""Synthetic orchestration checks; never read original study financial outcomes."""
from copy import deepcopy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_study as run
from frontier.historical_settlement import build_settlement_indices


def synthetic():
    calendar = json.loads((HERE.parents[1] / "post-filing-strategy20260928/calendar.json").read_text())
    days = [row["session"] for row in calendar["sessions"]]
    symbols = [f"S{i:02}" for i in range(25)] + ["SPY"]
    shape = (len(days), len(symbols))
    market = {"sessions": days, "symbols": symbols, "benchmark": 25,
              "dates": np.array(days, dtype="datetime64[D]"),
              "close": np.full(shape, 20.), "adjusted": np.full(shape, 20.), "atr": np.full(shape, .25),
              "vendor_quote_close": np.full(shape, 20.), "vendor_quote_volume": np.full(shape, 1000000.),
              "settlement_index": build_settlement_indices(days, "USD")}
    cohort = {"selected": [{"symbol": symbol, "cik": str(j+1).zfill(10)} for j, symbol in enumerate(symbols[:-1])]}
    events = []
    for year, count, issuers in ((2017, 256, 25), (2020, 64, 16), (2021, 3, 3)):
        base = next(i for i, day in enumerate(days) if day[:4] == str(year))
        for n in range(count):
            j = n % issuers
            entry = base + 10 * (n // issuers)
            end = entry + 5
            decision = datetime.fromisoformat(days[entry] + "T09:00:00").replace(tzinfo=ZoneInfo("America/New_York"))
            events.append({"symbol": symbols[j], "cik": str(j+1).zfill(10), "accession": f"synthetic-{year}-{n}",
                "filing_date": days[entry-1], "S": str(1.2+(n % 5)*.1), "Q": "0.01",
                "feature_status": "qualified", "q_status": "qualified", "joint_feature_status": "qualified",
                "strategy_source_status": "qualified", "execution_status": "qualified",
                "decision_time": decision.isoformat(), "availability_floor": decision.replace(hour=1).isoformat(),
                "entry_session": days[entry], "exit_session": days[end],
                "entry_time": calendar["sessions"][entry]["close"], "exit_time": calendar["sessions"][end]["close"],
                "source_sha256": "synthetic"})
            for key in ("close", "adjusted", "vendor_quote_close"):
                market[key][entry:end+1, j] = 20 * (1 + .02*np.arange(6))
    rows = run.event_inputs.prepare_events(market, events, cohort, calendar)["rows"]
    return market, rows, calendar, cohort


def test_full_synthetic_ten_models_twenty_accounts_and_forecast_barrier(tmp_path):
    market, rows, calendar, cohort = synthetic()
    original_extract = run.event_inputs.extract_labels
    destination = tmp_path / "models"
    test_seen = []

    def checked_extract(m, accessed):
        for row in accessed:
            year = run.models._decision(row).year
            if year >= 2021:
                # 2021 rows are test labels in fold2021, later calibration/fitting rows are causal.
                barrier = destination / str(year) / "forecasts-persisted.json"
                assert barrier.is_file(), "Test label read before both saved forecasts"
                for family in run.models.FAMILIES:
                    path = destination / str(year) / family / "forecasts.json"
                    assert path.is_file()
                    assert run.sha(path) == run.read(barrier)["forecast_sha256"][family]
                test_seen.append(row["event_id"])
        return original_extract(m, accessed)

    with patch.object(run.event_inputs, "extract_labels", side_effect=checked_extract):
        forecasts, models, labels = run.run_folds(market, rows, calendar, destination)
    assert len(models) == 10
    assert [row["status"] for row in models].count("complete") == 2
    assert [row["status"] for row in models].count("insufficient_sample") == 8
    assert len(set(test_seen)) == 3 and len(labels) == 3
    for family, records in forecasts.items():
        assert len(records) == 3
        assert all(row["status"] == "predicted" for row in records)
        saved = run.read(destination / (family + "-all-forecasts.json"))
        assert saved["forecasts"] == records
    reports = run.run_accounts(market, rows, forecasts, destination, tmp_path / "accounts")
    assert len(reports) == 20
    assert all(row["status"] == "complete" for row in reports)
    assert all(row["trades"] == 3 for row in reports)
    assert all(row["weekly_objective"]["count"] > 250 for row in reports)
    for path in (tmp_path / "accounts").glob("*.json"):
        data = run.read(path)
        if isinstance(data, dict):
            assert data["synthetic_interval_override"] is False
            assert len(data["event_decisions"]) == len(rows)
    counts = run.denominators(rows, forecasts, labels, cohort)
    assert counts["retained_events"] == 323 and counts["requested_issuers"] == 25
    reference = run.references(market)
    assert reference["10000"]["cash"]["total_return"] == 0
    assert reference["10000"]["SPY"]["total_return"] == 0


def test_lazy_labels_reject_future_purged_unavailable_and_cache_valid_access():
    market, rows, calendar, _ = synthetic()
    fold = run.models.specification()["chronology"]["folds"][0]
    labels = run.FoldLabels(market, rows, fold, market["sessions"])
    future = next(row for row in rows if row["decision_timestamp"].startswith("2021"))
    with pytest.raises(AssertionError):
        labels.get(future["event_id"])
    prior = rows[0]
    assert labels.get(prior["event_id"]) == labels.get(prior["event_id"])
    assert len(labels.values) == 1 and len(labels.accesses) == 2
    labels.rows[prior["event_id"]] = dict(prior, planned_label_end_session="2020-01-02")
    with pytest.raises(AssertionError):
        labels.get(prior["event_id"])
    labels.rows[prior["event_id"]] = dict(prior, model_input_status="unavailable")
    with pytest.raises(AssertionError):
        labels.get(prior["event_id"])


def test_account_failure_does_not_drop_declared_matrix(tmp_path):
    market, rows, _, _ = synthetic()
    for family in run.models.FAMILIES:
        run.write(tmp_path / (family + "-all-forecasts.json"), {"forecasts": []})
    def fail(*args, **kwargs):
        raise ValueError("Synthetic collision retained")
    with patch.object(run.accounts, "run_account", side_effect=fail):
        reports = run.run_accounts(market, rows, {f: [] for f in run.models.FAMILIES}, tmp_path, tmp_path/"accounts")
    assert len(reports) == 20 and all(row["status"] == "failed" for row in reports)
    assert len(list((tmp_path / "accounts").glob("*-failure.json"))) == 20


def test_read_only_lock_refuses_active_writer(tmp_path):
    path = tmp_path / "capture.lock.sqlite"
    connection = run.sqlite3.connect(path)
    connection.execute("CREATE TABLE fixture (value INTEGER)")
    connection.commit()
    connection.execute("BEGIN EXCLUSIVE")
    with pytest.raises(run.sqlite3.OperationalError):
        with run.read_lock(path):
            pass
    connection.rollback()
    connection.close()
    before = path.read_bytes()
    with run.read_lock(path):
        pass
    assert before == path.read_bytes()


def test_definition_review_and_bound_dependency_gates(tmp_path):
    path = tmp_path / "definition.json"
    run.write(path, {"schema": 1, "reviewed_for_execution": False})
    with pytest.raises(ValueError, match="Root-reviewed"):
        run.validate_definition(path)
    assert "economic/run_study.py" in " ".join(run.required_code_paths())
    assert set(run.runtime_dependencies()) == set(run.PACKAGES)


def test_diagnostic_same_rows_baseline_and_missing_bins():
    from types import SimpleNamespace
    bundle = SimpleNamespace(family="ridge", training_mean=np.array([.02, .03]),
        quantile_edges={"raw": [[.1], [.1]], "corrected": [[.2], [.2]]},
        audit={"status": "complete"})
    forecasts = {"test_decision_year": 2021, "forecasts": [
        {"event_id": "good", "status": "predicted", "raw": [.04, .05], "corrected": [.03, .04]},
        {"event_id": "missing", "status": "predicted", "raw": [.4, .5], "corrected": [.3, .4]},
        {"event_id": "causal-unavailable", "status": "unavailable", "raw": None, "corrected": None}]}
    labels = {"good": {"status": "qualified", "targets": [.01, .02]},
              "missing": {"status": "unavailable"},
              "causal-unavailable": {"status": "qualified", "targets": [.9, .9]}}
    result = run.diagnostics(bundle, forecasts, labels)
    for head in result["heads"].values():
        assert head["raw"]["count"] == 1
        assert head["raw"]["missing_labels"] == 1
        assert head["raw"]["training_mean_on_same_rows"]["count"] == 1
        assert head["training_mean"]["count"] == 1
    assert result["heads"]["return_5"]["raw"]["mae"] == pytest.approx(.03)
    assert result["heads"]["return_5"]["raw"]["training_mean_on_same_rows"]["mae"] == pytest.approx(.01)
    assert result["heads"]["return_5"]["raw"]["bins"][1]["missing_labels"] == 1


def test_missing_benchmark_mark_remains_unavailable():
    market, _, _, _ = synthetic()
    index = market["sessions"].index("2022-01-03")
    market["adjusted"][index, market["benchmark"]] = np.nan
    result = run.references(market)
    assert result["10000"]["SPY"]["status"] == "incomplete"
    assert result["10000"]["SPY"]["total_return"] is None


def test_declared_matrix_and_clustering_keep_idle_denominators():
    matrix = run.declared_attempts()
    assert len(matrix["models"]) == 10 and len(matrix["accounts"]) == 20
    rows = [{"model_input_status": "qualified", "cik": "0000000001",
             "decision_timestamp": "2021-01-04T09:00:00-05:00", "entry_index": 1,
             "planned_label_end_index": 6, "event_id": "one"},
            {"model_input_status": "qualified", "cik": "0000000001",
             "decision_timestamp": "2021-01-11T09:00:00-05:00", "entry_index": 6,
             "planned_label_end_index": 11, "event_id": "two"},
            {"model_input_status": "qualified", "cik": "0000000002",
             "decision_timestamp": "2021-01-05T09:00:00-05:00", "entry_index": 2,
             "planned_label_end_index": 7, "event_id": "three"}]
    cluster = run.event_clustering(rows)
    assert cluster["overlapping_closed_label_interval_pairs"] == 3
    assert cluster["same_issuer_overlapping_pairs"] == 1
    assert cluster["distinct_ciks"] == 2
