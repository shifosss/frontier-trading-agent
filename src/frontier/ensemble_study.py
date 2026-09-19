"""Chronological multi-output forecasts and ensembles evaluated in daily cash accounts."""

from __future__ import annotations

import gc
import hashlib
import json
from collections import Counter

import numpy as np

from frontier.ensemble_features import build_features
from frontier.ensemble_models import CONFIG as MODEL_CONFIG
from frontier.ensemble_models import fit_predict_heads
from frontier.historical_settlement import build_settlement_indices
from frontier.historical_study import (
    FAMILIES,
    TRAINING,
    WARMUP,
    _benchmark,
    _build_market,
    _metrics,
    _notify,
)
from frontier.short_horizon_study import HORIZONS, _simulate_daily, _statistics, _summarize
from frontier.strategy_study import BOOKS, COSTS, _prepare

RULES = {
    "relative_reversal_2": "Two-session benchmark-relative reversal / lagged residual volatility",
    "relative_reversal_5": "Five-session benchmark-relative reversal / lagged residual volatility",
    "relative_volume_continuation_5": "Five-session relative continuation with high activity",
}
LEARNED = {
    "ridge": "Regularized linear six-output prediction",
    "extra_trees": "Nonlinear randomized-tree six-output prediction",
    "hist_gradient_boosting": "Gradient-boosted trees fitted separately for six targets",
    "multi_head_mlp": "Shared-hidden neural network with three return and three downside outputs",
    "equal_ensemble": "Equal average of the four fitted predictors",
    "calibrated_ensemble": "Per-horizon weights from earlier calibration prediction error",
    "diversified_ensemble": "Calibrated ensemble with trailing-correlation constraint",
}
STRATEGIES = {**FAMILIES, **RULES, **LEARNED}
CONFIG = {
    "version": "daily-multi-model-v1",
    "strategies": STRATEGIES,
    "horizons": list(HORIZONS),
    "budgets": [2000, 10000],
    "cost_bps": list(COSTS),
    "training_sessions": TRAINING,
    "fit_sessions": 504,
    "calibration_sessions": 252,
    "test_sessions": 252,
    "maximum_examples_per_session": 96,
    "seed": 1729,
    "detailed_trade_audit": "learned strategies at 2000 and 40bps; other paths aggregate",
    "screening_frequency": "every_completed_session",
    "execution": "next_session_close",
    "maximum_positions": 5,
    "position_budget_fraction": 0.2,
    "atr_risk_budget_fraction": 0.005,
    "predicted_downside_penalty": 0.5,
    "diversification_correlation_ceiling": 0.85,
    "model_config": MODEL_CONFIG,
    "declaration": "docs/superpowers/plans/2026-09-19-multi-model-study.md",
}


def _sample_rows(features, start, end, boundary, seed):
    """Sample within each earlier session, purging every target crossing the boundary."""
    rng = np.random.default_rng(seed)
    row_indices, symbol_indices = [], []
    eligible_rows = unavailable = purged = 0
    for day in range(start, end + 1):
        candidates = np.flatnonzero(features["eligible"][day] & features["benchmark_known"][day])
        eligible_rows += len(candidates)
        if features["label_end"][day].max() >= boundary:
            purged += len(candidates)
            continue
        known = np.isfinite(features["labels"][day, candidates]).all(axis=1)
        unavailable += int((~known).sum())
        candidates = candidates[known]
        if len(candidates) > CONFIG["maximum_examples_per_session"]:
            candidates = np.sort(
                rng.choice(candidates, CONFIG["maximum_examples_per_session"], replace=False)
            )
        row_indices.extend([day] * len(candidates))
        symbol_indices.extend(candidates.tolist())
    rows, columns = np.array(row_indices, dtype=np.int32), np.array(symbol_indices, dtype=np.int32)
    return (
        rows,
        columns,
        {
            "seed": seed,
            "eligible_rows": eligible_rows,
            "excluded_label_rows": unavailable,
            "purged_rows": purged,
            "sample_rows": len(rows),
            "sample_sha256": hashlib.sha256(
                np.column_stack((rows, columns)).astype("<i4").tobytes()
            ).hexdigest(),
        },
    )


def _rank_scores(scores):
    known = np.isfinite(scores)
    ranking = np.argsort(-np.where(known, scores, -np.inf), axis=1, kind="stable").astype(np.int32)
    return ranking, known.sum(axis=1)


def _combine(parts):
    """Join fold ledgers; each fold closes positions but preserves receivable settlement."""
    combined = {
        key: np.concatenate([part[key] for part in parts]) if parts else np.array([])
        for key in ("equity", "cash", "settled_cash", "unsettled_cash")
    }
    tallies, activity = _statistics(), Counter()
    for part in parts:
        for key in ("pnl", "returns", "holds", "days"):
            tallies[key].extend(part["tallies"][key])
        for symbol, profit in part["tallies"]["symbols"].items():
            tallies["symbols"][symbol] += profit
        activity.update(part["activity"])
    combined.update(
        status="incomplete"
        if any(p["status"] != "complete" for p in parts)
        else "complete"
        if parts
        else "insufficient_history",
        missing=[value for part in parts for value in part["missing"]],
        fees=sum(p["fees"] for p in parts),
        trades=sum(p["trades"] for p in parts),
        traded_notional=sum(p["traded_notional"] for p in parts),
        net_pnl_total=sum(p["net_pnl_total"] for p in parts),
        tallies=tallies,
        activity=dict(activity),
        audit_retained=bool(parts) and all(part["audit_retained"] for part in parts),
        trade_records=[record for part in parts for record in part["trade_records"]],
    )
    return combined


def _methodology(budgets):
    return {
        **CONFIG,
        "budgets": list(budgets),
        "kind": "chronological learned-forecast and matched-rule cash portfolios",
        "model_signature": "sha256:"
        + hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest(),
        "attempts": [
            {"strategy": name, "horizon": h, "description": description}
            for name, description in STRATEGIES.items()
            for h in HORIZONS
        ],
        "limitations": [
            "Current-member universe omits delisted stocks; current adjusted "
            "price vintage is not point-in-time data.",
            "Previously inspected history is reused exploratory research, not an "
            "untouched holdout.",
            "Six-output MLP is shared-hidden multi-output learning, not "
            "transformer multi-head attention.",
            "Fit uses earlier 504 sessions; the following 252 calibrate weights; "
            "outcomes crossing boundaries are purged.",
            "Annual model refits do not imply annual holdings: daily signals hold"
            " 1, 3 or 5 sessions after next-close fills.",
            "Training-only median imputation can make unavailable longer-lookback"
            " features usable without future screening.",
            "Per-date training samples bound computation; all eligible stocks "
            "receive test forecasts, irrespective of later label availability.",
            "Pooled calibration MSE and derived weights are predictive "
            "diagnostics, not independent samples or statistical significance.",
            "Equal-weight fallback when calibration finds no positive improvement"
            " is an explicit research control, not qualification.",
            "Downside predictions measure completed-close path declines, not "
            "intraday losses or a guaranteed stop.",
            "Candidates require predicted net return on the ledger fee basis "
            "minus half predicted downside above zero.",
            "All accounts share whole-share cash/settlement constraints, five "
            "slots and 20% entry caps; nominal prices and synthetic adjusted "
            "marks remain exploratory.",
            "The diversified ensemble rejects positive 60-session return "
            "correlation above .85 or pairs with fewer than 40 usable "
            "observations.",
            "Fold boundaries flatten positions; settled/unsettled cash carries "
            "forward. Required missing prices or signal inputs invalidate "
            "accounts.",
            "20/40/100 bps are proportional sensitivity scenarios, excluding "
            "fixed broker charges, FX, subscription, taxes, interest and "
            "contributions.",
            "No hourly, event/news, fundamental, options, live-account or "
            "profitability qualification is claimed. No automatic paper "
            "promotion.",
        ],
    }


def _fold_forecasts(features, start, end, fold, currency, sessions, progress):
    calibration_start = start - CONFIG["calibration_sessions"]
    train_start = start - TRAINING
    train_rows, train_symbols, train_audit = _sample_rows(
        features, train_start, calibration_start - 1, calibration_start, CONFIG["seed"] + fold * 2
    )
    cal_rows, cal_symbols, cal_audit = _sample_rows(
        features, calibration_start, start - 1, start, CONFIG["seed"] + fold * 2 + 1
    )
    # Prediction membership depends exclusively on information at the signal close.
    test_mask = (
        features["eligible"][start : end + 1] & features["benchmark_known"][start : end + 1, None]
    )
    local_rows, test_symbols = np.nonzero(test_mask)
    test_rows = local_rows + start
    if not len(train_rows) or not len(cal_rows):
        raise ValueError(
            f"No usable model training/calibration rows for {currency}:{sessions[start]}"
        )
    _notify(
        progress,
        stage="ensemble_fit",
        currency=currency,
        fold=fold + 1,
        test_start=sessions[start],
        fit_rows=len(train_rows),
        calibration_rows=len(cal_rows),
        prediction_rows=len(test_rows),
    )
    fitted = fit_predict_heads(
        features["X"][train_rows, train_symbols],
        features["labels"][train_rows, train_symbols],
        features["X"][cal_rows, cal_symbols],
        features["labels"][cal_rows, cal_symbols],
        features["X"][test_rows, test_symbols],
        seed=CONFIG["seed"],
    )
    diagnostics = {
        "currency": currency,
        "training_start": sessions[train_start],
        "training_end": sessions[calibration_start - 1],
        "calibration_start": sessions[calibration_start],
        "calibration_end": sessions[start - 1],
        "test_start": sessions[start],
        "test_end": sessions[end],
        "fit_rows": len(train_rows),
        "calibration_rows": len(cal_rows),
        "prediction_rows": len(test_rows),
        "eligible_fit_rows": train_audit["eligible_rows"],
        "eligible_calibration_rows": cal_audit["eligible_rows"],
        "excluded_label_rows": train_audit["excluded_label_rows"]
        + cal_audit["excluded_label_rows"],
        "fit_sample": train_audit,
        "calibration_sample": cal_audit,
        **{key: value for key, value in fitted.items() if key != "predictions"},
    }
    return fitted["predictions"], (local_rows, test_symbols), diagnostics


def _forecast_score(predicted, head, cost_bps):
    """Expected net return on entry notional, using the ledger's two-sided fee basis."""
    half_cost = cost_bps / 20000
    return (
        predicted[:, head] * (1 - half_cost)
        - 2 * half_cost
        - CONFIG["predicted_downside_penalty"] * np.maximum(0, predicted[:, head + 3])
    )


def _latest_forecasts(market, strategy, horizon, head, predicted, indices, start, end, currency):
    last = np.flatnonzero(indices[0] == end - start)
    scores = _forecast_score(predicted, head, 40)
    order = last[np.argsort(-scores[last], kind="stable")[:10]]
    return [
        {
            "currency": currency,
            "strategy": strategy,
            "horizon": horizon,
            "symbol": market["symbols"][int(indices[1][row])],
            "session": market["sessions"][end],
            "rank": rank,
            "predicted_return": float(predicted[row, head]),
            "predicted_downside": float(max(0, predicted[row, head + 3])),
            "score_40bps": float(scores[row]),
            "price": float(market["close"][end, int(indices[1][row])]),
        }
        for rank, row in enumerate(order, 1)
    ]


def _account_fold(
    account,
    market,
    features,
    strategy,
    horizon,
    budget,
    cost,
    start,
    end,
    ranking,
    counts,
    diagnostics,
):
    if account["parts"] and account["parts"][-1]["status"] != "complete":
        return
    learned = strategy in LEARNED
    starting = account["state"]["cash"] if account["state"] is not None else budget
    simulation = _simulate_daily(
        market,
        strategy,
        horizon,
        starting,
        cost,
        start,
        end,
        state=account["state"],
        audit=learned and budget == 2000 and cost == 40,
        signal_ranking=ranking,
        signal_counts=counts,
        signal_known=features["benchmark_known"] if learned or strategy in RULES else None,
        correlation_limit=CONFIG["diversification_correlation_ceiling"]
        if strategy == "diversified_ensemble"
        else None,
    )
    account["parts"].append(simulation)
    account["state"] = simulation["state"]
    metrics = _metrics(simulation, market["sessions"][start : end + 1], starting, curves=False)
    account["folds"].append(
        {
            "training_start": diagnostics["training_start"],
            "training_end": diagnostics["training_end"],
            "test_start": market["sessions"][start],
            "test_end": market["sessions"][end],
            "selected_strategy": strategy,
            "selected_horizon": horizon,
            "training_score": None,
            "test_return": metrics["total_return"],
            "test_status": simulation["status"],
            "starting_equity": starting,
            "ending_equity": metrics["ending_equity"],
        }
    )


def evaluate_ensemble(frame, universe, *, as_of, budgets=(2000, 10000), progress=None):
    """Fit earlier data and evaluate every declared model/rule on continuous cash accounts."""
    _, specs, current, budgets = _prepare(frame.iloc[:0], universe, as_of, budgets)
    if set(frame.symbol.unique()) - specs.keys():
        raise ValueError("Data contains symbols outside the declared universe")
    result = {
        "schema_version": 1,
        "as_of": current.isoformat(),
        "methodology": _methodology(budgets),
        "coverage": {"markets": [], "instruments": []},
        "portfolios": [],
        "benchmarks": [],
        "walk_forward": [],
        "model_diagnostics": [],
        "latest_candidates": [],
    }
    first_test = WARMUP + TRAINING
    for currency in BOOKS:
        if not any(s["currency"] == currency for s in universe):
            continue
        market = _build_market(frame, universe, current, currency, progress, include_activity=True)
        market["settlement_index"] = build_settlement_indices(market["sessions"], currency)
        market["dates"] = np.array(market["sessions"], dtype="datetime64[D]")
        n, m = market["close"].shape
        _notify(progress, stage="ensemble_features", currency=currency, symbols=m)
        features = build_features(
            market,
            stock_mask=np.array([specs[s]["asset_type"] == "stock" for s in market["symbols"]]),
            liquidity_floor=BOOKS[currency][2],
            turnover=market.pop("turnover"),
            dollar_volume=market.pop("dollar_volume"),
        )
        result["methodology"]["feature_names"] = features["feature_names"]
        result["coverage"]["instruments"].extend(market["coverage"])
        result["coverage"]["markets"].append(
            {
                "currency": currency,
                "calendar_sessions": n,
                "first_session": market["sessions"][0] if n else None,
                "last_session": market["sessions"][-1] if n else None,
                "stock_count": sum(specs[s]["asset_type"] == "stock" for s in market["symbols"]),
                "discarded_rows": market["discarded_rows"],
                "benchmark": market["benchmark_symbol"],
            }
        )
        rule_ranks = {
            name: _rank_scores(values) for name, values in features.pop("rule_scores").items()
        }
        accounts = {
            (strategy, h, budget, cost): {"state": None, "parts": [], "folds": []}
            for strategy in STRATEGIES
            for h in HORIZONS
            for budget in budgets
            for cost in COSTS
        }
        for fold, start in enumerate(range(first_test, n, CONFIG["test_sessions"])):
            end = min(n - 1, start + CONFIG["test_sessions"] - 1)
            predictions, indices, diagnostics = _fold_forecasts(
                features, start, end, fold, currency, market["sessions"], progress
            )
            result["model_diagnostics"].append(diagnostics)
            for strategy in STRATEGIES:
                for horizon_index, h in enumerate(HORIZONS):
                    learned = strategy in LEARNED
                    ranking = counts = None
                    score = None
                    if learned:
                        predicted = predictions[
                            "calibrated_ensemble"
                            if strategy == "diversified_ensemble"
                            else strategy
                        ]
                        score = np.full((end - start + 1, m), np.nan)
                        ranking = np.zeros((n, m), dtype=np.int32)
                        if end == n - 1 and strategy != "diversified_ensemble":
                            result["latest_candidates"].extend(
                                _latest_forecasts(
                                    market,
                                    strategy,
                                    h,
                                    horizon_index,
                                    predicted,
                                    indices,
                                    start,
                                    end,
                                    currency,
                                )
                            )
                    elif strategy in RULES:
                        ranking, counts = rule_ranks[strategy]
                    for cost in COSTS:
                        if learned:
                            score[indices] = _forecast_score(predicted, horizon_index, cost)
                            positive = np.where(score > 0, score, np.nan)
                            fold_ranking, fold_counts = _rank_scores(positive)
                            ranking[start : end + 1] = fold_ranking
                            counts = np.zeros(n, dtype=np.int32)
                            counts[start : end + 1] = fold_counts
                        for budget in budgets:
                            _account_fold(
                                accounts[(strategy, h, budget, cost)],
                                market,
                                features,
                                strategy,
                                h,
                                budget,
                                cost,
                                start,
                                end,
                                ranking,
                                counts,
                                diagnostics,
                            )
                    if learned:
                        del ranking, score
            del predictions
            _notify(
                progress,
                stage="ensemble_portfolios",
                currency=currency,
                fold=fold + 1,
                total_folds=len(range(first_test, n, CONFIG["test_sessions"])),
                test_start=market["sessions"][start],
            )
        for (strategy, h, budget, cost), account in accounts.items():
            combined = _combine(account["parts"])
            sessions = market["sessions"][first_test : first_test + len(combined["equity"])]
            result["portfolios"].append(
                {
                    "currency": currency,
                    "budget": budget,
                    "cost_bps": cost,
                    "strategy": strategy,
                    "horizon": h,
                    **_summarize(combined, sessions, budget),
                    "folds": account["folds"],
                }
            )
        for budget in budgets:
            for cost in COSTS:
                for symbol in (market["benchmark_symbol"], "CASH"):
                    simulation = (
                        _benchmark(market, budget, cost, first_test, n - 1)
                        if symbol != "CASH"
                        else _simulate_daily(market, "cash", 1, budget, cost, first_test, n - 1)
                    )
                    result["benchmarks"].append(
                        {
                            "currency": currency,
                            "budget": budget,
                            "cost_bps": cost,
                            "symbol": symbol,
                            **_metrics(simulation, market["sessions"][first_test:n], budget),
                        }
                    )
        del market, features, accounts, rule_ranks
        gc.collect()
    return result
