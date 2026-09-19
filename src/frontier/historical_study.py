"""Chronological whole-share cash portfolios and retrospective walk-forward research."""

from __future__ import annotations

import gc
import hashlib
import json
import math

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from frontier.strategy_study import BOOKS, COSTS, HORIZONS, STRATEGIES, _market, _prepare

WARMUP = 200
TRAINING = 756
TESTING = 252
CHUNK_SIZE = 128
SIGNALS = {
    **STRATEGIES,
    "momentum_12_1": "Positive 252-to-21-session return; "
    "skip the latest month, volatility-normalized rank",
}
FAMILIES = {
    **SIGNALS,
    **{
        name + "_market_trend": description + "; benchmark must exceed its 200-session mean"
        for name, description in SIGNALS.items()
    },
}
CONFIG = {
    "version": "historical-cash-walk-forward-v1",
    "strategies": FAMILIES,
    "horizons": list(HORIZONS),
    "round_trip_cost_bps": list(COSTS),
    "training_sessions": TRAINING,
    "test_sessions": TESTING,
    "minimum_stock_sessions": WARMUP + 1,
    "intermediate_momentum_minimum_sessions": 253,
    "maximum_positions": 5,
    "position_budget_fraction": 0.2,
    "atr_risk_budget_fraction": 0.005,
    "cash_settlement_sessions": 3,
    "selection_cost_bps": max(COSTS),
    "selection_score": "median three 252-session returns minus half maximum drawdown",
    "selection_requirements": {
        "minimum_completed_position_trades": 12,
        "minimum_profitable_training_blocks": 2,
        "maximum_drawdown": 0.3,
        "minimum_score_exclusive": 0,
    },
}


def _notify(progress, **value):
    if progress is not None:
        progress(value)


def _build_market(frame, universe, current, currency, progress, *, include_activity=False):
    """Calculate each symbol's rolling features once, with bounded temporary matrices."""
    specs = {row["symbol"]: row for row in universe if row["currency"] == currency}
    symbols = sorted(specs)
    calendar_name, benchmark, _ = BOOKS[currency]
    groups = frame.groupby("symbol", sort=False, observed=True).indices
    offsets = [groups[symbol] for symbol in symbols if symbol in groups]
    first = (
        str(pd.Timestamp(frame.session.iloc[np.concatenate(offsets)].min()).date())
        if offsets
        else current.date().isoformat()
    )
    calendar = xcals.get_calendar(
        calendar_name, start=first, end=str(current.date() + pd.Timedelta(days=90))
    )
    schedule = calendar.schedule
    completed = schedule["close"] + pd.Timedelta(minutes=1) <= current
    sessions = schedule.index[completed].strftime("%Y-%m-%d").tolist()
    n, m = len(sessions), len(symbols)
    arrays = {key: np.full((n, m), np.nan) for key in ("close", "adjusted", "atr")}
    if include_activity:
        arrays.update({key: np.full((n, m), np.nan) for key in ("turnover", "dollar_volume")})
    scores = {key: np.full((n, m), np.nan) for key in SIGNALS}
    positions = pd.Index(sessions)
    coverage, discarded = [], 0
    for start in range(0, m, CHUNK_SIZE):
        chunk_symbols = symbols[start : start + CHUNK_SIZE]
        chunk_offsets = [groups[symbol] for symbol in chunk_symbols if symbol in groups]
        source = frame.iloc[np.concatenate(chunk_offsets)] if chunk_offsets else frame.iloc[:0]
        data, chunk_specs, _, _ = _prepare(
            source, [specs[symbol] for symbol in chunk_symbols], current, (1,)
        )
        market = _market(data, chunk_specs, current, currency)
        rows = positions.get_indexer(market["sessions"][: market["n"]])
        if (rows < 0).any():
            raise ValueError("Feature sessions do not match the market calendar")
        columns = np.arange(start, start + len(chunk_symbols))
        for key in arrays:
            arrays[key][np.ix_(rows, columns)] = market[key]
        for key in STRATEGIES:
            scores[key][np.ix_(rows, columns)] = market["scores"][key]
        prices = pd.DataFrame(market["adjusted"])
        volatility = prices.pct_change(fill_method=None).rolling(20).std() * np.sqrt(252)
        intermediate = prices.shift(21) / prices.shift(252) - 1
        mature = prices.notna().rolling(253, min_periods=253).sum().eq(253)
        stock = np.array([chunk_specs[symbol]["asset_type"] == "stock" for symbol in chunk_symbols])
        eligible = (
            mature.to_numpy()
            & (market["turnover"] >= BOOKS[currency][2])
            & (market["atr"] > 0)
            & (volatility.to_numpy() > 1e-12)
            & stock
        )
        scores["momentum_12_1"][np.ix_(rows, columns)] = (
            (intermediate / volatility).where(eligible & intermediate.gt(0)).to_numpy()
        )
        coverage.extend(market["coverage"])
        discarded += market["discarded_rows"]
        del data, market
        _notify(
            progress, stage="historical_features", currency=currency, symbols=start + len(columns)
        )
    ranking, counts = {}, {}
    for family in SIGNALS:
        values = scores.pop(family)
        counts[family] = np.isfinite(values).sum(axis=1)
        # Every eligible stock remains reachable; alphabetical columns break score ties.
        ranking[family] = np.argsort(
            -np.where(np.isfinite(values), values, -np.inf), axis=1, kind="stable"
        ).astype(np.int32)
        del values
    benchmark_index = symbols.index(benchmark) if benchmark in symbols else None
    trend = np.zeros(n, dtype=bool)
    trend_known = np.zeros(n, dtype=bool)
    if benchmark_index is not None:
        price = pd.Series(arrays["adjusted"][:, benchmark_index])
        trend_known = price.notna().rolling(200, min_periods=200).sum().eq(200).to_numpy()
        trend = (price > price.rolling(200, min_periods=200).mean()).to_numpy()
    return {
        **arrays,
        "n": n,
        "symbols": symbols,
        "sessions": sessions,
        "ranking": ranking,
        "counts": counts,
        "benchmark": benchmark_index,
        "benchmark_symbol": benchmark,
        "market_trend": trend,
        "market_trend_known": trend_known,
        "coverage": coverage,
        "discarded_rows": discarded,
    }


def _selection(market, strategy, signal, budget, cost_bps):
    family = strategy.removesuffix("_market_trend")
    if strategy.endswith("_market_trend") and not market["market_trend"][signal]:
        return np.array([], dtype=int), np.array([], dtype=int)
    ranked = market["ranking"][family][signal, : market["counts"][family][signal]]
    prices, atr = market["close"][signal, ranked], market["atr"][signal, ranked]
    fee = cost_bps / 20_000
    quantities = np.floor(
        np.minimum(0.2 * budget / (prices * (1 + fee)), 0.005 * budget / (2 * atr))
    )
    affordable = np.flatnonzero(quantities > 0)[:5]
    return ranked[affordable], quantities[affordable].astype(int)


def _simulate(
    market, strategy, horizon, budget, cost_bps, start, end, *, audit=True, cash_ready=None
):
    """Run nonoverlapping batches; sell proceeds are reused no earlier than T+3."""
    length = max(0, end - start + 1)
    equity = np.full(length, budget, dtype=float)
    cash_curve = equity.copy()
    cash, fees, trades = float(budget), 0.0, 0
    ready = start if cash_ready is None else cash_ready
    signal = max(start, ready - 1)
    missing, events = [], []
    half_cost = cost_bps / 20_000
    while signal + 1 + horizon <= end and strategy != "cash":
        entry, exit_ = signal + 1, signal + 1 + horizon
        if strategy.endswith("_market_trend") and not market["market_trend_known"][signal]:
            missing.append(f"{market['benchmark_symbol']}:{market['sessions'][signal]}:regime_200")
            equity[signal - start :], cash_curve[signal - start :] = np.nan, np.nan
            break
        selected, planned = _selection(market, strategy, signal, cash, cost_bps)
        if not len(selected):
            signal += horizon + 3
            continue
        prices = market["close"][entry, selected]
        invalid_entry = ~np.isfinite(prices) | (prices <= 0)
        if invalid_entry.any():
            missing.extend(
                f"{market['symbols'][j]}:{market['sessions'][entry]}:entry"
                for j in selected[invalid_entry]
            )
            equity[entry - start :] = np.nan
            cash_curve[entry - start :] = np.nan
            break
        # Signal-time quantities may decrease for gaps and fees, never increase or rerank.
        filled = np.minimum(planned, np.floor(0.2 * cash / (prices * (1 + half_cost)))).astype(int)
        held = filled > 0
        adjusted = market["adjusted"][entry : exit_ + 1, selected[held]]
        missing_mask = ~np.isfinite(adjusted) | (adjusted <= 0)
        if missing_mask.any():
            for j, symbol_index in enumerate(selected[held]):
                for day in np.flatnonzero(missing_mask[:, j]):
                    missing.append(
                        f"{market['symbols'][symbol_index]}:{market['sessions'][entry + day]}:mark"
                    )
            equity[entry - start :] = np.nan
            cash_curve[entry - start :] = np.nan
            break
        notionals = filled * prices
        entry_fee = float(notionals.sum() * half_cost)
        cash -= float(notionals.sum()) + entry_fee
        if cash < -1e-7:
            raise ArithmeticError("Cash account attempted to borrow")
        cash = max(0.0, cash)
        marks = (adjusted / adjusted[0] * notionals[held]).sum(axis=1)
        equity[entry - start : exit_ - start + 1] = cash + marks
        cash_curve[entry - start : exit_ - start + 1] = cash
        exit_fee = float(marks[-1] * half_cost)
        cash += float(marks[-1]) - exit_fee
        fees += entry_fee + exit_fee
        trades += int((filled > 0).sum())
        equity[exit_ - start :] = cash
        cash_curve[exit_ - start :] = cash
        if audit:
            events.append(
                {
                    "signal_session": market["sessions"][signal],
                    "entry_session": market["sessions"][entry],
                    "exit_session": market["sessions"][exit_],
                    "selected": [market["symbols"][j] for j in selected],
                    "planned_quantities": planned.tolist(),
                    "filled_quantities": filled.tolist(),
                    "entry_notional": float(notionals.sum()),
                    "fees": entry_fee + exit_fee,
                    "ending_cash": cash,
                }
            )
        ready = exit_ + CONFIG["cash_settlement_sessions"]
        signal = ready - 1
    return {
        "equity": equity,
        "cash": cash_curve,
        "status": "incomplete" if missing else "complete" if length else "insufficient_history",
        "missing": missing,
        "fees": fees,
        "trades": trades,
        "trade_batches": events,
        "cash_ready": ready,
    }


def _benchmark(market, budget, cost_bps, start, end):
    length = max(0, end - start + 1)
    equity = np.full(length, budget, dtype=float)
    cash = equity.copy()
    result = {"equity": equity, "cash": cash, "fees": 0.0, "trades": 0, "missing": []}
    if length < 2:
        return {**result, "status": "insufficient_history"}
    j = market["benchmark"]
    if j is None:
        return {**result, "status": "incomplete", "missing": ["benchmark_absent"]}
    price = market["close"][start + 1, j]
    if not np.isfinite(price) or price <= 0:
        equity[1:], cash[1:] = np.nan, np.nan
        return {**result, "status": "incomplete", "missing": ["benchmark_entry_missing"]}
    half_cost = cost_bps / 20_000
    quantity = math.floor(budget / (price * (1 + half_cost)))
    if quantity == 0:
        return {**result, "status": "complete", "quantity": 0}
    adjusted = market["adjusted"][start + 1 : end + 1, j]
    if not np.isfinite(adjusted).all() or (adjusted <= 0).any():
        equity[1:], cash[1:] = np.nan, np.nan
        return {**result, "status": "incomplete", "missing": ["benchmark_price_missing"]}
    notional = quantity * price
    free = budget - notional * (1 + half_cost)
    marks = notional * adjusted / adjusted[0]
    equity[1:] = free + marks
    cash[1:] = free
    equity[-1] -= marks[-1] * half_cost
    cash[-1] = equity[-1]
    return {
        **result,
        "status": "complete",
        "fees": float((notional + marks[-1]) * half_cost),
        "trades": int(quantity > 0),
        "quantity": quantity,
    }


def _metrics(simulation, sessions, budget, *, curves=True):
    equity, cash = simulation["equity"], simulation["cash"]
    result = {key: simulation[key] for key in ("status", "missing", "fees", "trades")}
    result.update(
        first_session=sessions[0] if sessions else None,
        last_session=sessions[-1] if sessions else None,
        ending_equity=None,
        total_return=None,
        max_drawdown=None,
        cagr=None,
        annualized_volatility=None,
        yearly=[],
    )
    if simulation["status"] == "complete" and len(equity):
        years = (pd.Timestamp(sessions[-1]) - pd.Timestamp(sessions[0])).days / 365.25
        daily = equity[1:] / equity[:-1] - 1
        result.update(
            ending_equity=float(equity[-1]),
            total_return=float(equity[-1] / budget - 1),
            max_drawdown=float(1 - np.min(equity / np.maximum.accumulate(equity))),
            cagr=float((equity[-1] / budget) ** (1 / years) - 1) if years > 0 else None,
            annualized_volatility=float(np.std(daily, ddof=1) * np.sqrt(252))
            if len(daily) > 1
            else None,
        )
        year_labels = np.array([value[:4] for value in sessions])
        for year in dict.fromkeys(year_labels):
            indices = np.flatnonzero(year_labels == year)
            before = equity[indices[0] - 1] if indices[0] else budget
            path = np.r_[before, equity[indices]]
            result["yearly"].append(
                {
                    "year": str(year),
                    "return": float(path[-1] / before - 1),
                    "max_drawdown": float(1 - np.min(path / np.maximum.accumulate(path))),
                }
            )
    if curves:
        result["equity_curve"] = [
            {
                "session": session,
                "equity": float(value) if np.isfinite(value) else None,
                "cash": float(balance) if np.isfinite(balance) else None,
            }
            for session, value, balance in zip(sessions, equity, cash)
        ]
    return result


def _choose(market, budget, start, end):
    candidates = []
    for strategy in FAMILIES:
        for horizon in HORIZONS:
            simulation = _simulate(
                market, strategy, horizon, budget, max(COSTS), start, end, audit=False
            )
            metrics = _metrics(
                simulation, market["sessions"][start : end + 1], budget, curves=False
            )
            row = {
                "strategy": strategy,
                "horizon": horizon,
                **metrics,
                "score": None,
                "eligible": False,
            }
            if metrics["status"] == "complete":
                values = simulation["equity"]
                ends = [values[TESTING - 1], values[TESTING * 2 - 1], values[-1]]
                returns = np.array(ends) / np.array([budget, *ends[:-1]]) - 1
                score = float(np.median(returns) - 0.5 * metrics["max_drawdown"])
                row.update(
                    score=score,
                    training_block_returns=returns.tolist(),
                    eligible=bool(
                        metrics["trades"] >= 12
                        and (returns > 0).sum() >= 2
                        and metrics["max_drawdown"] <= 0.3
                        and score > 0
                    ),
                )
            candidates.append(row)
    eligible = [row for row in candidates if row["eligible"]]
    selected = sorted(eligible, key=lambda row: (-row["score"], row["strategy"], row["horizon"]))
    return selected[0] if selected else {"strategy": "cash", "horizon": 5, "score": 0.0}, candidates


def _walk_forward(market, budget, currency, progress):
    first_test = WARMUP + TRAINING
    n = market["n"]
    accounts = {
        cost: {
            "cash": budget,
            "cash_ready": first_test,
            "parts": [],
            "folds": [],
            "fees": 0.0,
            "trades": 0,
            "missing": [],
        }
        for cost in COSTS
    }
    for test_start in range(first_test, n, TESTING):
        test_end = min(n - 1, test_start + TESTING - 1)
        train_start, train_end = test_start - TRAINING, test_start - 1
        selected, candidates = _choose(market, budget, train_start, train_end)
        for cost, account in accounts.items():
            if account["missing"]:
                continue
            starting = account["cash"]
            simulation = _simulate(
                market,
                selected["strategy"],
                selected["horizon"],
                starting,
                cost,
                test_start,
                test_end,
                cash_ready=account["cash_ready"],
            )
            metrics = _metrics(
                simulation, market["sessions"][test_start : test_end + 1], starting, curves=False
            )
            account["folds"].append(
                {
                    "training_start": market["sessions"][train_start],
                    "training_end": market["sessions"][train_end],
                    "test_start": market["sessions"][test_start],
                    "test_end": market["sessions"][test_end],
                    "selected_strategy": selected["strategy"],
                    "selected_horizon": selected["horizon"],
                    "training_score": selected["score"],
                    "selection_candidates": candidates,
                    "test_return": metrics["total_return"],
                    "test_status": simulation["status"],
                    "starting_equity": starting,
                    "ending_equity": metrics["ending_equity"],
                    "trade_batches": simulation["trade_batches"],
                }
            )
            account["parts"].append(simulation)
            account["missing"].extend(simulation["missing"])
            account["fees"] += simulation["fees"]
            account["trades"] += simulation["trades"]
            if not account["missing"]:
                account["cash"] = float(simulation["equity"][-1])
                account["cash_ready"] = simulation["cash_ready"]
        _notify(
            progress,
            stage="historical_walk_forward",
            currency=currency,
            budget=budget,
            test_start=market["sessions"][test_start],
        )
    results = []
    for cost, account in accounts.items():
        parts = account["parts"]
        equity = np.concatenate([part["equity"] for part in parts]) if parts else np.array([])
        cash = np.concatenate([part["cash"] for part in parts]) if parts else np.array([])
        simulation = {
            "equity": equity,
            "cash": cash,
            "fees": account["fees"],
            "trades": account["trades"],
            "missing": account["missing"],
            "status": "incomplete"
            if account["missing"]
            else "complete"
            if parts
            else "insufficient_history",
        }
        sessions = market["sessions"][first_test : first_test + len(equity)]
        reference = _benchmark(market, budget, cost, first_test, n - 1)
        results.append(
            {
                "currency": currency,
                "budget": budget,
                "cost_bps": cost,
                **_metrics(simulation, sessions, budget),
                "folds": account["folds"],
                "benchmark": _metrics(reference, market["sessions"][first_test:n], budget),
            }
        )
    return results


def evaluate_historical(
    frame, universe, *, as_of, budgets=(500, 2000, 10000, 100000), progress=None
):
    """Evaluate declared historical attempts and separately simulate rolling model selection."""
    _, specs, current, budgets = _prepare(frame.iloc[:0], universe, as_of, budgets)
    if set(frame.symbol.unique()) - specs.keys():
        raise ValueError("Data contains symbols outside the declared universe")
    attempts = [
        {"strategy": strategy, "horizon": horizon, "description": description}
        for strategy, description in FAMILIES.items()
        for horizon in HORIZONS
    ]
    portfolios, references, walk_forward, markets, instruments = [], [], [], [], []
    for currency in BOOKS:
        if not any(row["currency"] == currency for row in universe):
            continue
        market = _build_market(frame, universe, current, currency, progress)
        n = market["n"]
        instruments.extend(market["coverage"])
        markets.append(
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
        for budget in budgets:
            for cost in COSTS:
                reference = _benchmark(market, budget, cost, WARMUP, n - 1)
                references.append(
                    {
                        "currency": currency,
                        "budget": budget,
                        "cost_bps": cost,
                        "symbol": market["benchmark_symbol"],
                        **_metrics(reference, market["sessions"][WARMUP:n], budget),
                    }
                )
                cash_reference = _simulate(market, "cash", 5, budget, cost, WARMUP, n - 1)
                references.append(
                    {
                        "currency": currency,
                        "budget": budget,
                        "cost_bps": cost,
                        "symbol": "CASH",
                        **_metrics(cash_reference, market["sessions"][WARMUP:n], budget),
                    }
                )
                for attempt in attempts:
                    simulation = _simulate(
                        market, attempt["strategy"], attempt["horizon"], budget, cost, WARMUP, n - 1
                    )
                    portfolios.append(
                        {
                            "currency": currency,
                            "budget": budget,
                            "cost_bps": cost,
                            "strategy": attempt["strategy"],
                            "horizon": attempt["horizon"],
                            **_metrics(simulation, market["sessions"][WARMUP:n], budget),
                            "trade_batches": simulation["trade_batches"],
                        }
                    )
            _notify(progress, stage="historical_portfolios", currency=currency, budget=budget)
            walk_forward.extend(_walk_forward(market, budget, currency, progress))
        del market
        gc.collect()
    return {
        "schema_version": 1,
        "as_of": current.isoformat(),
        "methodology": {
            **CONFIG,
            "model_signature": "sha256:"
            + hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest(),
            "attempts": attempts,
            "budgets": list(budgets),
            "cost_bps": list(COSTS),
            "limitations": [
                "Retrospective research designed today, not a prospectively untouched "
                "historical test.",
                "Current-listed membership omits historical delisted firms and introduces "
                "survivorship bias.",
                "Provider-adjusted prices are today's vintage. Signals may reflect later "
                "corrections.",
                "Historical availability is imputed at exchange close plus one minute, "
                "not verified provider publication time.",
                "Historical capture reconstructs nominal prices using provider-reported splits; "
                "missing or revised actions can still distort historical share affordability.",
                "Daily marks anchor raw entry notional to adjusted-close ratios: synthetic "
                "total-return units, not a corporate-action cash ledger.",
                "Training uses only the preceding 756 sessions; a selected rule is frozen for "
                "the next 252 sessions. All attempts and training scores are reported.",
                "Selection uses the declared initial budget at 100 bps costs; test accounts "
                "compound their own wealth. Cash is selected when no candidate qualifies.",
                "Next-close entries, nonoverlapping batches, no margin, whole shares, maximum "
                "five stocks, conservative T+3 sale settlement in every era.",
                "Portfolios are in cash at each predetermined fold boundary; entries that "
                "cannot finish their full horizon before that boundary are skipped.",
                "Any missing selected entry or held daily adjusted price invalidates that "
                "portfolio result; losses are never dropped from an average.",
                "Costs are symmetric proportional fees and slippage per executed notional; "
                "taxes, fixed commissions, FX, borrow, interest and monthly contributions are "
                "excluded.",
                "Full-period fixed-rule comparisons are descriptive; selecting their best "
                "result would reuse test data.",
                "Drawdown is a positive loss fraction from the preceding daily equity peak; "
                "all returns are native currency with no FX conversion.",
            ],
        },
        "coverage": {"markets": markets, "instruments": instruments},
        "portfolios": portfolios,
        "benchmarks": references,
        "walk_forward": walk_forward,
    }
