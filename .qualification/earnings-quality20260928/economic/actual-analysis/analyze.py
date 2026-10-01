"""Read-only economic analysis of one completed immutable study; writes new analysis artifacts only."""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ATTEMPT = HERE.parent / "attempts/7487019bf15a4eb89e1a3702f5a0f7fb"
REPO = HERE.parents[2]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)

def fraction(value):
    return Decimal(str(value))

def weeks_from_curve(account):
    groups = []
    for point in account["equity_curve"]:
        year, week, _ = date.fromisoformat(point["session"]).isocalendar()
        name = f"{year}-W{week:02}"
        if not groups or groups[-1]["period"] != name:
            groups.append({"period": name, "first_session": point["session"], "sessions": []})
        groups[-1]["sessions"].append(point["session"])
        groups[-1]["last_session"] = point["session"]
        groups[-1]["ending_equity"] = point["equity"]
    previous = fraction(account["starting_capital"])
    for row in groups:
        equity = fraction(row.pop("ending_equity"))
        row["return"] = float(equity / previous - 1)
        previous = equity
        row["overlaps_entry_period"] = any("2021-01-01" <= day <= "2025-12-31" for day in row["sessions"])
    original = account["period_returns"]["weekly"]
    assert len(groups) == len(original)
    assert len({row["period"] for row in groups}) == len(groups)
    for computed, saved in zip(groups, original, strict=True):
        assert computed["period"] == saved["period"]
        assert computed["last_session"] == saved["last_session"]
        assert abs(computed["return"] - saved["return"]) < 3e-15
    return groups

def weekly_summary(rows):
    values = [row["return"] for row in rows]
    longest = streak = 0
    for value in values:
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    return {"weeks": len(rows), "idle": sum(value == 0 for value in values),
            "losing": sum(value < 0 for value in values), "winning": sum(value > 0 for value in values),
            "median": statistics.median(values), "worst": min(values), "best": max(values),
            "longest_losing_streak": longest,
            "targets": {str(target): {"hits": sum(value >= target for value in values), "denominator": len(values)}
                        for target in (.05, .10, .15)}}

def analyze_account(account):
    trades = account["trade_records"]
    by_symbol = defaultdict(float)
    for trade in trades:
        by_symbol[trade["symbol"]] += trade["net_pnl"]
    net = sum(fraction(trade["net_pnl"]) for trade in trades)
    gross = sum(fraction(trade["gross_pnl"]) for trade in trades)
    fees = sum(fraction(trade["entry_fee"]) + fraction(trade["exit_fee"]) for trade in trades)
    assert abs(gross - fees - net) < Decimal("0.000001")
    assert abs(net - (fraction(account["ending_equity"]) - fraction(account["starting_capital"]))) < Decimal("0.000001")
    assert abs(fees - fraction(account["fees"])) < Decimal("0.000001")
    assert not account["final_state"]["held"] and not account["final_state"]["pending"]
    weeks = weeks_from_curve(account)
    full = weekly_summary(weeks)
    entry = weekly_summary([row for row in weeks if row["overlaps_entry_period"]])
    assert full["weeks"] == account["weekly_objective"]["count"]
    assert full["longest_losing_streak"] == account["weekly_objective"]["longest_losing_streak"]
    assert all(full["targets"][target]["hits"] == account["weekly_objective"]["targets"][target]["hits"]
               for target in full["targets"])
    sorted_symbols = sorted(by_symbol.items(), key=lambda row: (-row[1], row[0]))
    gross_winning_symbols = sum(max(value, 0) for value in by_symbol.values())
    best = sorted_symbols[0] if sorted_symbols else None
    selected = Counter(row["status"] for row in account["event_decisions"])
    policy_reasons = Counter(decision["reason"] for row in account.get("policy_audit", [])
                             if row["phase"] == "full_selection" for decision in row["decisions"])
    return {key: account[key] for key in ("recipe", "starting_capital", "cost_profile", "status",
            "total_return", "ending_equity", "max_drawdown", "trades", "fees", "yearly", "trade_metrics", "activity")} | {
        "net_pnl": float(net), "gross_pnl": float(gross), "qualification_drawdown_breach": account["max_drawdown"] > .30,
        "weekly_full": full, "weekly_entry_overlap": entry, "weekly_verified_series": weeks,
        "event_dispositions": dict(selected), "planner_decision_reasons": dict(policy_reasons),
        "intent_count": len(account["intents"]), "issuer_net_pnl": sorted_symbols,
        "best_issuer": best, "best_issuer_share_of_net_profit": best[1]/float(net) if best and net > 0 else None,
        "best_issuer_share_of_positive_issuer_pnl": best[1]/gross_winning_symbols if best and gross_winning_symbols else None,
        "top_five_trades": sorted([{key: trade[key] for key in
            ("symbol", "event_id", "entry_session", "exit_session", "net_pnl", "gross_pnl")} for trade in trades],
            key=lambda row: -row["net_pnl"])[:5],
        "bottom_five_trades": sorted([{key: trade[key] for key in
            ("symbol", "event_id", "entry_session", "exit_session", "net_pnl", "gross_pnl")} for trade in trades],
            key=lambda row: row["net_pnl"])[:5]}

def analyze():
    completion = read(ATTEMPT/"completion.json")
    assert completion["status"] == "complete"
    identities = {"completion.json": sha(ATTEMPT/"completion.json")}
    for name, digest in completion["outputs"].items():
        actual = sha(ATTEMPT/name)
        assert actual == digest, name
        identities[name] = actual
    model_attempts = read(ATTEMPT/"models/model-attempts.json")
    diagnostics = read(ATTEMPT/"models/diagnostics.json")
    accounts = [analyze_account(read(ATTEMPT/"accounts"/
                f'{row["recipe"]}-{row["starting_capital"]}-{row["cost_profile"]}.json'))
                for row in read(ATTEMPT/"accounts/summary.json")]
    error_table = []
    for row in diagnostics:
        for head, value in row["heads"].items():
            raw, corrected = value["raw"], value["corrected"]
            base = corrected["training_mean_on_same_rows"]
            error_table.append({"family": row["family"], "test_year": row["year"], "head": head,
                "count": corrected["count"], "raw": {key:raw[key] for key in ("mae","mse","mean_error")},
                "corrected": {key:corrected[key] for key in ("mae","mse","mean_error")},
                "fit_mean": base, "corrected_mse_beats_fit_mean": corrected["mse"] < base["mse"],
                "corrected_mae_beats_fit_mean": corrected["mae"] < base["mae"],
                "corrected_mse_beats_raw": corrected["mse"] < raw["mse"],
                "corrected_bins": corrected["bins"], "calibration_only_edges": corrected["calibration_only_edges"]})
    aggregate = []
    for family in ("ridge", "hist_gradient_boosting"):
        for head in ("return_5", "downside_5"):
            subset = [row for row in error_table if row["family"] == family and row["head"] == head]
            count = sum(row["count"] for row in subset)
            aggregate.append({"family": family, "head": head, "count": count,
                 **{layer:{metric:sum(row[layer][metric]*row["count"] for row in subset)/count
                           for metric in ("mae","mse","mean_error")} for layer in ("raw","corrected","fit_mean")},
                 "years_corrected_beats_fit_mean_mse":sum(row["corrected_mse_beats_fit_mean"] for row in subset),
                 "years_corrected_beats_fit_mean_mae":sum(row["corrected_mae_beats_fit_mean"] for row in subset),
                 "years_corrected_beats_raw_mse":sum(row["corrected_mse_beats_raw"] for row in subset)})
    metadata = {}
    clustering = {}
    for year in range(2021, 2026):
        clustering[str(year)] = read(ATTEMPT/f"models/{year}/test-event-clustering.json")
        metadata[str(year)] = {}
        for family in ("ridge","hist_gradient_boosting"):
            info = read(ATTEMPT/f"models/{year}/{family}/metadata.json")
            forecast = read(ATTEMPT/f"models/{year}/{family}/forecasts.json")
            metadata[str(year)][family] = {
                "calibration_bias":info["audit"]["calibration"]["bias"],"training_mean":info["training_mean"],
                "prediction_warnings":forecast["warnings"],"prediction_error":forecast.get("error"),
                "dispositions":{part:dict(Counter(row["status"] for row in info["audit"]["row_dispositions"]
                                               if row["partition"] == part)) for part in ("fit","calibration","test","outside","unassigned")}}
    result = {"status":"complete_read_only_analysis","created_at":datetime.now(timezone.utc).isoformat(),
              "attempt":str(ATTEMPT),"definition_sha256":completion["definition_sha256"],
              "source_outputs_verified":identities,"model_attempts":model_attempts,
              "model_metadata":metadata,"per_year_head_errors_and_bins":error_table,
              "pooled_head_errors":aggregate,"clustering":clustering,
              "denominators":read(ATTEMPT/"denominators.json"),"accounts":accounts,
              "references":read(ATTEMPT/"references.json"),
              "interpretation":"Computational completion and exploratory historical economics; no promotion, economic qualification, broker execution or profitability guarantee"}
    write(HERE/"report.json",result)
    print(json.dumps({"accounts":len(accounts),"positive":sum(row["net_pnl"]>0 for row in accounts),
          "total_trades":sum(row["trades"] for row in accounts),"pool":aggregate,
          "model_metadata":metadata,
          "account_compact":[{k:row[k] for k in ("recipe","starting_capital","cost_profile","gross_pnl","net_pnl",
          "trades","best_issuer","best_issuer_share_of_net_profit","event_dispositions","planner_decision_reasons")}
          |{"exposure":row["trade_metrics"]["mean_exposure_fraction"],"weekly":row["weekly_full"],
            "entry_week_count":row["weekly_entry_overlap"]["weeks"],"yearly":row["yearly"]} for row in accounts]},indent=2))

if __name__ == "__main__":
    analyze()
