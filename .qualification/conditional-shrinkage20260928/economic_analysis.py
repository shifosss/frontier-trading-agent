"""All six calibrated accounts and matched original dollar-ranking controls."""
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "conditional-selection20260928"
spec = importlib.util.spec_from_file_location("source_economic_analysis", SOURCE / "economic_analysis.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
read, sha = source.read, source.sha


def main():
    summary, hashes = read(ROOT / "summary.json"), read(ROOT / "result-hashes.json")
    request = read(ROOT / "request.json")
    assert read(ROOT / "status.json")["phase"] == "complete"
    assert summary["request"] == request
    original = read(SOURCE / "economic-results.json")
    control = {(row["horizon"], row["cost_profile"]): row for row in original["accounts"] if row["policy"] == "conditional_net_dollars"}
    rows, pairs = [], []
    for hold in request["holding_sessions"]:
        for profile in request["cost_profiles"]:
            path = ROOT / "accounts" / f"conditional_shrinkage_dollars-{hold}-{profile}.json"
            assert sha(path) == hashes[path.name]
            report = read(path)
            assert report["definition_sha256"] == summary["definition_sha256"]
            assert report["forecast_identity"] == summary["forecast_identity"]
            row = source.helpers["account_readout"](report, request["capital_usd"])
            old = control[hold, profile]
            valid = row["economic_metrics_valid"] and old["economic_metrics_valid"]
            pairs.append({"horizon": hold, "cost_profile": profile, "valid_pair": valid,
                          "original_artifact": old["artifact"], "original_sha256": old["sha256"],
                          "deltas": {key: row[key] - old[key] if row[key] is not None and old[key] is not None else None
                                     for key in ("ending_equity", "total_return", "max_drawdown", "completed_trades", "net_expectancy_usd", "mean_exposure_fraction")} if valid else None})
            row["artifact"] = path.name
            row["sha256"] = hashes[path.name]
            rows.append(row)
    valid = [row for row in rows if row["economic_metrics_valid"]]
    result = {"definition_sha256": summary["definition_sha256"], "forecast_identity": summary["forecast_identity"],
              "analysis_sha256": sha(Path(__file__)), "original_economic_results_sha256": sha(SOURCE / "economic-results.json"),
              "scope": {"planned_accounts": 6, "complete_accounts": len(valid), "incomplete_accounts": 6-len(valid),
                        "positive_accounts": sum(row["net_pnl"] > 0 for row in valid),
                        "zero_trade_accounts": sum(row["completed_trades"] == 0 for row in valid),
                        "completed_trade_observations": sum(row["completed_trades"] for row in valid)},
              "accounts": rows, "paired_comparisons": pairs, "limitations": request["limitations"]}
    (ROOT / "economic-results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    columns = ["policy", "horizon", "cost_profile", "status", "ending_equity", "total_return", "max_drawdown", "gross_pnl", "fees", "completed_trades", "net_expectancy_usd", "mean_exposure_fraction"]
    with (ROOT / "economic-results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in columns} for row in rows)
    print(json.dumps({"scope": result["scope"], "paired_comparisons": pairs}), flush=True)


if __name__ == "__main__":
    main()
