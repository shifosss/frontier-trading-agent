"""Independent economic readout; never changes fitted models or running policies."""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_CEILING
import csv
import hashlib
import json
from pathlib import Path
import runpy

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PRIOR = ROOT.parent / "strategy-interactions20260928/economic_analysis.py"
ACTION_EVENTS = ROOT.parent / "strategy-action-attribution20260928/matched-event-definitions.json"
helpers = runpy.run_path(str(PRIOR))
check = helpers["check"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fee(q, notional, side, profile):
    """Independent Decimal calculation of the frozen scenario, not actual broker fills."""
    amount, shares = Decimal(str(notional)), Decimal(q)
    result = amount * Decimal("0.002")
    if profile == "moomoo_ca_us":
        rates = ("0.0005", "0.0005") if amount < shares else ("0.0049", "0.005")
        for minimum, rate in zip(("0.99", "1.00"), rates, strict=True):
            result += max(Decimal(minimum), shares * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        if side == "sell":
            result += max(Decimal("0.01"), amount * Decimal("0.0000206")).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    return float(result)


def main():
    request = read(ROOT / "request.json")
    assert read(ROOT / "status.json")["phase"] == "complete", "Preserve incomplete study; no full-result claim"
    summary = read(ROOT / "summary.json")
    hashes = read(ROOT / "result-hashes.json")
    assert summary["request"] == request
    market, _ = joblib.load(ROOT / "preparation/market-features.joblib", mmap_mode="r")
    forecast_path = ROOT / "corrected-forecasts.npy"
    assert sha(forecast_path) == summary["forecast_identity"]
    forecasts = np.load(forecast_path, mmap_mode="r")
    source_hashes = {r["symbol"]: r["sha256"] for r in read(ROOT / "preparation/source-evidence.json")["source_hashes"]}
    events = defaultdict(list)
    for event in read(ACTION_EVENTS):
        assert source_hashes[event["symbol"]] == event["source_sha256"]
        events[event["symbol"]].append(event)
    session_index = {value: i for i, value in enumerate(market["sessions"])}
    symbol_index = {value: j for j, value in enumerate(market["symbols"])}
    benchmark = pd.Series(market["adjusted"][:, market["benchmark"]])
    rv = benchmark.pct_change(fill_method=None).rolling(20).std(ddof=1) * np.sqrt(252)
    high_vol = rv > rv.shift(1).rolling(252).median()
    trend = benchmark > benchmark.rolling(200).mean()
    context = {
        "state_labels": {"0": "below_ma200_lower_vol", "1": "above_ma200_lower_vol", "2": "below_ma200_higher_vol", "3": "above_ma200_higher_vol"},
        "rows": [{"session": day, "state": int(trend.iloc[i]) + 2 * int(high_vol.iloc[i])}
                 for i, day in enumerate(market["sessions"]) if day >= request["first_signal"]],
    }
    rows, checked_trades = [], 0
    for policy in request["policies"]:
        for hold in request["holding_sessions"]:
            for profile in request["cost_profiles"]:
                path = ROOT / "accounts" / f"{policy}-{hold}-{profile}.json"
                assert sha(path) == hashes[path.name]
                report = read(path)
                assert (report["policy"], report["horizon"], report["cost_profile"]) == (policy, hold, profile)
                assert report["definition_sha256"] == summary["definition_sha256"]
                row = helpers["account_readout"](report, request["capital_usd"])
                if row["economic_metrics_valid"]:
                    row["observed_regime_context"] = helpers["regime_readout"](report, context)
                    for point in report["equity_curve"]:
                        assert point["settled_cash"] >= -1e-7
                        check(point["cash"], point["settled_cash"] + point["unsettled_cash"], "cash components")
                    reference_error = fill_error = 0.0
                    crossings = []
                    for trade in report["trade_records"]:
                        i, entry, end = (session_index[trade[k]] for k in ("signal_session", "entry_session", "exit_session"))
                        j, q = symbol_index[trade["symbol"]], trade["quantity"]
                        assert isinstance(q, int) and q > 0 and entry == i + 1 and end == entry + hold
                        notional = q * float(market["close"][entry, j])
                        sale = notional * float(market["adjusted"][end, j] / market["adjusted"][entry, j])
                        check(notional, trade["entry_notional"], "source entry notional")
                        check(sale, trade["exit_notional"], "source adjusted exit notional")
                        check(fee(q, trade["entry_notional"], "buy", profile), trade["entry_fee"], "Decimal buy fee")
                        check(fee(q, trade["exit_notional"], "sell", profile), trade["exit_fee"], "Decimal sell fee")
                        crossed = [e for e in events[trade["symbol"]] if trade["entry_session"] < e["effective_session"] <= trade["exit_session"]]
                        if crossed:
                            crossings.append({"symbol": trade["symbol"], "signal_session": trade["signal_session"],
                                              "entry_session": trade["entry_session"], "exit_session": trade["exit_session"],
                                              "net_pnl": trade["net_pnl"], "events": [e["event_id"] for e in crossed],
                                              "flags": sorted({flag for e in crossed for flag in e["flags"]})})
                        if policy != "static_setup_rank":
                            assert "conditional" in trade, "Learned trade is missing its frozen projection"
                        if "conditional" in trade:
                            condition = trade["conditional"]
                            reference, filled = condition["reference_projection"], condition["fill_projection"]
                            assert filled["quantity"] == q <= reference["quantity"]
                            assert (reference["mu"], reference["downside"]) == (filled["mu"], filled["downside"])
                            head = request["holding_sessions"].index(hold)
                            assert (reference["mu"], reference["downside"]) == (forecasts[i, j, head], forecasts[i, j, head + 3])
                            check(reference["price"], float(market["close"][i, j]), "signal source price")
                            check(reference["notional"], reference["quantity"] * reference["price"], "signal source notional")
                            check(filled["price"], float(market["close"][entry, j]), "fill source price")
                            check(filled["notional"], trade["entry_notional"], "fill ledger notional")
                            for key in ("reference_projection", "fill_projection"):
                                p = condition[key]
                                assert p["reason"] == "eligible" and p["utility"] > 0 and p["downside"] >= 0
                                buy = fee(p["quantity"], p["notional"], "buy", profile)
                                sell = fee(p["quantity"], p["notional"] * (1 + p["mu"]), "sell", profile)
                                check(buy, p["entry_fee"], "projected buy fee")
                                check(sell, p["exit_fee"], "projected sell fee")
                                check(p["projected_exit_notional"], p["notional"] * (1 + p["mu"]), "projected exit notional")
                                check(p["notional"] * (p["mu"] - .5 * p["downside"]) - buy - sell, p["utility"], "projected utility")
                                check(p["utility"] / p["notional"], p["utility_fraction"], "projected utility fraction")
                            actual_fees = trade["entry_fee"] + trade["exit_fee"]
                            check(condition["realized_minus_reference_projected_fees"], actual_fees - reference["entry_fee"] - reference["exit_fee"], "reference fee error")
                            check(condition["realized_minus_fill_projected_fees"], actual_fees - filled["entry_fee"] - filled["exit_fee"], "fill fee error")
                            reference_error += condition["realized_minus_reference_projected_fees"]
                            fill_error += condition["realized_minus_fill_projected_fees"]
                        checked_trades += 1
                    row["projected_fee_error_totals"] = {"reference": reference_error, "fill": fill_error}
                    absolute_pnl = sum(abs(t["net_pnl"]) for t in report["trade_records"])
                    row["provider_split_labelled_crossings"] = {
                        "trades": len(crossings), "net_pnl": sum(t["net_pnl"] for t in crossings),
                        "absolute_pnl_share": sum(abs(t["net_pnl"]) for t in crossings) / absolute_pnl if absolute_pnl else None,
                        "known_issue_trades": sum("known_source_issue_union" in t["flags"] for t in crossings),
                        "known_issue_net_pnl": sum(t["net_pnl"] for t in crossings if "known_source_issue_union" in t["flags"]),
                        "records": crossings,
                    }
                row["artifact"] = path.relative_to(REPO).as_posix()
                row["sha256"] = hashes[path.name]
                reference = summary["references"][profile]
                row["spy_total_return"] = reference.get("total_return")
                row["ending_equity_minus_spy"] = row["ending_equity"] - reference["ending_equity"] if row["economic_metrics_valid"] and reference.get("ending_equity") is not None else None
                rows.append(row)
    assert len(rows) == request["planned_accounts"] == 18
    by_id = {(r["policy"], r["horizon"], r["cost_profile"]): r for r in rows}
    pairs = []
    for new, control in (("conditional_net_fraction", "static_setup_rank"), ("conditional_net_dollars", "conditional_net_fraction")):
        for hold in request["holding_sessions"]:
            for profile in request["cost_profiles"]:
                a, b = by_id[new, hold, profile], by_id[control, hold, profile]
                valid = a["economic_metrics_valid"] and b["economic_metrics_valid"]
                pairs.append({"policy": new, "control": control, "horizon": hold, "cost_profile": profile, "valid_pair": valid,
                              "deltas": {k: a[k] - b[k] if a[k] is not None and b[k] is not None else None for k in ("ending_equity", "total_return", "max_drawdown", "net_expectancy_usd", "completed_trades", "mean_exposure_fraction")} if valid else None})
    valid = [r for r in rows if r["economic_metrics_valid"]]
    result = {
        "study": request["study"], "definition_sha256": summary["definition_sha256"],
        "analysis_files": {str(p.relative_to(REPO)): sha(p) for p in (Path(__file__), PRIOR, ACTION_EVENTS)},
        "scope": {"planned_accounts": 18, "complete_accounts": len(valid), "failed_or_incomplete_accounts": 18 - len(valid),
                  "positive_accounts": sum(r["net_pnl"] > 0 for r in valid), "zero_trade_accounts": sum(r["completed_trades"] == 0 for r in valid),
                  "positive_with_drawdown_at_most_30_percent": sum(r["positive_and_drawdown_within_30_percent"] for r in valid),
                  "checked_trade_observations": checked_trades, "statuses": dict(Counter(r["status"] for r in rows))},
        "accounts": rows, "paired_comparisons": pairs, "references": summary["references"],
        "limitations": request["limitations"] + ["Arithmetic/source-array checks do not resolve source corporate actions.", "Provider split-labelled event crossings are not an ordinary-dividend/full-action audit or proof of clean signal lookbacks; no corrected account is constructed.", "Regime and concentration partitions are descriptive attribution, not independent account reruns.", "Low exposure or cash preservation alone does not establish a profitable strategy."],
    }
    (ROOT / "economic-results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    columns = ["policy", "horizon", "cost_profile", "status", "ending_equity", "total_return", "max_drawdown", "net_pnl", "gross_pnl", "fees", "completed_trades", "net_expectancy_usd", "net_expectancy_trade_return", "mean_exposure_fraction", "annualized_turnover", "ending_equity_minus_spy"]
    with (ROOT / "economic-results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({k: row.get(k) for k in columns} for row in rows)
    print(json.dumps({"scope": result["scope"], "pairs": pairs}), flush=True)


if __name__ == "__main__":
    main()
