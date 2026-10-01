"""Operational qualification on a declared subset of the frozen historical capture."""

import ctypes
import hashlib
import json
import sys
import time
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from frontier.historical_data import read_history

OUT = Path(__file__).resolve().parent
SOURCE_ID = "90af4c840aad48f7ab58fba7a682f96a"
SOURCE = ROOT / "artifacts/historical-lab/runs" / SOURCE_ID
SYMBOLS = ("AAPL", "AMZN", "META", "MSFT", "SPY", "RY.TO", "TD.TO", "XIU.TO")
CODE_NAMES = (
    "ensemble_study.py", "ensemble_models.py", "ensemble_features.py", "historical_data.py",
    "historical_study.py", "short_horizon_study.py", "historical_settlement.py", "strategy_study.py",
)


def read(path):
    return json.loads(path.read_text("utf-8"))


def save(name, value):
    with (OUT / name).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, allow_nan=False, separators=(",", ":"))


def identities():
    return {name: hashlib.sha256((ROOT / "src/frontier" / name).read_bytes()).hexdigest() for name in CODE_NAMES}


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in (
        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
    )]


def memory():
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(MemoryCounters), ctypes.c_ulong)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"peak_working_set_mb": counters.PeakWorkingSetSize / 2**20, "working_set_mb": counters.WorkingSetSize / 2**20}


def prepare():
    original = read(SOURCE / "definition.json")
    records = {r["symbol"]: r for r in read(SOURCE / "capture-index.json")}
    specs = {s["symbol"]: s for s in original["instruments"]}
    selected = [records[symbol] for symbol in SYMBOLS]
    universe = [specs[symbol] for symbol in SYMBOLS]
    assert all(r["spec"] == specs[r["symbol"]] for r in selected)
    index_sha = hashlib.sha256((SOURCE / "capture-index.json").read_bytes()).hexdigest()
    assert index_sha == original["capture_index_sha256"]
    frames, normalization = [], []
    for record in selected:
        frame = read_history(ROOT / "data/historical/capture-workspace", record)
        frame = frame.loc[frame.session >= "2020-01-01"].copy()
        normalization.append({"symbol": record["symbol"], "rows": len(frame), "first_session": frame.session.min(), "last_session": frame.session.max(), **frame.attrs})
        frames.append(frame)
    definition = {
        "kind": "partial-universe/date-range operational qualification; not edge evidence",
        "source_run_id": SOURCE_ID, "source_capture_index_sha256": index_sha,
        "as_of": original["frozen_at"], "first_included_session": "2020-01-01",
        "symbols": list(SYMBOLS), "instruments": universe, "budgets": [2000],
        "all_declared_strategies_and_costs": True, "hyperparameters_unmodified": True,
        "normalization": normalization,
    }
    save("capture-index.json", selected)
    save("definition.json", definition)
    return pd.concat(frames, ignore_index=True), universe, definition


def sanity(result):
    errors, checked_trades, complete, incomplete = [], 0, 0, []
    fee_legs_checked = 0
    for row in result["portfolios"]:
        key = "/".join(str(row[field]) for field in ("currency", "strategy", "horizon", "cost_bps"))
        if row["status"] != "complete":
            incomplete.append({"account": key, "status": row["status"], "missing": row.get("missing", [])})
            if row["total_return"] is not None or row["trade_metrics"]["net_expectancy_native"] is not None or row["period_metrics"]:
                errors.append(key + ": incomplete account reports profitability")
            continue
        complete += 1
        curve = row["equity_curve"]
        points = np.array([[p[name] for name in ("equity", "cash", "settled_cash", "unsettled_cash")] for p in curve])
        if not np.isfinite(points).all() or (points < -1e-7).any():
            errors.append(key + ": invalid daily ledger value")
        if not np.allclose(points[:, 1], points[:, 2] + points[:, 3], atol=1e-7, rtol=1e-12):
            errors.append(key + ": cash does not reconcile with settlement")
        if (points[:, 0] < points[:, 1] - 1e-7).any():
            errors.append(key + ": equity below cash with long-only holdings")
        if not np.isclose(row["ending_equity"], row["budget"] + row["trade_metrics"]["net_pnl_total"], atol=1e-7, rtol=1e-12):
            errors.append(key + ": account wealth differs from realized PnL")
        if not np.isclose(points[-1, 0], points[-1, 1], atol=1e-7):
            errors.append(key + ": final fold still holds positions")
        trades = row["trade_metrics"]["completed_trades"]
        if row["activity"].get("filled_positions", 0) != trades:
            errors.append(key + ": completed fills and exits differ")
        if trades and (row["trade_metrics"]["mean_holding_sessions"] != row["horizon"] or row["trade_metrics"]["max_holding_sessions"] != row["horizon"]):
            errors.append(key + ": holding clock mismatch")
        if row["audit_retained"]:
            records = row["trade_records"]
            checked_trades += len(records)
            if len(records) != trades:
                errors.append(key + ": retained trade count differs")
            index = {p["session"]: i for i, p in enumerate(curve)}
            for trade in records:
                for fee_name, notional_name in (("entry_fee", "entry_notional"), ("exit_fee", "exit_notional")):
                    expected_fee = trade[notional_name] * row["cost_bps"] / 20000
                    if not np.isclose(trade[fee_name], expected_fee, atol=1e-10, rtol=1e-12):
                        errors.append(key + ": fee basis differs")
                    fee_legs_checked += 1
                if index[trade["entry_session"]] != index[trade["signal_session"]] + 1 or index[trade["exit_session"]] != index[trade["entry_session"]] + row["horizon"]:
                    errors.append(key + ": signal/fill/exit ordering differs")
                    break
                if trade["quantity"] <= 0 or int(trade["quantity"]) != trade["quantity"]:
                    errors.append(key + ": non-whole share fill")
                    break
                expected = trade["exit_notional"] - trade["entry_notional"] - trade["entry_fee"] - trade["exit_fee"]
                if not np.isclose(trade["net_pnl"], expected, atol=1e-9):
                    errors.append(key + ": trade PnL differs")
                    break
            if not np.isclose(sum(t["entry_fee"] + t["exit_fee"] for t in records), row["trade_metrics"]["fees"], atol=1e-7):
                errors.append(key + ": audited fee total differs")
            if not np.isclose(sum(t["net_pnl"] for t in records), row["trade_metrics"]["net_pnl_total"], atol=1e-7):
                errors.append(key + ": audited PnL does not match account")
        elif "trade_records" in row:
            errors.append(key + ": aggregate-only account unexpectedly retains records")
    return {"complete_accounts_checked": complete, "incomplete_accounts": incomplete, "detailed_trades_checked": checked_trades, "fee_legs_checked": fee_legs_checked, "errors": errors, "passed": not errors}


def main():
    started = time.perf_counter()
    frame, universe, definition = prepare()
    if "--prepare-only" in sys.argv:
        print(json.dumps({"phase": "prepared", "rows": len(frame), "symbols": list(SYMBOLS), "as_of": definition["as_of"], "seconds": time.perf_counter() - started}), flush=True)
        return
    from frontier import ensemble_models, ensemble_study
    from frontier.historical_lab import compact_result
    assert hasattr(ensemble_study, "_forecast_score"), "Wait for reviewed forecast-score fix"
    assert "hist_gradient_boosting" in ensemble_models.BASE_MODEL_NAMES, "Wait for declared fourth model"
    assert len(ensemble_study.STRATEGIES) == 20
    definition.update(financial_source_sha256=identities(), package_versions={name: version(name) for name in ("numpy", "pandas", "scikit-learn")}, methodology=ensemble_study._methodology((2000,)))
    save("definition.json", definition)
    evaluated_at = time.perf_counter()
    events = []

    def progress(value):
        event = {"elapsed_seconds": time.perf_counter() - evaluated_at, **value, **memory()}
        events.append(event)
        print(json.dumps(event), flush=True)

    result = ensemble_study.evaluate_ensemble(frame, universe, as_of=definition["as_of"], budgets=(2000,), progress=progress)
    finished = time.perf_counter()
    assert definition["financial_source_sha256"] == identities(), "Financial source changed during smoke"
    save("result.json", result)
    save("summary.json", compact_result(result))
    checks = sanity(result)
    save("account-sanity.json", checks)
    report = {
        "evaluation_seconds": finished - evaluated_at, "normalization_and_import_seconds": evaluated_at - started,
        "total_seconds": time.perf_counter() - started, "rows": len(frame),
        "portfolio_statuses": dict(Counter(r["status"] for r in result["portfolios"])),
        "benchmark_statuses": dict(Counter(r["status"] for r in result["benchmarks"])),
        "strategies": list(ensemble_study.STRATEGIES), "models": list(ensemble_models.BASE_MODEL_NAMES),
        "model_folds": len(result["model_diagnostics"]),
        "warnings": [w for fold in result["model_diagnostics"] for w in fold["warnings"]],
        "progress": events, "sanity": checks, "operational_qualification_only": True, **memory(),
    }
    save("performance.json", report)
    assert checks["passed"], checks["errors"]
    print(json.dumps({key: value for key, value in report.items() if key not in ("progress", "warnings")}), flush=True)


if __name__ == "__main__":
    main()
