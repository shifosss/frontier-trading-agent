"""Describe every saved learned USD account at the fixed40bps scenario; no refit."""
from collections import Counter
from pathlib import Path
import hashlib
import json

from frontier.historical_lab import _save

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/summary.json"
FAMILIES = {"ridge", "extra_trees", "hist_gradient_boosting", "multi_head_mlp",
            "equal_ensemble", "calibrated_ensemble", "diversified_ensemble"}


def main():
    raw = SOURCE.read_bytes()
    source = json.loads(raw)
    accounts = [p for p in source["portfolios"] if p["currency"] == "USD"
                and p["budget"] in (2000, 10000) and p["cost_bps"] == 40
                and p["strategy"] in FAMILIES]
    assert len(accounts) == 42
    keys = ("currency", "budget", "cost_bps", "strategy", "horizon", "status", "missing",
            "fees", "trades", "first_session", "last_session", "ending_equity",
            "total_return", "max_drawdown", "cagr", "period_metrics", "yearly")
    report = {"source": str(SOURCE.relative_to(REPO)), "source_sha256": hashlib.sha256(raw).hexdigest(),
              "method": "Post-hoc descriptive re-read of all seven learned/ensemble families, three horizons, two USD balances at40bps; no strategy selection, refit or new account run.",
              "limitations": ["The40bps scenario is a sensitivity, not verified full broker costs.",
                              "Current-member and revised-price source limits persist.",
                              "Weekly target-hit rates and losing streaks cannot be recovered from summary aggregates and are not invented.",
                              "Arithmetic mean weekly return differs from compounded growth.",
                              "Returns cover the entire multi-year account path, not one week."],
              "accounts": [{key: p.get(key) for key in keys} for p in accounts], "by_capital": {}}
    for budget in (2000, 10000):
        selected = [p for p in accounts if p["budget"] == budget]
        complete = [p for p in selected if p["status"] == "complete"]
        weekly = [p["period_metrics"]["weekly"] for p in complete]
        report["by_capital"][str(budget)] = {
            "status_counts": dict(Counter(p["status"] for p in selected)),
            "positive_full_path_accounts": sum(p["total_return"] > 0 for p in complete),
            "within_30pct_observed_drawdown": sum(p["max_drawdown"] <= .3 for p in complete),
            "full_path_return_range": [min(p["total_return"] for p in complete), max(p["total_return"] for p in complete)],
            "mean_weekly_return_range": [min(p["mean_return"] for p in weekly), max(p["mean_return"] for p in weekly)],
            "median_weekly_return_range": [min(p["median_return"] for p in weekly), max(p["median_return"] for p in weekly)],
            "accounts_with_mean_weekly_return_at_least_5pct": sum(p["mean_return"] >= .05 for p in weekly)}
    _save(Path(__file__).parent / "capital-comparison.json", report)
    print(json.dumps(report["by_capital"]))


if __name__ == "__main__":
    main()
