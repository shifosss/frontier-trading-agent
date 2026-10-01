"""Reproducible read-only real-capture smoke for the daily short-hold engine."""

import ctypes
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from frontier.historical_data import read_history
from frontier.historical_lab import compact_result
from frontier.short_horizon_study import evaluate_short_horizon


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = "577a24e71a844022b3ac86ca66e32c34"
SOURCE = ROOT / "artifacts/historical-lab/runs" / RUN
SYMBOLS = "SPY AAPL MSFT AMD JPM XOM WMT NVDA TSLA AMZN GOOGL META COST".split()


def read_json(path):
    return json.loads(path.read_text("utf-8"))


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage",
        )
    ]


def memory():
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(MemoryCounters), ctypes.c_ulong)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"peak_working_set_mb": counters.PeakWorkingSetSize / 2**20,
            "working_set_mb": counters.WorkingSetSize / 2**20}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, allow_nan=False, indent=2), "utf-8")


def main():
    started = time.perf_counter()
    definition = read_json(SOURCE / "definition.json")
    records = {row["symbol"]: row for row in read_json(SOURCE / "capture-index.json")}
    specs = {row["symbol"]: row for row in definition["instruments"]}
    selected = [records[symbol] for symbol in SYMBOLS]
    universe = [specs[symbol] for symbol in SYMBOLS]
    assert all(row["spec"] == specs[row["symbol"]] for row in selected)
    as_of = definition["frozen_at"]
    frames = [read_history(ROOT / "data/historical/capture-workspace", row) for row in selected]
    frame = pd.concat(frames, ignore_index=True)
    del frames
    normalized_at = time.perf_counter()
    events = []

    def progress(value):
        event = {"elapsed_seconds": time.perf_counter() - normalized_at, **value, **memory()}
        events.append(event)
        print(json.dumps(event), flush=True)

    print(json.dumps({"phase": "normalized", "symbols": SYMBOLS, "rows": len(frame),
                      "as_of": as_of, "seconds": normalized_at - started}), flush=True)
    result = evaluate_short_horizon(frame, universe, as_of=as_of, budgets=(500,), progress=progress)
    evaluated_at = time.perf_counter()
    summary = compact_result(result)
    save("result-summary.json", summary)
    statuses = {key: dict(Counter(row["status"] for row in result[key]))
                for key in ("portfolios", "walk_forward", "benchmarks")}
    incomplete = [{"collection": key, **{field: row.get(field) for field in (
        "currency", "budget", "cost_bps", "strategy", "horizon", "symbol", "status", "missing"
    )}} for key in statuses for row in result[key] if row["status"] != "complete"]
    report = {
        "source_run_id": RUN, "as_of": as_of, "symbols": SYMBOLS, "budgets": [500],
        "rows": len(frame), "coverage": result["coverage"]["markets"],
        "normalization_seconds": normalized_at - started,
        "evaluation_seconds": evaluated_at - normalized_at,
        "total_seconds": time.perf_counter() - started,
        "statuses": statuses, "incomplete_paths": incomplete, "progress": events,
        "fixed_completed_trade_count": sum(row["trade_metrics"]["completed_trades"] for row in result["portfolios"]),
        "rolling_audit_trade_count": sum(len(row.get("trade_records", [])) for row in result["walk_forward"]),
        "fixed_audit_retained": any(row["audit_retained"] for row in result["portfolios"]),
        "summary_bytes": (OUT / "result-summary.json").stat().st_size,
        "source_sha256": {name: hashlib.sha256((ROOT / "src/frontier" / name).read_bytes()).hexdigest()
                          for name in ("short_horizon_study.py", "historical_settlement.py", "historical_study.py")},
        **memory(),
    }
    save("performance.json", report)
    print(json.dumps({key: value for key, value in report.items() if key not in ("progress", "source_sha256")}), flush=True)


if __name__ == "__main__":
    main()
