"""Describe every committed pilot account without selecting or rerunning strategies."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean, median

from frontier.historical_lab import _save

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    pointer = read(ROOT / "completed.json")
    summary_path = ROOT / pointer["summary"]
    attempt = summary_path.parent
    summary = read(summary_path)
    assert len(summary["accounts"]) == summary["planned_accounts"] == 4
    results = []
    for item in summary["accounts"]:
        path = attempt / item["artifact"]
        assert sha(path) == item["sha256"] == pointer["files"][path.relative_to(ROOT).as_posix()]
        account = read(path)
        trades = account.get("trades", [])
        positive = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
        negative = [t["net_pnl"] for t in trades if t["net_pnl"] < 0]
        names = defaultdict(lambda: {"trades": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0})
        for trade in trades:
            row = names[trade["symbol"]]
            row["trades"] += 1
            row["gross_pnl"] += trade["exit_notional"] - trade["entry_notional"]
            row["fees"] += trade["entry_fee"] + trade["exit_fee"]
            row["net_pnl"] += trade["net_pnl"]
        row = {**item, "economic_metrics_valid": item["status"] == "complete",
               "completed_prefix_gross_pnl": sum(x["gross_pnl"] for x in names.values()),
               "completed_prefix_fees": sum(x["fees"] for x in names.values()),
               "completed_prefix_net_pnl": sum(t["net_pnl"] for t in trades),
               "completed_prefix_win_rate": len(positive)/len(trades) if trades else None,
               "completed_prefix_average_win": mean(positive) if positive else None,
               "completed_prefix_average_loss": mean(negative) if negative else None,
               "completed_prefix_profit_factor": -sum(positive)/sum(negative) if negative else None,
               "top_five_share_of_positive_pnl": sum(sorted(positive, reverse=True)[:5])/sum(positive) if positive else None,
               "median_entry_notional": median(t["entry_notional"] for t in trades) if trades else None,
               "by_symbol": dict(names), "yearly": account.get("yearly", []),
               "periods": {}, "reference": account.get("event_reference_summary"),
               "stale_mark_observations": account.get("stale_mark_observations"),
               "max_mark_age_seconds": account.get("max_mark_age_seconds")}
        for period in ["weekly", "monthly", "yearly"]:
            values = [x["return_"] for x in account.get(period, [])]
            row["periods"][period] = {"count": len(values), "positive": sum(x > 0 for x in values),
                                      "negative": sum(x < 0 for x in values), "flat": sum(x == 0 for x in values),
                                      "worst": min(values) if values else None, "best": max(values) if values else None}
        results.append(row)
    report = {"at": datetime.now(timezone.utc).isoformat(), "definition_sha256": pointer["definition_sha256"],
              "source_inputs_sha256": summary["source_inputs_sha256"], "summary_sha256": sha(summary_path),
              "analysis_sha256": sha(Path(__file__)), "accounts": results,
              "limitations": ["All four accounts retained; invalid/failed paths do not supply full-period economic results.",
                              "Gross dollars use actual fee-affected sizes; subtracting fees is not a fee-free account replay.",
                              "Six surviving purposive pilot names and revised provider data, not broad historical membership.",
                              "Sampled marks and declared friction are not realized execution or maximum intrabar loss.",
                              "The event reference is an unfunded gross-return diagnostic, not a funded benchmark."]}
    _save(ROOT / "economic-results.json", report)
    print(json.dumps({"accounts": [{k: row[k] for k in ["arm", "cost_profile", "status", "total_return", "completed_trades", "sampled_mark_max_drawdown", "completed_prefix_gross_pnl", "completed_prefix_fees", "failure"]} for row in results]}, indent=2))


if __name__ == "__main__":
    main()
