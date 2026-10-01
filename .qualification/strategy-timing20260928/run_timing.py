"""Offline paired entry-timing diagnostics; default invocation only runs synthetic checks."""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import os
import sqlite3
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
TIMINGS = ("next_open_to_same_close_exit", "next_close_to_close", "next_open_to_open")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def status(phase, **details):
    value = dict(phase=phase, updated_at=datetime.now(timezone.utc).isoformat(), pid=os.getpid(), **details)
    save(ROOT / "status.json", value)
    print(json.dumps(value), flush=True)


def number(value):
    return float(value) if value is not None else float("nan")


def bar_values(raw_open, raw_close, raw_high, raw_low, adjusted_close, cached_adjusted_close):
    """Derive same-source adjusted open without changing any provider price."""
    opened, closed, high, low, adjusted, cached = map(number, (
        raw_open, raw_close, raw_high, raw_low, adjusted_close, cached_adjusted_close
    ))
    close_issue = None
    if not all(math.isfinite(v) and v > 0 for v in (closed, high, low, adjusted, cached)):
        close_issue = "missing_or_nonpositive_close_endpoint"
    elif not low <= closed <= high:
        close_issue = "close_outside_raw_high_low"
    elif adjusted != cached:
        close_issue = "raw_adjusted_close_differs_from_cache"
    factor = adjusted / closed if close_issue is None else float("nan")
    if close_issue is None and not (math.isfinite(factor) and factor > 0):
        close_issue = "invalid_same_source_adjustment_factor"
    open_issue = close_issue
    if open_issue is None and not (math.isfinite(opened) and opened > 0):
        open_issue = "missing_or_nonpositive_open"
    if open_issue is None and not low <= opened <= high:
        open_issue = "open_outside_raw_high_low"
    adjusted_open = opened * factor if open_issue is None else float("nan")
    if open_issue is None and not (math.isfinite(adjusted_open) and adjusted_open > 0):
        open_issue = "invalid_adjusted_open"
    close_log = math.log(adjusted) if close_issue is None else None
    open_log = math.log(adjusted_open) if open_issue is None else None
    intraday = math.log(closed) - math.log(opened) if open_issue is None else None
    identity = (close_log - open_log - intraday) if open_issue is None else None
    return {"close_log": close_log, "open_log": open_log, "intraday_log": intraday,
            "close_issue": close_issue, "open_issue": open_issue,
            "adjustment_identity_residual": identity}


def outcomes(signal, entry, exit_):
    values = {}
    for timing, entry_key, exit_key in (
        (TIMINGS[0], "open_log", "close_log"),
        (TIMINGS[1], "close_log", "close_log"),
        (TIMINGS[2], "open_log", "open_log"),
    ):
        a = entry.get(entry_key) if entry else None
        b = exit_.get(exit_key) if exit_ else None
        values[timing] = b - a if a is not None and b is not None else None
    overnight = None
    if signal and entry and signal["close_log"] is not None and entry["open_log"] is not None:
        overnight = entry["open_log"] - signal["close_log"]
    entry_intraday = entry["intraday_log"] if entry else None
    exit_intraday = exit_["intraday_log"] if exit_ else None
    same_residual = None
    equal_residual = None
    if values[TIMINGS[0]] is not None and values[TIMINGS[1]] is not None:
        same_residual = values[TIMINGS[0]] - values[TIMINGS[1]] - entry_intraday
    if values[TIMINGS[2]] is not None and values[TIMINGS[1]] is not None:
        equal_residual = values[TIMINGS[2]] - values[TIMINGS[1]] - (entry_intraday-exit_intraday)
    return dict(log_returns=values, overnight_log=overnight, entry_intraday_log=entry_intraday,
                exit_intraday_log=exit_intraday, same_exit_identity_residual=same_residual,
                equal_clock_identity_residual=equal_residual)


def stats(values):
    values = np.asarray([v for v in values if v is not None], dtype=float)
    return {"count": len(values), "mean": float(values.mean()) if len(values) else None,
            "median": float(np.median(values)) if len(values) else None,
            "positive_fraction": float((values > 0).mean()) if len(values) else None}


def bootstrap(values, sampled_dates):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).any():
        return None
    samples = values[sampled_dates]
    count = np.isfinite(samples).sum(axis=1)
    means = np.nansum(samples, axis=1) / np.where(count > 0, count, np.nan)
    known = means[np.isfinite(means)]
    return np.quantile(known, [0.025, 0.975]).tolist() if len(known) else None


def select_events(market, scores, request, first, last_signal):
    from frontier.daily_policy import plan_entries

    events, needed = [], defaultdict(set)
    symbols = market["symbols"]
    for policy in request["policies"]:
        values = scores[policy]
        for t in range(first, last_signal + 1):
            finite = np.isfinite(values[t])
            ranked = np.argsort(-np.where(finite, values[t], -np.inf), kind="stable")[:finite.sum()]
            plan = plan_entries(symbols=symbols, ranking=ranked, prices=market["close"][t],
                                atrs=market["atr"][t], nav=2000.0, available_cash=2000.0,
                                slots=5, cost_bps=40.0, audit=False)
            selected = [{"symbol_index": int(o["symbol_index"]), "quantity": int(o["quantity"]),
                         "reference_price": float(o["reference_price"])} for o in plan["orders"]]
            events.append({"policy": policy, "signal_index": t, "eligible_count": int(finite.sum()),
                           "selected": selected})
            for row in selected:
                needed[row["symbol_index"]].update((t, t+1, t+2, t+4, t+6))
        status("selecting_original_signals", policy=policy, date_cohorts=len(events))
    benchmark = int(market["benchmark"])
    for t in range(first, last_signal + 1):
        events.append({"policy": "SPY_reference", "signal_index": t, "eligible_count": 1,
                       "selected": [{"symbol_index": benchmark, "quantity": None, "reference_price": None}]})
        needed[benchmark].update((t, t+1, t+2, t+4, t+6))
    return events, needed


def load_bars(market, needed, capture_run_id):
    index_path = REPO / "artifacts/historical-lab/runs" / capture_run_id / "capture-index.json"
    assert sha(index_path) == read(ROOT / "open-availability-definition.json")["capture_index_sha256"]
    records = {r["symbol"]: r for r in read(index_path)}
    position = {s: i for i, s in enumerate(market["sessions"])}
    bars, actions, source_audit, issues = {}, {}, [], []
    max_factor_residual = 0.0
    for count, (j, required) in enumerate(sorted(needed.items()), 1):
        symbol = market["symbols"][j]
        record = records[symbol]
        path = REPO / "data/historical/capture-workspace" / record["path"]
        assert sha(path) == record["sha256"], f"Changed source: {symbol}"
        item = read(path)["chart"]["result"][0]
        quote = item["indicators"]["quote"][0]
        stamps = item["timestamp"]
        fields = {key: quote.get(key, []) for key in ("open", "close", "high", "low")}
        fields["adjusted_close"] = item["indicators"]["adjclose"][0]["adjclose"]
        dates = pd.to_datetime(stamps, unit="s", utc=True).tz_convert("America/Toronto").strftime("%Y-%m-%d")
        duplicates = set(pd.Index(dates)[pd.Index(dates).duplicated(keep=False)])
        aligned = all(len(a) == len(stamps) for a in fields.values())
        locations = {session: row for row, session in enumerate(dates)}
        found = {}
        for i in sorted(required):
            session = market["sessions"][i]
            row = locations.get(session)
            if not aligned or row is None or session in duplicates:
                reason = "misaligned_source_arrays" if not aligned else "missing_session" if row is None else "duplicate_source_session"
                issues.append({"symbol": symbol, "session": session, "kind": reason})
                continue
            value = bar_values(*(fields[key][row] for key in ("open", "close", "high", "low", "adjusted_close")), market["adjusted"][i, j])
            found[i] = value
            for kind in set(v for v in (value["close_issue"], value["open_issue"]) if v is not None):
                issues.append({"symbol": symbol, "session": session, "kind": kind})
            if value["adjustment_identity_residual"] is not None:
                max_factor_residual = max(max_factor_residual, abs(value["adjustment_identity_residual"]))
        bars[j] = found
        reported = []
        for kind in ("splits", "dividends"):
            for action in item.get("events", {}).get(kind, {}).values():
                session = pd.Timestamp(action["date"], unit="s", tz="UTC").tz_convert("America/Toronto").strftime("%Y-%m-%d")
                if session in position:
                    reported.append((position[session], kind))
        actions[j] = sorted(reported)
        source_audit.append({"symbol": symbol, "sha256": record["sha256"], "requested_sessions": len(required),
                             "mapped_sessions": len(found), "open_array_present": "open" in quote,
                             "arrays_aligned": aligned})
        if count % 100 == 0 or count == len(needed):
            status("reading_retained_opens", sources=count, total_sources=len(needed), issue_records=len(issues))
    save(ROOT / "source-audit.json", {"sources": source_audit, "issue_records": issues,
         "issue_counts": dict(Counter(r["kind"] for r in issues)),
         "maximum_same_bar_adjustment_identity_residual": max_factor_residual})
    return bars, actions


def evaluate(events, bars, actions, market, context, first, last_signal):
    primary = defaultdict(lambda: defaultdict(list))
    overnight = defaultdict(lambda: defaultdict(list))
    cells = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(Counter)
    identity_maxima = {"same_exit": 0.0, "equal_clock": 0.0}
    fields = ["policy", "signal_session", "symbol", "quantity_reference", "horizon", "signal_regime",
              "reported_actions_including_entry", "next_open_same_exit_log", "next_close_log", "next_open_to_open_log",
              "next_open_same_exit_simple", "next_close_simple", "next_open_to_open_simple",
              "overnight_gap_log", "entry_intraday_log", "exit_intraday_log", "entry_open_issue", "exit_open_issue", "exit_close_issue"]
    with (ROOT / "event-outcomes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cohort in events:
            policy, t, selected = cohort["policy"], cohort["signal_index"], cohort["selected"]
            counts[policy]["signal_dates"] += 1
            counts[policy]["eligible_stock_date_count"] += cohort["eligible_count"]
            counts[policy]["planned_events"] += len(selected)
            counts[policy]["active_dates" if selected else "no_selected_candidate_dates"] += 1
            primary[policy][t] = []
            overnight[policy][t] = []
            for h in (1, 3, 5):
                for timing in TIMINGS:
                    cells[(policy, h, timing)][t] = []
            for chosen in selected:
                j, e = chosen["symbol_index"], t+1
                source = bars[j]
                signal, entry = source.get(t), source.get(e)
                primary[policy][t].append(entry["intraday_log"] if entry else None)
                if signal and entry and signal["close_log"] is not None and entry["open_log"] is not None:
                    overnight[policy][t].append(entry["open_log"]-signal["close_log"])
                else:
                    overnight[policy][t].append(None)
                for h in (1, 3, 5):
                    x = e+h
                    exit_ = source.get(x)
                    result = outcomes(signal, entry, exit_)
                    for timing in TIMINGS:
                        cells[(policy, h, timing)][t].append(result["log_returns"][timing])
                    for short, long in (("same_exit", "same_exit_identity_residual"), ("equal_clock", "equal_clock_identity_residual")):
                        value = result[long]
                        if value is not None:
                            identity_maxima[short] = max(identity_maxima[short], abs(value))
                    logs = [result["log_returns"][timing] for timing in TIMINGS]
                    writer.writerow(dict(zip(fields, [policy, market["sessions"][t], market["symbols"][j], chosen["quantity"], h,
                        int(context["regime_state"][t]), sum(e <= date <= x for date, _ in actions[j]),
                        *logs, *(math.expm1(v) if v is not None else None for v in logs),
                        result["overnight_log"], result["entry_intraday_log"], result["exit_intraday_log"],
                        entry["open_issue"] if entry else "missing_entry_bar", exit_["open_issue"] if exit_ else "missing_exit_bar",
                        exit_["close_issue"] if exit_ else "missing_exit_bar"])))
    n = last_signal-first+1
    rng = np.random.default_rng(1729)
    starts = rng.integers(0, n, size=(2000, math.ceil(n/10)))
    sampled_dates = ((starts[:, :, None] + np.arange(10)) % n).reshape(2000, -1)[:, :n]
    def summaries(dated, *, confidence=False):
        complete, available, valid_events = [], [], []
        sequence = np.full(n, np.nan)
        yearly, regimes = defaultdict(list), defaultdict(list)
        attempted = 0
        for t, values in dated.items():
            attempted += len(values)
            known = [v for v in values if v is not None]
            valid_events.extend(known)
            if known:
                available.append(float(np.mean(known)))
            if values and len(known) == len(values):
                value = float(np.mean(values))
                complete.append(value)
                sequence[t-first] = value
                yearly[market["sessions"][t][:4]].append(value)
                regimes[str(int(context["regime_state"][t]))].append(value)
        result = {"attempted_events": attempted, "valid_events": len(valid_events), "unavailable_events": attempted-len(valid_events),
                  "complete_active_date_log": stats(complete), "available_pair_date_log": stats(available),
                  "event_weighted_log": stats(valid_events), "complete_date_years_log": {k: stats(v) for k,v in yearly.items()},
                  "complete_date_regimes_log": {k: stats(v) for k,v in regimes.items()}}
        if confidence:
            result["paired_equal_date_mean_log_95pct_block_interval"] = bootstrap(sequence, sampled_dates)
        return result
    primary_summary = {policy: {**summaries(dated, confidence=True), "selection": dict(counts[policy]),
                                "overnight_gap_unavailable_to_close_signal": summaries(overnight[policy])}
                       for policy, dated in primary.items()}
    cell_summary = [{"policy": policy, "horizon": h, "timing": timing, **summaries(dated)}
                    for (policy, h, timing), dated in cells.items()]
    assert len(cell_summary) == 90
    assert max(identity_maxima.values()) < 1e-10
    return {"status": "complete_exploratory_timing_diagnostic", "primary": primary_summary, "cells": cell_summary,
            "maximum_log_identity_residuals": identity_maxima, "strategy_cells": 81, "reference_cells": 9,
            "qualification": "Gross overlapping price-event observations; not cash account returns, fills, or profitability qualification."}


def main():
    request = read(ROOT / "request.json")
    source_root = REPO / ".qualification/strategy-interactions20260928"
    assert read(source_root / "status.json")["phase"] == "complete", "Wait for the original54 account worker to complete."
    assert sha(source_root / "request.json") == request["signal_request_sha256"]
    assert sha(source_root / "signals.py") == request["signal_implementation_sha256"]
    assert sha(source_root / "definition.json") == request["signal_definition_sha256"]
    definition = {"request_sha256": sha(ROOT / "request.json"), "script_sha256": sha(Path(__file__)),
                  "plan_sha256": sha(REPO / "docs/strategy-timing-study-2026-09-28.md"),
                  "signal_definition_sha256": request["signal_definition_sha256"],
                  "declared_at": datetime.now(timezone.utc).isoformat()}
    if (ROOT / "execution-definition.json").exists():
        raise RuntimeError("Existing timing attempt preserved; declare a separate resume rather than overwrite it.")
    save(ROOT / "execution-definition.json", definition)
    lock_path = REPO / "data/historical/worker.lock.sqlite"
    lock = sqlite3.connect(lock_path.as_uri()+"?mode=rw", uri=True, timeout=0)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        cache = source_root / "market-signals.joblib"
        manifest = read(source_root / "cache-manifest.json")
        status("verifying_frozen_cache")
        assert sha(cache) == manifest["sha256"]
        assert manifest["definition_sha256"] == request["signal_definition_sha256"]
        market, scores, context = joblib.load(cache, mmap_mode="r")
        save(ROOT / "regime-context.json", {"cache_sha256": manifest["sha256"], "signal_definition_sha256": request["signal_definition_sha256"],
             "state_labels": {"0":"unknown", "1":"continuation", "2":"reversal"},
             "rows": [{"session": session, "state": int(context["regime_state"][i]),
                       "benchmark_above_ma200": bool(context["benchmark_above_ma200"][i]),
                       "volatility20": float(context["benchmark_volatility20"][i]) if np.isfinite(context["benchmark_volatility20"][i]) else None,
                       "prior252_volatility_median": float(context["benchmark_prior252_volatility_median"][i]) if np.isfinite(context["benchmark_prior252_volatility_median"][i]) else None}
                      for i,session in enumerate(market["sessions"])]})
        first = market["sessions"].index(request["first_signal"])
        last = market["sessions"].index(request["last_session"])
        events, needed = select_events(market, scores, request, first, last-6)
        save(ROOT / "selected-cohorts.json", events)
        bars, actions = load_bars(market, needed, request["source_run_id"])
        status("evaluating_paired_timings", planned_events=sum(len(e["selected"]) for e in events))
        result = evaluate(events, bars, actions, market, context, first, last-6)
        result["cache_sha256"] = manifest["sha256"]
        result["request_sha256"] = definition["request_sha256"]
        save(ROOT / "summary.json", result)
        save(ROOT / "artifact-manifest.json", {p.name: sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name not in {"artifact-manifest.json", "status.json"}})
        status("complete", strategy_cells=81, reference_cells=9, primary_paired_contrasts=9)
    finally:
        lock.rollback()
        lock.close()


def self_check():
    # A 10% entry intraday move is captured by open entry regardless of the common exit's units.
    signal = bar_values(99,100,101,98,100,100)
    entry = bar_values(110,121,122,109,121,121)
    exit_ = bar_values(133.1,146.41,147,133,146.41,146.41)
    result = outcomes(signal, entry, exit_)
    np.testing.assert_allclose(result["entry_intraday_log"], math.log(1.1), atol=1e-14)
    np.testing.assert_allclose(result["overnight_log"], math.log(1.1), atol=1e-14)
    assert abs(result["same_exit_identity_residual"]) < 1e-14
    assert abs(result["equal_clock_identity_residual"]) < 1e-14
    shifted_entry = bar_values(110,121,122,109,60.5,60.5)
    shifted = outcomes(signal, shifted_entry, exit_)
    np.testing.assert_allclose(shifted["log_returns"][TIMINGS[0]]-shifted["log_returns"][TIMINGS[1]], math.log(1.1), atol=1e-14)
    malformed = bar_values(200,121,122,109,121,121)
    missing = bar_values(None,121,122,109,121,121)
    for invalid in (malformed, missing):
        value = outcomes(signal, invalid, exit_)
        assert value["log_returns"][TIMINGS[0]] is None
        assert value["log_returns"][TIMINGS[1]] is not None
        assert invalid["open_issue"] is not None
    inconsistent = bar_values(110,121,122,109,121,120)
    assert inconsistent["close_issue"] == "raw_adjusted_close_differs_from_cache"
    return {"status": "passed", "checks": ["same-exit entry timing identity", "equal-clock identity", "overnight gap distinct",
         "later unit-factor cancellation", "missing/out-of-range opens preserve close-only outcome", "cache/source close disagreement rejected"],
         "real_timing_outcomes_computed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Run only after explicit coordinator confirmation and original54 completion.")
    args = parser.parse_args()
    if not args.run:
        print(json.dumps(self_check(), indent=2))
    else:
        try:
            main()
        except Exception as exc:
            status("failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
            raise
