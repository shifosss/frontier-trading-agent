"""Independent read-only audit of a completed daily short-horizon experiment."""
import argparse
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

OMIT = {"equity_curve", "trade_batches", "trade_records", "period_returns", "selection_candidates", "monthly_equity_curve"}
CODE_FILES = ("historical_lab.py", "historical_data.py", "historical_study.py", "short_horizon_study.py", "historical_settlement.py", "strategy_study.py", "research_lab.py", "scan_data.py")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def compact(value):
    if isinstance(value, dict):
        return {key: compact(item) for key, item in value.items() if key not in OMIT}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def array_rows(path, key):
    needle = '"' + key + '":['
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8") as handle:
        buffer = ""
        while needle not in buffer:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                raise ValueError(f"Array {key} absent in {path}")
            buffer = buffer[-len(needle):] + chunk
        buffer = buffer.split(needle, 1)[1]
        while True:
            buffer = buffer.lstrip(" ,\r\n")
            if buffer.startswith("]"):
                return
            try:
                row, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    raise
                buffer += chunk
                continue
            yield row
            buffer = buffer[end:]


def close(actual, expected, context):
    if not np.allclose(actual, expected, rtol=1e-10, atol=1e-7, equal_nan=True):
        error = np.nanmax(np.abs(np.asarray(actual) - np.asarray(expected)))
        raise AssertionError(f"{context}: maximum error {error}")


def independent_settlement_dates(currency, first, last):
    name = "XNYS" if currency == "USD" else "XTSE"
    calendar = xcals.get_calendar(name, start=first, end=pd.Timestamp(last) + pd.Timedelta(days=32))
    dates = calendar.sessions
    if currency == "USD":
        holidays = set(USFederalHolidayCalendar().holidays(dates[0], dates[-1]))
        # Federal Reserve does not observe Saturday holidays on the prior Friday.
        for year in range(dates[0].year, dates[-1].year + 2):
            for month, day in ((1,1),(6,19),(7,4),(11,11),(12,25)):
                holiday = pd.Timestamp(year, month, day)
                if holiday.weekday() == 5:
                    holidays.discard(holiday - pd.Timedelta(days=1))
    else:
        holidays = set()
        for year in range(dates[0].year, dates[-1].year + 1):
            for month, day in ((9,30),(11,11)):
                if month == 9 and year < 2021:
                    continue
                holiday = pd.Timestamp(year, month, day)
                if holiday.weekday() >= 5:
                    holiday += pd.Timedelta(days=7-holiday.weekday())
                holidays.add(holiday)
    available = {}
    for i, sale in enumerate(dates):
        if sale > pd.Timestamp(last):
            break
        t1 = pd.Timestamp("2024-05-28" if currency == "USD" else "2024-05-27")
        left = 1 if sale >= t1 else 2 if sale >= pd.Timestamp("2017-09-05") else 3
        for j in range(i + 1, len(dates)):
            if dates[j] not in holidays:
                left -= 1
                if not left:
                    available[i] = j
                    break
    return available


def object_field(path, key):
    needle = '"' + key + '":'
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8") as handle:
        buffer = ""
        while needle not in buffer:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                raise ValueError(f"Field {key} missing")
            buffer = buffer[-len(needle):] + chunk
        buffer = buffer.split(needle, 1)[1].lstrip()
        while True:
            try:
                return decoder.raw_decode(buffer)[0]
            except json.JSONDecodeError:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    raise
                buffer += chunk


def run(run_id, part=None):
    workspace = Path.cwd()
    root = workspace / "artifacts/historical-lab/runs" / run_id
    source_root = workspace / "src/frontier"
    result_path = root / (f"{part.lower()}-result.json" if part else "result.json")
    definition = json.loads((root / "definition.json").read_text(encoding="utf-8"))
    summary = (json.loads((root / "summary.json").read_text(encoding="utf-8")) if not part else {
        "definition": definition, "capture": {"usable": len(json.loads((root / "capture-index.json").read_text(encoding="utf-8")))},
        "coverage": object_field(result_path, "coverage"),
    })
    records = json.loads((root / "capture-index.json").read_text(encoding="utf-8"))
    assert definition == summary["definition"]
    assert len(records) == summary["capture"]["usable"]
    assert digest(root / "capture-index.json") == definition["capture_index_sha256"]
    identity = hashlib.sha256()
    for name in CODE_FILES:
        identity.update(name.encode())
        identity.update((source_root / name).read_text(encoding="utf-8").encode())
    assert identity.hexdigest() == definition["code_identity"]
    source = definition["source_reuse"]
    original = workspace / "artifacts/historical-lab/runs" / source["run_id"]
    assert digest(original / "definition.json") == source["definition_sha256"]
    assert digest(original / "capture-index.json") == source["capture_index_sha256"]
    assert (root / "capture-index.json").read_bytes() == (original / "capture-index.json").read_bytes()
    original_definition = json.loads((original / "definition.json").read_text(encoding="utf-8"))
    for key in ("frozen_at", "requested_start", "instruments", "universe_sha256", "universe_snapshot"):
        assert definition[key] == original_definition[key]
    print("Code, original input identities and universe/cutoff verified", flush=True)
    capture_root = workspace / "data/historical/capture-workspace"
    def check_raw(record):
        path = (capture_root / record["path"]).resolve()
        assert path.is_relative_to(capture_root / "data/scanner/raw")
        assert digest(path) == record["sha256"], record["symbol"]
        return path.stat().st_size
    with ThreadPoolExecutor(max_workers=4) as pool:
        raw_bytes = sum(pool.map(check_raw, records))
    print(f"Verified {len(records)} raw-source hashes ({raw_bytes:,} bytes)", flush=True)
    by_symbol = {row["symbol"]: row for row in records}
    markets = {}
    for row in summary["coverage"]["markets"]:
        name = "XNYS" if row["currency"] == "USD" else "XTSE"
        calendar = xcals.get_calendar(name, start=row["first_session"], end=row["last_session"])
        sessions = calendar.sessions.strftime("%Y-%m-%d").tolist()
        assert len(sessions) == row["calendar_sessions"]
        markets[row["currency"]] = {"sessions": sessions, "lookup": {day:i for i,day in enumerate(sessions)},
            "settlements": independent_settlement_dates(row["currency"], sessions[0], sessions[-1])}

    @lru_cache(maxsize=1024)
    def prices(symbol):
        record = by_symbol[symbol]
        raw = json.loads((capture_root / record["path"]).read_text(encoding="utf-8"))["chart"]["result"][0]
        dates = pd.to_datetime(raw["timestamp"], unit="s", utc=True).tz_convert("America/Toronto").strftime("%Y-%m-%d")
        quote = raw["indicators"]["quote"][0]
        adjusted = np.asarray(raw["indicators"]["adjclose"][0]["adjclose"], dtype=float)
        nominal = np.asarray(quote["close"], dtype=float)
        captured = pd.Timestamp(record["captured_at"]).tz_convert("America/Toronto").strftime("%Y-%m-%d")
        for event in raw.get("events", {}).get("splits", {}).values():
            effective = pd.Timestamp(event["date"], unit="s", tz="UTC").tz_convert("America/Toronto").strftime("%Y-%m-%d")
            if effective <= captured:
                nominal[dates < effective] *= float(event["numerator"]) / float(event["denominator"])
        market = markets[record["spec"]["currency"]]
        adj = np.full(len(market["sessions"]), np.nan)
        nom = adj.copy()
        positions = pd.Index(market["sessions"]).get_indexer(dates)
        keep = positions >= 0
        adj[positions[keep]] = adjusted[keep]
        nom[positions[keep]] = nominal[keep]
        return adj, nom

    counts, audit_rows, ledgers = Counter(), [], []
    def check_metrics(row, context):
        status = row["status"]
        counts[f"{context.split(':')[0]}:{status}"] += 1
        if status == "complete":
            points = row["equity_curve"]
            equity = np.array([point["equity"] for point in points])
            assert np.isfinite(equity).all() and (equity >= 0).all()
            close(row["ending_equity"], equity[-1], context + " ending wealth")
            close(row["total_return"], equity[-1] / row["budget"] - 1, context + " economic denominator")
            drawdown = 1 - np.min(equity / np.maximum.accumulate(equity))
            close(row["max_drawdown"], drawdown, context + " daily drawdown")
            years = (pd.Timestamp(points[-1]["session"]) - pd.Timestamp(points[0]["session"])).days / 365.25
            if years > 0:
                close(row["cagr"], (equity[-1] / row["budget"]) ** (1 / years) - 1, context + " CAGR")
            for year in row["yearly"]:
                indices = [i for i,p in enumerate(points) if p["session"].startswith(year["year"])]
                before = equity[indices[0] - 1] if indices[0] else row["budget"]
                path = np.r_[before, equity[indices]]
                close(year["return"], path[-1] / before - 1, context + " year return")
                close(year["max_drawdown"], 1 - np.min(path / np.maximum.accumulate(path)), context + " year drawdown")
            audit_rows.append({"context":context,"status":status,"ending_equity":float(equity[-1]),"daily_max_drawdown":float(drawdown)})
        else:
            for key in ("ending_equity", "total_return", "max_drawdown", "cagr", "annualized_volatility"):
                assert row[key] is None, (context, key)
            for key,value in row.get("trade_metrics", {}).items():
                if key not in {"completed_trades", "fees"}:
                    assert value is None, (context, key)
            assert not row.get("period_metrics")
            audit_rows.append({"context":context,"status":status,"missing":row.get("missing")})

    def check_rolling(row, context):
        market = markets[row["currency"]]
        lookup = market["lookup"]
        n = len(market["sessions"])
        cash = np.full(n, row["budget"], dtype=float)
        settled = cash.copy()
        held = np.zeros(n)
        position_counts = np.zeros(n, dtype=int)
        fees = 0.0
        pnl = 0.0
        trade_returns = []
        half_cost = row["cost_bps"] / 20000
        for trade in row["trade_records"]:
            entry, exit_ = lookup[trade["entry_session"]], lookup[trade["exit_session"]]
            signal = lookup[trade["signal_session"]]
            assert entry == signal + 1
            assert exit_ - entry == trade["holding_sessions"] in {1,3,5}
            assert trade["holding_calendar_days"] == (pd.Timestamp(trade["exit_session"]) - pd.Timestamp(trade["entry_session"])).days
            assert trade["settlement_index"] == market["settlements"][exit_]
            adjusted, nominal = prices(trade["symbol"])
            close(trade["entry_notional"], nominal[entry] * trade["quantity"], context + " nominal entry")
            marked = trade["entry_notional"] * adjusted[entry:exit_ + 1] / adjusted[entry]
            assert np.isfinite(marked).all()
            close(trade["exit_notional"], marked[-1], context + " total-return exit")
            close(trade["entry_fee"], trade["entry_notional"] * half_cost, context + " entry fee")
            close(trade["exit_fee"], trade["exit_notional"] * half_cost, context + " exit fee")
            debit = trade["entry_notional"] + trade["entry_fee"]
            credit = trade["exit_notional"] - trade["exit_fee"]
            close(trade["net_pnl"], credit - debit, context + " net trade PnL")
            close(trade["net_return"], (credit - debit) / trade["entry_notional"], context + " trade return")
            cash[entry:] -= debit
            cash[exit_:] += credit
            settled[entry:] -= debit
            settled[trade["settlement_index"]:] += credit
            held[entry:exit_] += marked[:-1]
            position_counts[entry:exit_] += 1
            fees += trade["entry_fee"] + trade["exit_fee"]
            pnl += trade["net_pnl"]
            trade_returns.append(trade["net_return"])
        points = row["equity_curve"]
        indices = [lookup[p["session"]] for p in points]
        assert position_counts.max() <= 5
        complete = row["status"] == "complete"
        if complete:
            close([p["cash"] for p in points], cash[indices], context + " cash ledger")
            close([p["settled_cash"] for p in points], settled[indices], context + " settled ledger")
            close([p["unsettled_cash"] for p in points], (cash - settled)[indices], context + " receivables ledger")
            close([p["equity"] for p in points], (cash + held)[indices], context + " raw-price daily valuation")
            close(row["fees"], fees, context + " total fees")
            close(row["ending_equity"], row["budget"] + pnl, context + " total realized PnL")
            close(row["trade_metrics"]["net_pnl_total"], pnl, context + " expectancy denominator")
            assert cash[indices].min() >= -1e-7 and settled[indices].min() >= -1e-7
            if trade_returns:
                close(row["trade_metrics"]["net_expectancy_return"], np.mean(trade_returns), context + " mean trade return")
            close(np.prod([1 + fold["test_return"] for fold in row["folds"]]), 1 + row["total_return"], context + " fold compounding")
            for previous, following in zip(row["folds"], row["folds"][1:]):
                close(previous["ending_equity"], following["starting_equity"], context + " fold continuity")
            for period in ("weekly", "monthly"):
                close(np.prod([1 + p["return"] for p in row["period_returns"][period]]), 1 + row["total_return"], context + " period compounding")
        else:
            assert row["fees"] + 1e-7 >= fees
        ledgers.append({"context":context,"status":row["status"],"completed_trades_checked":len(row["trade_records"]),"daily_raw_price_ledger_reconstructed":complete,"incomplete_scope":None if complete else "Completed trades verified; open positions at failure are absent from completed-trade audit, so incomplete portfolio ledger is not claimed."})

    for key in ("portfolios", "benchmarks", "walk_forward"):
        seen = 0
        for i,row in enumerate(array_rows(result_path, key)):
            brief = summary[key][i] if not part else None
            if brief is not None:
                assert compact(row) == compact(brief), (key, i, "compact mismatch")
            context = f"{key}:{row['currency']}:{row['budget']}:{row['cost_bps']}:{row.get('strategy', row.get('symbol', 'rolling'))}:{row.get('horizon', '')}"
            check_metrics(row, context)
            if key == "walk_forward":
                reference = {**row["benchmark"], "budget":row["budget"]}
                check_metrics(reference, "rolling_reference:" + context)
                for full, sampled in (((row,brief),(row["benchmark"],brief["benchmark"])) if brief is not None else ()):
                    points = full["equity_curve"]
                    expected = list({p["session"][:7]:p for p in points}.values())
                    if points and expected[0] != points[0]:
                        expected.insert(0,points[0])
                    assert sampled["monthly_equity_curve"] == expected
                check_rolling(row,context)
                print(context + " audited", flush=True)
            seen += 1
        if not part:
            assert seen == len(summary[key])
        print(f"{key}: {seen} account rows verified; compact equivalence={not part}", flush=True)
    # Sources must remain stable throughout this potentially long audit.
    repeated = hashlib.sha256()
    for name in CODE_FILES:
        repeated.update(name.encode())
        repeated.update((source_root / name).read_text(encoding="utf-8").encode())
    assert repeated.hexdigest() == identity.hexdigest()
    assert digest(root / "capture-index.json") == definition["capture_index_sha256"]
    output = {"run_id":run_id,"currency_part":part,"compact_equivalence_checked":part is None,"status":"passed","code_identity":identity.hexdigest(),"source_reuse":source,"declared_instruments":len(definition["instruments"]),"raw_sources_verified":len(records),"raw_bytes_verified":raw_bytes,"counts":dict(counts),"account_checks":audit_rows,"rolling_ledger_checks":ledgers}
    suffix = f"-{part.lower()}" if part else ""
    target = workspace / ".qualification/historical-source-probes" / f"independent-short-horizon-{run_id}{suffix}.json"
    target.write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps({"status":"passed","evidence":str(target),"counts":dict(counts)}),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--part", choices=["USD","CAD"])
    args = parser.parse_args()
    run(args.run_id, args.part)
