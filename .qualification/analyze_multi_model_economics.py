"""Read one saved compact study; compare every account without running financial code.

Outputs stay under .qualification. Run only after the chosen summary is published.
Smoke use validates this analyzer's schema handling, never trading performance.
"""

import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / ".qualification"
LEARNED = {
    "ridge",
    "extra_trees",
    "hist_gradient_boosting",
    "multi_head_mlp",
    "equal_ensemble",
    "calibrated_ensemble",
    "diversified_ensemble",
}
BASE_MODELS = ("ridge", "extra_trees", "hist_gradient_boosting", "multi_head_mlp")
KEY = ("currency", "budget", "cost_bps", "strategy", "horizon")
GROUP = ("currency", "budget", "cost_bps", "horizon")
FINANCIAL = ("ending_equity", "total_return", "max_drawdown", "cagr")


def complete(row):
    return row["status"] == "complete"


def key(row, fields=KEY):
    return tuple(row[field] for field in fields)


def account_id(row):
    return "/".join(map(str, key(row)))


def distribution(values):
    values = [float(value) for value in values if value is not None]
    return {
        "count": len(values),
        "positive": sum(v > 0 for v in values),
        "zero": sum(abs(v) <= 1e-12 for v in values),
        "minimum": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "maximum": max(values) if values else None,
    }


def compounded(values):
    return math.prod(1 + value for value in values) - 1


def check_close(errors, row, label, actual, expected):
    if actual is None or not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-7):
        errors.append(
            {"account": account_id(row), "check": label, "actual": actual, "expected": expected}
        )


def class_summary(rows):
    valid = [row for row in rows if complete(row)]
    return {
        "attempted": len(rows),
        "statuses": dict(Counter(row["status"] for row in rows)),
        "positive": sum(row["total_return"] > 0 for row in valid),
        "negative": sum(row["total_return"] < 0 for row in valid),
        "cash_only": sum(row["trade_metrics"]["completed_trades"] == 0 for row in valid),
        "mean_exposure_below_10pct": sum(
            row["trade_metrics"]["mean_exposure_fraction"] < 0.1 for row in valid
        ),
        "drawdown_above_30pct": sum(row["max_drawdown"] > 0.3 for row in valid),
        "positive_and_drawdown_at_most_30pct": sum(
            row["total_return"] > 0 and row["max_drawdown"] <= 0.3 for row in valid
        ),
        "total_return": distribution(row["total_return"] for row in valid),
        "mean_exposure": distribution(
            row["trade_metrics"]["mean_exposure_fraction"] for row in valid
        ),
    }


def analyze(study):
    rows, benchmarks = study["portfolios"], study["benchmarks"]
    method = study["methodology"]
    currencies = sorted({row["currency"] for row in study["coverage"]["markets"]})
    strategies = list(method["strategies"])
    budgets, costs, horizons = method["budgets"], method["cost_bps"], method["horizons"]
    expected = set(itertools.product(currencies, budgets, costs, strategies, horizons))
    observed = [key(row) for row in rows]
    errors = []
    if len(observed) != len(set(observed)) or set(observed) != expected:
        errors.append(
            {
                "check": "declared_grid",
                "expected": len(expected),
                "observed": len(observed),
                "unique": len(set(observed)),
                "missing": sorted(expected - set(observed)),
                "extra": sorted(set(observed) - expected),
            }
        )
    if not LEARNED <= set(strategies):
        errors.append(
            {"check": "declared_learned_roster", "missing": sorted(LEARNED - set(strategies))}
        )
    benchmark_index = defaultdict(list)
    for row in benchmarks:
        benchmark_index[key(row, ("currency", "budget", "cost_bps"))].append(row)
    ledger, years, folds, comparisons, groups, pairs = [], [], [], [], [], []
    for row in rows:
        valid = complete(row)
        metrics = row["trade_metrics"]
        entry = {field: row[field] for field in KEY}
        entry.update(
            account_id=account_id(row),
            model_class="learned" if row["strategy"] in LEARNED else "rule",
            status=row["status"],
            first_session=row["first_session"],
            last_session=row["last_session"],
            completed_trades=metrics["completed_trades"],
            missing="; ".join(row.get("missing", [])),
            audit_retained=row.get("audit_retained", False),
        )
        entry.update({field: row.get(field) if valid else None for field in FINANCIAL})
        entry.update(
            {
                field: metrics.get(field) if valid else None
                for field in (
                    "net_expectancy_native",
                    "net_expectancy_return",
                    "win_rate",
                    "profit_factor",
                    "annualized_turnover",
                    "mean_exposure_fraction",
                    "mean_settled_cash_fraction",
                    "mean_holding_sessions",
                    "trades_per_week",
                    "net_pnl_total",
                    "fees",
                    "consecutive_losses",
                    "max_drawdown_duration_sessions",
                )
            }
        )
        for period in ("weekly", "monthly"):
            source = row.get("period_metrics", {}).get(period, {}) if valid else {}
            for field in ("count", "profitable_fraction", "worst_return", "median_return"):
                entry[period + "_" + field] = source.get(field)
        candidates = benchmark_index[key(row, ("currency", "budget", "cost_bps"))]
        for kind, matches in (
            ("etf", [b for b in candidates if b["symbol"] != "CASH"]),
            ("cash", [b for b in candidates if b["symbol"] == "CASH"]),
        ):
            if len(matches) != 1:
                errors.append(
                    {
                        "account": account_id(row),
                        "check": kind + "_unique_reference",
                        "found": len(matches),
                    }
                )
                continue
            benchmark = matches[0]
            matched = (
                valid
                and complete(benchmark)
                and all(row[k] == benchmark[k] for k in ("first_session", "last_session"))
            )
            entry[kind + "_comparison_available"] = matched
            entry[kind + "_symbol"] = benchmark["symbol"]
            entry[kind + "_return"] = benchmark["total_return"] if matched else None
            entry[kind + "_excess_total_return"] = (
                row["total_return"] - benchmark["total_return"] if matched else None
            )
            if kind == "etf" and matched:
                bm_years = {r["year"]: r for r in benchmark["yearly"]}
                for yearly in row["yearly"]:
                    bm = bm_years.get(yearly["year"])
                    years.append(
                        {
                            **{field: row[field] for field in KEY},
                            **yearly,
                            "benchmark_return": bm["return"] if bm else None,
                            "excess_return": yearly["return"] - bm["return"] if bm else None,
                        }
                    )
        if valid:
            check_close(
                errors,
                row,
                "ending_equity_return",
                row["ending_equity"],
                row["budget"] * (1 + row["total_return"]),
            )
            check_close(
                errors,
                row,
                "ending_equity_realized_pnl",
                row["ending_equity"],
                row["budget"] + metrics["net_pnl_total"],
            )
            check_close(
                errors, row, "completed_trade_count", metrics["completed_trades"], row["trades"]
            )
            check_close(
                errors,
                row,
                "year_compounding",
                compounded(r["return"] for r in row["yearly"]),
                row["total_return"],
            )
            valid_folds = row.get("folds", [])
            if any(f["test_status"] != "complete" or f["test_return"] is None for f in valid_folds):
                errors.append({"account": account_id(row), "check": "complete_account_failed_fold"})
            else:
                check_close(
                    errors,
                    row,
                    "fold_compounding",
                    compounded(f["test_return"] for f in valid_folds),
                    row["total_return"],
                )
            if metrics["completed_trades"] == 0:
                check_close(errors, row, "zero_trades_preserve_cash", row["total_return"], 0)
                check_close(
                    errors, row, "zero_trades_exposure", metrics["mean_exposure_fraction"], 0
                )
            else:
                check_close(
                    errors,
                    row,
                    "mean_holding_clock",
                    metrics["mean_holding_sessions"],
                    row["horizon"],
                )
            for frequency in ("weekly", "monthly"):
                returns = [p["return"] for p in row.get("period_returns", {}).get(frequency, [])]
                if returns:
                    check_close(
                        errors,
                        row,
                        frequency + "_compounding",
                        compounded(returns),
                        row["total_return"],
                    )
            y = distribution(r["return"] for r in row["yearly"])
            f = distribution(f["test_return"] for f in valid_folds)
            entry.update(
                year_count=y["count"],
                positive_years=y["positive"],
                worst_year=y["minimum"],
                median_year=y["median"],
                fold_count=f["count"],
                positive_folds=f["positive"],
                worst_fold=f["minimum"],
                median_fold=f["median"],
            )
        else:
            if (
                any(row.get(field) is not None for field in FINANCIAL)
                or metrics.get("net_expectancy_native") is not None
                or row.get("period_metrics")
            ):
                errors.append(
                    {"account": account_id(row), "check": "incomplete_profitability_not_suppressed"}
                )
        for fold in row.get("folds", []):
            folds.append(
                {
                    **{field: row[field] for field in KEY},
                    "account_status": row["status"],
                    "prefix_only_not_full_performance": not valid,
                    **fold,
                }
            )
        ledger.append(entry)
        comparisons.append(
            {
                "account_id": account_id(row),
                "status": row["status"],
                "year_summary": distribution(r["return"] for r in row["yearly"]) if valid else None,
                "profit_concentration_top_bottom_only": row.get("profit_concentration")
                if valid
                else None,
                "activity": row.get("activity", {}),
            }
        )
    indexed = {key(row): row for row in ledger}
    for group_key, selected in itertools.groupby(
        sorted(rows, key=lambda r: key(r, GROUP)), key=lambda r: key(r, GROUP)
    ):
        selected = list(selected)
        group = dict(zip(GROUP, group_key))
        for name, subset in (
            ("learned", [r for r in selected if r["strategy"] in LEARNED]),
            ("rules", [r for r in selected if r["strategy"] not in LEARNED]),
        ):
            group[name] = class_summary(subset)
            available = [
                indexed[key(r)] for r in subset if indexed[key(r)].get("etf_comparison_available")
            ]
            group[name]["matched_etf_comparisons"] = len(available)
            group[name]["beat_etf"] = sum(r["etf_excess_total_return"] > 0 for r in available)
        for learned in [r for r in selected if r["strategy"] in LEARNED]:
            for rule in [r for r in selected if r["strategy"] not in LEARNED]:
                matched = (
                    complete(learned)
                    and complete(rule)
                    and all(learned[k] == rule[k] for k in ("first_session", "last_session"))
                )
                pairs.append(
                    {
                        **dict(zip(GROUP, group_key)),
                        "learned": learned["strategy"],
                        "rule": rule["strategy"],
                        "learned_status": learned["status"],
                        "rule_status": rule["status"],
                        "comparison_available": matched,
                        "excess_total_return": learned["total_return"] - rule["total_return"]
                        if matched
                        else None,
                        "drawdown_difference": learned["max_drawdown"] - rule["max_drawdown"]
                        if matched
                        else None,
                    }
                )
        groups.append(group)
    cost_groups = defaultdict(list)
    for row in ledger:
        cost_groups[key(row, ("currency", "budget", "strategy", "horizon"))].append(row)
    robustness = []
    for group_key, selected in sorted(cost_groups.items()):
        valid = all(r["status"] == "complete" for r in selected) and {
            r["cost_bps"] for r in selected
        } == set(costs)
        result = dict(zip(("currency", "budget", "strategy", "horizon"), group_key))
        result.update(
            all_declared_costs_complete=valid,
            costs=[
                {
                    k: r.get(k)
                    for k in (
                        "cost_bps",
                        "status",
                        "total_return",
                        "max_drawdown",
                        "completed_trades",
                        "mean_exposure_fraction",
                        "etf_excess_total_return",
                    )
                }
                for r in sorted(selected, key=lambda r: r["cost_bps"])
            ],
            positive_at_every_cost=all(r["total_return"] > 0 for r in selected) if valid else None,
            under_30pct_drawdown_at_every_cost=all(r["max_drawdown"] <= 0.3 for r in selected)
            if valid
            else None,
            beat_etf_at_every_cost=all(
                r["etf_excess_total_return"] is not None and r["etf_excess_total_return"] > 0
                for r in selected
            )
            if valid
            else None,
        )
        robustness.append(result)
    diagnostics = calibration_summary(study.get("model_diagnostics", []))
    return {
        "integrity": {
            "passed": not errors,
            "errors": errors,
            "expected_accounts": len(expected),
            "observed_accounts": len(rows),
        },
        "all_accounts": ledger,
        "matched_groups": groups,
        "all_years": years,
        "all_folds": folds,
        "all_learned_rule_pairs": pairs,
        "cost_robustness": robustness,
        "activity_and_concentration": comparisons,
        "diagnostics": diagnostics,
        "global_counts": class_summary(rows),
        "missing_reasons": dict(Counter(m for row in rows for m in row.get("missing", []))),
        "benchmarks": benchmarks,
    }


def calibration_summary(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["currency"]].append(row)
    summary = []
    for currency, folds in sorted(groups.items()):
        by_horizon = []
        for index, horizon in enumerate((1, 3, 5)):
            items = [f["calibration"]["horizons"][str(horizon)] for f in folds]
            by_horizon.append(
                {
                    "horizon": horizon,
                    "folds": len(items),
                    "equal_weight_fallbacks": sum(i["equal_weight_fallback"] for i in items),
                    "weights_equal_fold_summary": {
                        model: distribution(i["weights"][model] for i in items)
                        for model in BASE_MODELS
                    },
                    "models_beating_training_mean_return_mse": {
                        model: sum(
                            f["calibration"]["model_mse"][model][index]
                            < f["calibration"]["baseline_mse"][index]
                            for f in folds
                        )
                        for model in BASE_MODELS
                    },
                    "models_beating_training_mean_downside_mse": {
                        model: sum(
                            f["calibration"]["model_mse"][model][index + 3]
                            < f["calibration"]["baseline_mse"][index + 3]
                            for f in folds
                        )
                        for model in BASE_MODELS
                    },
                }
            )
        warning_rows = [
            {"test_start": f["test_start"], "test_end": f["test_end"], **warning}
            for f in folds
            for warning in f.get("warnings", [])
        ]
        summary.append(
            {
                "currency": currency,
                "fold_count": len(folds),
                "horizons": by_horizon,
                "fit_rows": sum(f["fit_rows"] for f in folds),
                "calibration_rows": sum(f["calibration_rows"] for f in folds),
                "prediction_rows": sum(f["prediction_rows"] for f in folds),
                "excluded_label_rows": sum(f["excluded_label_rows"] for f in folds),
                "purged_fit_rows": sum(f["fit_sample"]["purged_rows"] for f in folds),
                "purged_calibration_rows": sum(
                    f["calibration_sample"]["purged_rows"] for f in folds
                ),
                "warnings": warning_rows,
                "warning_count": len(warning_rows),
                "mlp_convergence_warning_folds": len(
                    {
                        w["test_start"]
                        for w in warning_rows
                        if w["model"] == "multi_head_mlp" and w["category"] == "ConvergenceWarning"
                    }
                ),
                "sample_count_interpretation": (
                    "Overlapping rolling windows reuse historical rows; totals are processing "
                    "counts, not independent examples."
                ),
            }
        )
    return summary


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operational-smoke", action="store_true")
    args = parser.parse_args()
    source, target = args.input.resolve(), args.output.resolve()
    if not target.is_relative_to(QUALIFICATION.resolve()) or target == QUALIFICATION.resolve():
        parser.error("Output must be a named directory under .qualification")
    payload = source.read_bytes()
    study = json.loads(payload)
    report = analyze(study)
    report.update(
        provenance={
            "source": str(source),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "run_id": study.get("run_id"),
            "as_of": study["as_of"],
            "model_signature": study["methodology"]["model_signature"],
            "definition": study.get("definition"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "operational_smoke_only": args.operational_smoke,
        },
        interpretation=[
            (
                "Every declared account is retained. Incomplete accounts have no "
                "profitability comparison; their observed fold prefixes remain explicitly "
                "labeled."
            ),
            (
                "Matched references share currency, starting cash, proportional costs, "
                "first and last evaluation sessions. Rules also share holding period."
            ),
            (
                "Cost changes alter eligibility and sizing; higher-cost outcomes are not "
                "assumed to decrease monotonically."
            ),
            (
                "Cash-heavy means average invested fraction below 10%, a descriptive "
                "analysis threshold. A 30% observed drawdown screen is not an enforced "
                "future loss cap."
            ),
            (
                "Calendar-year and fold summaries include partial terminal intervals. "
                "Positive counts use strictly greater than zero."
            ),
            (
                "Pooled MSE and repeated account comparisons are descriptive, not "
                "independent tests or significance. Historical best rows remain "
                "exploratory."
            ),
            (
                "Current-member and adjusted-vintage biases remain. Proportional costs "
                "omit fixed brokerage charges, FX, subscription, taxes and contributions."
            ),
            (
                "Profit concentration retains only saved top/bottom symbols; it does not "
                "establish a complete per-symbol attribution."
            ),
            (
                "No model training, study execution, new data access, broker calls or "
                "main-result mutation is performed by this script."
            ),
        ],
    )
    target.mkdir(parents=True, exist_ok=True)
    for name in ("all_accounts", "all_years", "all_folds", "all_learned_rule_pairs"):
        write_csv(target / (name + ".csv"), report[name])
    (target / "analysis.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    compact = {
        "provenance": {k: v for k, v in report["provenance"].items() if k != "definition"},
        "integrity": report["integrity"],
        "global_counts": report["global_counts"],
        "matched_groups": report["matched_groups"],
        "diagnostics": report["diagnostics"],
        "cost_robustness_counts": {
            "declared_groups": len(report["cost_robustness"]),
            **{
                field: sum(row[field] is True for row in report["cost_robustness"])
                for field in (
                    "all_declared_costs_complete",
                    "positive_at_every_cost",
                    "under_30pct_drawdown_at_every_cost",
                    "beat_etf_at_every_cost",
                )
            },
        },
        "missing_reasons": report["missing_reasons"],
        "interpretation": report["interpretation"],
    }
    (target / "summary.json").write_text(
        json.dumps(compact, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(target),
                "integrity": report["integrity"],
                "accounts": len(report["all_accounts"]),
                "year_rows": len(report["all_years"]),
                "fold_rows": len(report["all_folds"]),
                "learned_rule_pairs": len(report["all_learned_rule_pairs"]),
                "operational_smoke_only": args.operational_smoke,
            }
        )
    )
    if not report["integrity"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
