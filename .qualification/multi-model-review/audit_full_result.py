"""Independent saved-report, source-price and cash-ledger audit; never runs research."""

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from frontier.historical_data import read_history
from frontier.historical_settlement import build_settlement_indices

OUT = Path(__file__).resolve().parent
OMITTED = {"equity_curve", "trade_batches", "trade_records", "period_returns", "selection_candidates"}
LEARNED = {"ridge", "extra_trees", "hist_gradient_boosting", "multi_head_mlp", "equal_ensemble", "calibrated_ensemble", "diversified_ensemble"}
FINANCIAL = ("ending_equity", "total_return", "max_drawdown", "cagr", "annualized_volatility")


def read(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save(path, value):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, allow_nan=False, indent=2)


def close(a, b, name, atol=1e-7):
    if a is None or b is None:
        assert a is b, (name, a, b)
    else:
        assert np.allclose(a, b, rtol=1e-9, atol=atol, equal_nan=False), (name, a, b)


def compact_equal(full, brief, path="result"):
    if isinstance(full, dict):
        expected = set(full) - OMITTED
        assert set(brief) - {"monthly_equity_curve"} == expected, (path, "summary keys")
        for key in expected:
            compact_equal(full[key], brief[key], path + "." + key)
        if "monthly_equity_curve" in brief:
            points = full.get("equity_curve", [])
            expected_points = list({point["session"][:7]: point for point in points}.values())
            if points and (not expected_points or points[0] != expected_points[0]):
                expected_points.insert(0, points[0])
            assert brief["monthly_equity_curve"] == expected_points, (path, "sampled chart")
    elif isinstance(full, list):
        assert len(full) == len(brief), (path, "summary length")
        for i, (a, b) in enumerate(zip(full, brief)):
            compact_equal(a, b, path + f"[{i}]")
    else:
        assert full == brief, (path, full, brief)


def key(row):
    return "/".join(str(row.get(name, "")) for name in ("currency", "strategy", "symbol", "horizon", "budget", "cost_bps"))


def calendar_data(result):
    output = {}
    for item in result["coverage"]["markets"]:
        currency = item["currency"]
        cal = xcals.get_calendar("XNYS" if currency == "USD" else "XTSE", start=item["first_session"], end=item["last_session"])
        sessions = cal.sessions.strftime("%Y-%m-%d").tolist()
        assert len(sessions) == item["calendar_sessions"]
        output[currency] = {"sessions": sessions, "index": {s: i for i, s in enumerate(sessions)}, "settlement": build_settlement_indices(sessions, currency)}
    return output


def period_checks(row):
    label = key(row)
    if row["status"] != "complete":
        assert all(row[name] is None for name in FINANCIAL), (label, "incomplete profitability")
        assert not row["yearly"]
        if "trade_metrics" in row:
            assert all(value is None for name, value in row["trade_metrics"].items() if name not in {"completed_trades", "fees"}), (label, "incomplete trade metrics")
            assert row["period_metrics"] == row["period_returns"] == {}
        return
    curve = row["equity_curve"]
    sessions = pd.DatetimeIndex([point["session"] for point in curve])
    equity = np.array([point["equity"] for point in curve])
    cash = np.array([point["cash"] for point in curve])
    assert np.isfinite(equity).all() and np.isfinite(cash).all()
    assert (equity >= cash - 1e-7).all() and (cash >= -1e-7).all()
    close(equity[-1], row["ending_equity"], label + ": final equity")
    close(equity[-1] / row["budget"] - 1, row["total_return"], label + ": total return")
    close(1 - np.min(equity / np.maximum.accumulate(equity)), row["max_drawdown"], label + ": drawdown")
    years = (sessions[-1] - sessions[0]).days / 365.25
    close((equity[-1] / row["budget"]) ** (1 / years) - 1 if years else None, row["cagr"], label + ": CAGR")
    daily = equity[1:] / equity[:-1] - 1
    close(np.std(daily, ddof=1) * np.sqrt(252) if len(daily) > 1 else None, row["annualized_volatility"], label + ": volatility")
    close(np.prod(1 + daily), equity[-1] / equity[0], label + ": daily product")
    previous = row["budget"]
    for year in row["yearly"]:
        indices = np.flatnonzero(sessions.year == int(year["year"]))
        path = np.r_[previous, equity[indices]]
        close(path[-1] / previous - 1, year["return"], label + ": yearly return")
        close(1 - np.min(path / np.maximum.accumulate(path)), year["max_drawdown"], label + ": yearly drawdown")
        previous = path[-1]
    close(np.prod([1 + y["return"] for y in row["yearly"]]), equity[-1] / row["budget"], label + ": yearly product")
    if "period_metrics" not in row:
        return
    iso = sessions.isocalendar()
    groups = {"weekly": [f"{y}-W{w:02}" for y, w in zip(iso.year, iso.week)], "monthly": sessions.strftime("%Y-%m").tolist()}
    for frequency, names in groups.items():
        ends = [i for i in range(len(names)) if i + 1 == len(names) or names[i] != names[i + 1]]
        returns = equity[ends] / np.r_[row["budget"], equity[ends[:-1]]] - 1
        details = row["period_returns"][frequency]
        assert len(details) == len(ends)
        for item, end, change in zip(details, ends, returns):
            assert item["period"] == names[end] and item["last_session"] == str(sessions[end].date())
            close(item["return"], change, label + ": period return")
        stats = row["period_metrics"][frequency]
        assert stats["count"] == len(returns)
        for name, value in {"profitable_fraction": np.mean(returns > 0), "mean_return": np.mean(returns), "median_return": np.median(returns), "worst_return": np.min(returns), "best_return": np.max(returns), "p05_return": np.quantile(returns, .05)}.items():
            close(stats[name], value, label + ": period statistic")
        close(np.prod(1 + returns), equity[-1] / row["budget"], label + ": period product")
    points = np.array([[p[name] for name in ("cash", "settled_cash", "unsettled_cash")] for p in curve])
    assert np.isfinite(points).all() and (points >= -1e-7).all()
    close(points[:, 0], points[:, 1] + points[:, 2], label + ": settlement decomposition")
    metrics = row["trade_metrics"]
    close(equity[-1], row["budget"] + metrics["net_pnl_total"], label + ": realized wealth")
    close(equity[-1], cash[-1], label + ": final flat positions")
    assert row["activity"].get("filled_positions", 0) == metrics["completed_trades"]
    if metrics["completed_trades"]:
        close(metrics["mean_holding_sessions"], row["horizon"], label + ": holding mean")
        assert metrics["max_holding_sessions"] == row["horizon"]


def source_prices(records, calendars, symbols):
    indexed = {record["symbol"]: record for record in records}
    prices = {}
    for count, symbol in enumerate(sorted(symbols), 1):
        record = indexed[symbol]
        normalized = read_history(ROOT / "data/historical/capture-workspace", record)
        cal = calendars[record["spec"]["currency"]]
        values = np.full((len(cal["sessions"]), 2), np.nan)
        offsets = pd.Index(cal["sessions"]).get_indexer(normalized.session)
        keep = offsets >= 0
        values[offsets[keep]] = normalized.loc[keep, ["close", "adjusted_close"]].to_numpy()
        prices[symbol] = values
        if count % 250 == 0:
            print(json.dumps({"stage": "audit_source_prices", "symbols": count}), flush=True)
    return prices


def trade_checks(row, calendar, prices):
    records, label = row.get("trade_records", []), key(row)
    assert len(records) == row["trade_metrics"]["completed_trades"], (label, "audit count")
    entries, exits, settled_proceeds = defaultdict(list), defaultdict(list), defaultdict(float)
    total_pnl = total_fees = 0.0
    for record in records:
        symbol = record["symbol"]
        signal, entry, exit_ = [calendar["index"][record[name]] for name in ("signal_session", "entry_session", "exit_session")]
        assert entry == signal + 1 and exit_ == entry + row["horizon"], (label, "trade timing")
        assert record["holding_sessions"] == row["horizon"]
        assert record["holding_calendar_days"] == (pd.Timestamp(record["exit_session"]) - pd.Timestamp(record["entry_session"])).days
        quantity = record["quantity"]
        assert quantity > 0 and int(quantity) == quantity
        source = prices[symbol]
        close_entry, adjusted_entry = source[entry]
        assert np.isfinite(source[entry : exit_ + 1, 1]).all() and (source[entry : exit_ + 1, 1] > 0).all()
        entry_notional = quantity * close_entry
        exit_notional = entry_notional * source[exit_, 1] / adjusted_entry
        half = row["cost_bps"] / 20000
        close(entry_notional, record["entry_notional"], label + ": nominal entry notional")
        close(exit_notional, record["exit_notional"], label + ": adjusted exit notional")
        close(entry_notional * half, record["entry_fee"], label + ": entry fee")
        close(exit_notional * half, record["exit_fee"], label + ": exit fee")
        close(exit_notional - entry_notional, record["gross_pnl"], label + ": gross PnL")
        pnl = exit_notional * (1 - half) - entry_notional * (1 + half)
        close(pnl, record["net_pnl"], label + ": net PnL")
        close(pnl / entry_notional, record["net_return"], label + ": net return")
        assert record["settlement_index"] == int(calendar["settlement"][exit_]), (label, "settlement date")
        assert any(f["test_start"] <= record["signal_session"] and record["exit_session"] <= f["test_end"] for f in row["folds"]), (label, "trade crosses fold")
        entries[entry].append(record)
        exits[exit_].append(record)
        total_pnl += pnl
        total_fees += record["entry_fee"] + record["exit_fee"]
    if row["status"] != "complete":
        # Open positions at failure are absent from the completed-trade contract.
        return {"completed_records": len(records), "daily_ledger_reconstructed": False, "reason": "Incomplete account can contain unrecorded open positions at failure"}
    close(total_pnl, row["trade_metrics"]["net_pnl_total"], label + ": total trade PnL")
    close(total_fees, row["trade_metrics"]["fees"], label + ": total trade fees")
    cash = settled = float(row["budget"])
    held = {}
    fold_ends = {f["test_end"] for f in row["folds"]}
    for point in row["equity_curve"]:
        day = calendar["index"][point["session"]]
        settled += settled_proceeds.pop(day, 0)
        for record in exits[day]:
            assert held.pop(record["symbol"]) is record
            proceeds = record["exit_notional"] - record["exit_fee"]
            cash += proceeds
            settled_proceeds[record["settlement_index"]] += proceeds
        def marks():
            return sum(r["entry_notional"] * prices[s][day, 1] / prices[s][calendar["index"][r["entry_session"]], 1] for s, r in held.items())
        nav = cash + marks()
        for record in entries[day]:
            assert record["symbol"] not in held and len(held) < 5
            debit = record["entry_notional"] + record["entry_fee"]
            assert debit <= 0.2 * nav + 1e-7, (label, "20 percent entry cap")
            assert debit <= settled + 1e-7, (label, "unsettled cash spent")
            cash -= debit
            settled -= debit
            held[record["symbol"]] = record
            nav -= record["entry_fee"]
        assert min(cash, settled) >= -1e-7
        close(cash + marks(), point["equity"], label + ": reconstructed equity")
        close(cash, point["cash"], label + ": reconstructed cash")
        close(settled, point["settled_cash"], label + ": reconstructed settled cash")
        close(sum(settled_proceeds.values()), point["unsettled_cash"], label + ": reconstructed unsettled cash")
        if point["session"] in fold_ends:
            assert not held, (label, "fold positions not flat")
    assert not held
    return {"completed_records": len(records), "daily_ledger_reconstructed": True, "daily_points": len(row["equity_curve"])}


def reference_checks(row, calendar, prices):
    if row["status"] != "complete":
        return
    curve, budget, symbol = row["equity_curve"], row["budget"], row["symbol"]
    if symbol == "CASH":
        close([p["equity"] for p in curve], budget, key(row) + ": cash reference")
        close(row["fees"], 0, "cash fee")
        return
    entry = calendar["index"][curve[1]["session"]]
    half = row["cost_bps"] / 20000
    quantity = int(np.floor(budget / (prices[symbol][entry, 0] * (1 + half))))
    entry_notional = quantity * prices[symbol][entry, 0]
    free = budget - entry_notional * (1 + half)
    marks = [entry_notional * prices[symbol][calendar["index"][p["session"]], 1] / prices[symbol][entry, 1] for p in curve[1:]] if quantity else [0.0] * (len(curve) - 1)
    expected = np.r_[budget, free + np.array(marks)]
    expected[-1] -= marks[-1] * half
    close(expected, [p["equity"] for p in curve], key(row) + ": source-priced reference")
    close((entry_notional + marks[-1]) * half, row["fees"], key(row) + ": reference fees")


def fold_checks(result, calendars):
    evidence = []
    for currency in calendars:
        folds = [d for d in result["model_diagnostics"] if d["currency"] == currency]
        for number, fold in enumerate(folds):
            positions = {name: calendars[currency]["index"][fold[name]] for name in ("training_start", "training_end", "calibration_start", "calibration_end", "test_start", "test_end")}
            assert positions["training_start"] == 200 + 252 * number
            assert positions["training_end"] - positions["training_start"] + 1 == 504
            assert positions["calibration_start"] == positions["training_end"] + 1
            assert positions["calibration_end"] - positions["calibration_start"] + 1 == 252
            assert positions["test_start"] == positions["calibration_end"] + 1 == 956 + 252 * number
            assert 1 <= positions["test_end"] - positions["test_start"] + 1 <= 252
            for which, max_days, seed in (("fit", 498, 1729 + 2 * number), ("calibration", 246, 1730 + 2 * number)):
                sample = fold[which + "_sample"]
                assert re.fullmatch("[0-9a-f]{64}", sample["sample_sha256"])
                assert sample["seed"] == seed
                assert sample["sample_rows"] == fold[which + "_rows"] <= max_days * 96
                assert sample["eligible_rows"] >= sample["sample_rows"] + sample["excluded_label_rows"] + sample["purged_rows"]
            evidence.append({"currency": currency, "test_start": fold["test_start"], "latest_allowed_fit_signal": calendars[currency]["sessions"][positions["calibration_start"] - 7], "latest_allowed_calibration_signal": calendars[currency]["sessions"][positions["test_start"] - 7], "sample_digests_recorded": True})
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--artifact-dir")
    args = parser.parse_args()
    assert bool(args.run_id) != bool(args.artifact_dir)
    directory = Path(args.artifact_dir).resolve() if args.artifact_dir else ROOT / "artifacts/historical-lab/runs" / args.run_id
    started = time.perf_counter()
    report = {"run_id": args.run_id, "artifact_directory": str(directory), "passed": False, "limitations": ["Corporate-action source normalization is shared with the frozen loader; the independent audit validates arithmetic, not completeness of provider actions.", "Sample digests and calendar purge constraints are checked, but exact training membership is not reconstructed without the full feature matrices.", "Incomplete accounts retain completed trades only; open positions at failure prevent full independent daily-ledger reconstruction for those accounts."]}
    try:
        print(json.dumps({"stage": "audit_load", "bytes": (directory / "result.json").stat().st_size}), flush=True)
        full, brief = read(directory / "result.json"), read(directory / "summary.json")
        compact_equal(full, brief)
        report["full_and_compact_exactly_match"] = True
        del brief
        definition, records = read(directory / "definition.json"), read(directory / "capture-index.json")
        digest = hashlib.sha256((directory / "capture-index.json").read_bytes()).hexdigest()
        if args.run_id:
            from frontier.historical_lab import _identity
            assert full["definition"] == definition
            assert definition["code_identity"] == _identity(), "Frozen source identity differs from current financial source"
            report["frozen_code_identity_verified"] = definition["code_identity"]
        if "capture_index_sha256" in definition:
            assert digest == definition["capture_index_sha256"]
        specs = {s["symbol"]: s for s in definition["instruments"]}
        assert len({r["symbol"] for r in records}) == len(records)
        raw_bytes = 0
        for count, record in enumerate(records, 1):
            assert record["spec"] == specs[record["symbol"]]
            path = (ROOT / "data/historical/capture-workspace" / record["path"]).resolve()
            assert path.is_relative_to(ROOT / "data/historical/capture-workspace/data/scanner/raw")
            with path.open("rb") as handle:
                assert hashlib.file_digest(handle, "sha256").hexdigest() == record["sha256"]
            raw_bytes += path.stat().st_size
        report.update(raw_files_verified=len(records), raw_bytes_verified=raw_bytes, capture_index_sha256=digest)
        calendars = calendar_data(full)
        row_keys = [key(row) for row in full["portfolios"]]
        assert len(row_keys) == len(set(row_keys))
        expected_count = 20 * 3 * len(full["methodology"]["budgets"]) * 3 * len(calendars)
        assert len(row_keys) == expected_count
        assert len(full["benchmarks"]) == 2 * len(full["methodology"]["budgets"]) * 3 * len(calendars)
        assert len({key(row) for row in full["benchmarks"]}) == len(full["benchmarks"])
        audited = [row for row in full["portfolios"] if row["audit_retained"]]
        for row in full["portfolios"]:
            expected_audit = row["strategy"] in LEARNED and row["budget"] == 2000 and row["cost_bps"] == 40
            assert row["audit_retained"] == expected_audit
            if not expected_audit:
                assert "trade_records" not in row
        assert len(audited) == 7 * 3 * len(calendars)
        for count, row in enumerate(full["portfolios"] + full["benchmarks"], 1):
            period_checks(row)
        report.update(portfolios_verified=len(row_keys), references_verified=len(full["benchmarks"]), portfolio_statuses=dict(Counter(row["status"] for row in full["portfolios"])), audit_accounts=len(audited))
        report["fold_boundary_checks"] = fold_checks(full, calendars)
        symbols = {record["symbol"] for row in audited for record in row.get("trade_records", [])} | {r["symbol"] for r in full["benchmarks"] if r["symbol"] != "CASH"}
        prices = source_prices(records, calendars, symbols)
        report["source_price_symbols_reconstructed"] = len(prices)
        report["audited_accounts"] = []
        for count, row in enumerate(audited, 1):
            checked = trade_checks(row, calendars[row["currency"]], prices)
            report["audited_accounts"].append({"account": key(row), "status": row["status"], **checked})
            if count % 10 == 0:
                print(json.dumps({"stage": "audit_ledgers", "accounts": count}), flush=True)
        for row in full["benchmarks"]:
            reference_checks(row, calendars[row["currency"]], prices)
        report.update(detailed_trades_verified=sum(r["completed_records"] for r in report["audited_accounts"]), daily_ledgers_reconstructed=sum(r["daily_ledger_reconstructed"] for r in report["audited_accounts"]), passed=True)
    except Exception as exc:
        report["failure"] = repr(exc)
        raise
    finally:
        report["elapsed_seconds"] = time.perf_counter() - started
        destination = OUT / (f"full-audit-{args.run_id}.json" if args.run_id else "smoke-auditor-self-check.json")
        save(destination, report)
        print(json.dumps({name: value for name, value in report.items() if name not in {"fold_boundary_checks", "audited_accounts", "limitations"}}), flush=True)


if __name__ == "__main__":
    main()
