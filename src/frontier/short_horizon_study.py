"""Daily, independent short-hold cash portfolios; isolated from frozen research/paper rules."""

from __future__ import annotations

import gc
import hashlib
import json
import math
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from frontier.historical_settlement import SETTLEMENT_ASSUMPTION, build_settlement_indices
from frontier.historical_study import (
    FAMILIES,
    TRAINING,
    WARMUP,
    _benchmark,
    _build_market,
    _metrics,
    _notify,
)
from frontier.strategy_study import BOOKS, COSTS, _prepare

HORIZONS = (1, 3, 5)
TESTING = 252
TRAINING_BLOCK = 252
CONFIG = {
    "version": "daily-short-hold-v1",
    "horizons": list(HORIZONS),
    "strategies": FAMILIES,
    "training_sessions": TRAINING,
    "training_block_sessions": TRAINING_BLOCK,
    "test_sessions": TESTING,
    "screening_frequency": "every_completed_session",
    "execution": "next_session_close",
    "maximum_positions": 5,
    "position_budget_fraction": 0.2,
    "atr_risk_budget_fraction": 0.005,
    "round_trip_cost_bps": list(COSTS),
    "settlement": "date-specific T+3/T+2/T+1; conservative bank/exchange calendar intersection",
    "settlement_assumption": SETTLEMENT_ASSUMPTION,
    "selection_cost_bps": max(COSTS),
    "selection_score": "median three 252-session returns minus half maximum drawdown",
    "selection_requirements": {
        "minimum_completed_position_trades": 12,
        "minimum_profitable_training_blocks": 2,
        "maximum_drawdown": 0.3,
        "minimum_score_exclusive": 0,
    },
    "fixed_grid_audit": "aggregate statistics; replay one view for individual trade records",
    "view_replay_api": "evaluate_short_horizon_view",
}


def _market_data(frame, universe, current, currency, progress):
    market = _build_market(frame, universe, current, currency, progress)
    market["settlement_index"] = build_settlement_indices(market["sessions"], currency)
    market["dates"] = np.array(market["sessions"], dtype="datetime64[D]")
    return market


def _diversified(adjusted, signal, candidate, peers, limit):
    """Compare trailing completed returns only; unknown pair risk is not zero risk."""
    if not peers:
        return True
    history = adjusted[max(0, signal - 60) : signal + 1, [candidate, *peers]]
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = history[1:] / history[:-1] - 1
    for column in range(1, returns.shape[1]):
        pair = returns[:, [0, column]]
        pair = pair[np.isfinite(pair).all(axis=1)]
        if len(pair) < 40 or (pair.std(axis=0) <= 1e-12).any():
            return False
        if np.corrcoef(pair.T)[0, 1] > limit:
            return False
    return True


def _statistics():
    return {"pnl": [], "returns": [], "holds": [], "days": [], "symbols": defaultdict(float)}


def _simulate_daily(
    market,
    strategy,
    horizon,
    budget,
    cost_bps,
    start,
    end,
    *,
    state=None,
    audit=False,
    statistics=True,
    signal_ranking=None,
    signal_counts=None,
    signal_known=None,
    correlation_limit=None,
):
    """Signal after close, fill at next close, expire each position independently.

    Receivables settle at their calendar-derived session open. Known next-opening
    settlements may reserve an order today; proceeds cannot be spent before settlement.
    """
    if horizon not in HORIZONS or (signal_ranking is None and strategy not in {*FAMILIES, "cash"}):
        raise ValueError("Unknown short-hold strategy or horizon")
    length = max(0, end - start + 1)
    path = {
        key: np.full(length, np.nan) for key in ("equity", "cash", "settled_cash", "unsettled_cash")
    }
    cash = float(state["cash"] if state is not None else budget)
    settled = float(state["settled_cash"] if state is not None else budget)
    receivables = list(state["receivables"]) if state is not None else []
    held, pending, missing, records = {}, [], [], []
    tallies, activity = _statistics(), Counter()
    fees = traded_notional = net_pnl = 0.0
    completed_trades = 0
    half_cost = cost_bps / 20_000
    for i in range(start, end + 1):
        remaining = []
        for due, amount in receivables:
            if due <= i:
                settled += amount
            else:
                remaining.append((due, amount))
        receivables = remaining
        marks = {}
        for j, position in held.items():
            price = market["adjusted"][i, j]
            if not np.isfinite(price) or price <= 0:
                missing.append(f"{market['symbols'][j]}:{market['sessions'][i]}:mark")
            else:
                marks[j] = position["notional"] * price / position["adjusted_entry"]
        if missing:
            break
        for j in list(held):
            position = held[j]
            if position["exit"] != i:
                continue
            value = marks.pop(j)
            exit_fee = value * half_cost
            proceeds = value - exit_fee
            cash += proceeds
            receivables.append((int(market["settlement_index"][i]), proceeds))
            profit = proceeds - position["notional"] - position["entry_fee"]
            completed_trades += 1
            net_pnl += profit
            fees += exit_fee
            traded_notional += value
            days = int((market["dates"][i] - market["dates"][position["entry"]]).astype(int))
            if statistics:
                tallies["pnl"].append(profit)
                tallies["returns"].append(profit / position["notional"])
                tallies["holds"].append(i - position["entry"])
                tallies["days"].append(days)
                tallies["symbols"][market["symbols"][j]] += profit
            if audit:
                records.append(
                    {
                        "symbol": market["symbols"][j],
                        "signal_session": market["sessions"][position["signal"]],
                        "entry_session": market["sessions"][position["entry"]],
                        "exit_session": market["sessions"][i],
                        "quantity": position["quantity"],
                        "entry_notional": position["notional"],
                        "exit_notional": value,
                        "entry_fee": position["entry_fee"],
                        "exit_fee": exit_fee,
                        "gross_pnl": value - position["notional"],
                        "net_pnl": profit,
                        "net_return": profit / position["notional"],
                        "holding_sessions": i - position["entry"],
                        "holding_calendar_days": days,
                        "settlement_index": int(market["settlement_index"][i]),
                    }
                )
            del held[j]
        nav = cash + sum(marks.values())
        for order in pending:
            j = order["symbol_index"]
            price = market["close"][i, j]
            if not np.isfinite(price) or price <= 0:
                missing.append(f"{market['symbols'][j]}:{market['sessions'][i]}:entry")
                break
            quantity = int(
                min(
                    order["quantity"],
                    math.floor(0.2 * nav / (price * (1 + half_cost))),
                    math.floor(max(0.0, settled) / (price * (1 + half_cost))),
                )
            )
            if not quantity:
                activity["zero_fill_orders"] += 1
                continue
            adjusted = market["adjusted"][i, j]
            if not np.isfinite(adjusted) or adjusted <= 0:
                missing.append(f"{market['symbols'][j]}:{market['sessions'][i]}:entry_adjustment")
                break
            notional = quantity * price
            fee = notional * half_cost
            cash -= notional + fee
            settled -= notional + fee
            if min(cash, settled) < -1e-7 or len(held) >= 5 or j in held:
                raise ArithmeticError("Daily cash portfolio violated cash or position constraints")
            cash, settled = max(0.0, cash), max(0.0, settled)
            held[j] = {
                "signal": order["signal"],
                "entry": i,
                "exit": i + horizon,
                "quantity": quantity,
                "notional": notional,
                "adjusted_entry": adjusted,
                "entry_fee": fee,
            }
            marks[j] = notional
            fees += fee
            traded_notional += notional
            nav -= fee
            activity["filled_positions"] += 1
        if missing:
            break
        pending = []
        offset = i - start
        path["equity"][offset] = cash + sum(marks.values())
        path["cash"][offset] = cash
        path["settled_cash"][offset] = settled
        path["unsettled_cash"][offset] = sum(amount for _, amount in receivables)
        if abs(cash - settled - path["unsettled_cash"][offset]) > 1e-6 * max(1, cash):
            raise ArithmeticError("Cash settlement ledger failed to reconcile")
        if strategy == "cash" or i + 1 + horizon > end:
            activity["boundary_or_cash_sessions"] += 1
            continue
        activity["screened_sessions"] += 1
        slots = 5 - sum(position["exit"] > i + 1 for position in held.values())
        if not slots:
            activity["no_free_slots_sessions"] += 1
            continue
        available = settled + sum(amount for due, amount in receivables if due <= i + 1)
        if available <= 0:
            activity["insufficient_settled_cash_sessions"] += 1
            continue
        if strategy.endswith("_market_trend"):
            if not market["market_trend_known"][i]:
                missing.append(f"{market['benchmark_symbol']}:{market['sessions'][i]}:regime_200")
                for values in path.values():
                    values[offset:] = np.nan
                break
            if not market["market_trend"][i]:
                activity["market_regime_off_sessions"] += 1
                continue
        if signal_known is not None and not signal_known[i]:
            missing.append(f"{market['benchmark_symbol']}:{market['sessions'][i]}:signal_input")
            for values in path.values():
                values[offset:] = np.nan
            break
        family = strategy.removesuffix("_market_trend")
        ranking = market["ranking"][family] if signal_ranking is None else signal_ranking
        counts = market["counts"][family] if signal_counts is None else signal_counts
        ranked = ranking[i, : counts[i]]
        if not len(ranked):
            activity["no_signal_sessions"] += 1
            continue
        activity["eligible_signal_sessions"] += 1
        ranked = ranked[~np.isin(ranked, list(held))]
        prices, atrs = market["close"][i, ranked], market["atr"][i, ranked]
        planned = np.floor(
            np.minimum(0.2 * nav / (prices * (1 + half_cost)), 0.005 * nav / (2 * atrs))
        )
        affordable = (planned > 0) & (prices * (1 + half_cost) <= available)
        for j, planned_quantity in zip(ranked[affordable], planned[affordable]):
            j = int(j)
            if correlation_limit is not None:
                peers = list(held) + [order["symbol_index"] for order in pending]
                if not _diversified(market["adjusted"], i, j, peers, correlation_limit):
                    activity["correlation_rejected_candidates"] += 1
                    continue
            price = market["close"][i, j]
            quantity = math.floor(min(planned_quantity, available / (price * (1 + half_cost))))
            if quantity <= 0:
                continue
            pending.append({"symbol_index": j, "quantity": quantity, "signal": i})
            available -= quantity * price * (1 + half_cost)
            if len(pending) >= slots:
                break
        activity["planned_orders"] += len(pending)
        if not pending:
            activity["unaffordable_or_held_signal_sessions"] += 1
    return {
        **path,
        "status": "incomplete" if missing else "complete" if length else "insufficient_history",
        "missing": missing,
        "fees": fees,
        "trades": completed_trades,
        "trade_records": records,
        "audit_retained": audit,
        "tallies": tallies,
        "traded_notional": traded_notional,
        "net_pnl_total": net_pnl,
        "activity": dict(activity),
        "state": {"cash": cash, "settled_cash": settled, "receivables": receivables},
    }


def _period_returns(equity, sessions, budget):
    dates = pd.DatetimeIndex(sessions)
    iso = dates.isocalendar()
    labels = {
        "weekly": [f"{year}-W{week:02}" for year, week in zip(iso.year, iso.week)],
        "monthly": dates.strftime("%Y-%m").tolist(),
    }
    details, summaries = {}, {}
    for frequency, values in labels.items():
        ends = [i for i in range(len(values)) if i == len(values) - 1 or values[i] != values[i + 1]]
        previous = budget
        rows = []
        for i in ends:
            rows.append(
                {
                    "period": values[i],
                    "last_session": sessions[i],
                    "return": float(equity[i] / previous - 1),
                }
            )
            previous = equity[i]
        returns = np.array([row["return"] for row in rows])
        summaries[frequency] = {
            "count": len(rows),
            "profitable_fraction": float(np.mean(returns > 0)) if len(rows) else None,
            "mean_return": float(np.mean(returns)) if len(rows) else None,
            "median_return": float(np.median(returns)) if len(rows) else None,
            "worst_return": float(np.min(returns)) if len(rows) else None,
            "best_return": float(np.max(returns)) if len(rows) else None,
            "p05_return": float(np.quantile(returns, 0.05)) if len(rows) else None,
        }
        details[frequency] = rows
    return details, summaries


def _summarize(simulation, sessions, budget, *, curves=True):
    result = _metrics(simulation, sessions, budget, curves=curves)
    result.update(activity=simulation["activity"], audit_retained=simulation["audit_retained"])
    if simulation["audit_retained"]:
        result["trade_records"] = simulation["trade_records"]
    keys = (
        "net_expectancy_native",
        "net_expectancy_return",
        "win_rate",
        "average_win_native",
        "average_loss_native",
        "profit_factor",
        "turnover",
        "annualized_turnover",
        "mean_exposure_fraction",
        "invested_session_fraction",
        "mean_holding_sessions",
        "max_holding_sessions",
        "mean_holding_calendar_days",
        "max_holding_calendar_days",
        "trades_per_week",
        "net_pnl_total",
        "consecutive_losses",
        "worst_day_return",
        "p05_trade_return",
        "max_drawdown_duration_sessions",
        "mean_settled_cash_fraction",
    )
    metrics = {key: None for key in keys}
    metrics.update(completed_trades=simulation["trades"], fees=simulation["fees"])
    result.update(trade_metrics=metrics, period_metrics={}, period_returns={})
    if curves:
        for row, settled, unsettled in zip(
            result["equity_curve"], simulation["settled_cash"], simulation["unsettled_cash"]
        ):
            row.update(
                settled_cash=float(settled) if np.isfinite(settled) else None,
                unsettled_cash=float(unsettled) if np.isfinite(unsettled) else None,
            )
    if simulation["status"] != "complete" or not len(sessions):
        return result
    equity, cash = simulation["equity"], simulation["cash"]
    tallies = simulation["tallies"]
    pnl, returns = np.array(tallies["pnl"]), np.array(tallies["returns"])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    years = max((pd.Timestamp(sessions[-1]) - pd.Timestamp(sessions[0])).days / 365.25, 1 / 365.25)
    streak = longest = duration = longest_duration = 0
    for value in pnl:
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    for underwater in equity < np.maximum.accumulate(equity):
        duration = duration + 1 if underwater else 0
        longest_duration = max(longest_duration, duration)
    turnover = simulation["traded_notional"] / float(np.mean(equity))
    metrics.update(
        net_expectancy_native=float(pnl.mean()) if len(pnl) else None,
        net_expectancy_return=float(returns.mean()) if len(returns) else None,
        win_rate=float(np.mean(pnl > 0)) if len(pnl) else None,
        average_win_native=float(wins.mean()) if len(wins) else None,
        average_loss_native=float(losses.mean()) if len(losses) else None,
        profit_factor=float(wins.sum() / -losses.sum()) if len(losses) else None,
        turnover=turnover,
        annualized_turnover=turnover / years,
        mean_exposure_fraction=float(np.mean(1 - cash / equity)),
        invested_session_fraction=float(np.mean(equity - cash > 1e-8)),
        mean_settled_cash_fraction=float(np.mean(simulation["settled_cash"] / equity)),
        mean_holding_sessions=float(np.mean(tallies["holds"])) if len(pnl) else None,
        max_holding_sessions=max(tallies["holds"]) if len(pnl) else None,
        mean_holding_calendar_days=float(np.mean(tallies["days"])) if len(pnl) else None,
        max_holding_calendar_days=max(tallies["days"]) if len(pnl) else None,
        trades_per_week=simulation["trades"] / (len(sessions) / 5),
        net_pnl_total=simulation["net_pnl_total"],
        consecutive_losses=longest,
        worst_day_return=float(np.min(equity[1:] / equity[:-1] - 1)) if len(equity) > 1 else None,
        p05_trade_return=float(np.quantile(returns, 0.05)) if len(returns) else None,
        max_drawdown_duration_sessions=longest_duration,
    )
    result["period_returns"], result["period_metrics"] = _period_returns(equity, sessions, budget)
    result["profit_concentration"] = {
        "best_symbols": sorted(tallies["symbols"].items(), key=lambda item: (-item[1], item[0]))[
            :10
        ],
        "worst_symbols": sorted(tallies["symbols"].items(), key=lambda item: (item[1], item[0]))[
            :10
        ],
    }
    return result


def _choose_daily(market, budget, start, end):
    candidates = []
    for strategy in FAMILIES:
        for horizon in HORIZONS:
            simulation = _simulate_daily(
                market, strategy, horizon, budget, max(COSTS), start, end, statistics=False
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
            if simulation["status"] == "complete":
                equity = simulation["equity"]
                ends = [equity[TRAINING_BLOCK - 1], equity[2 * TRAINING_BLOCK - 1], equity[-1]]
                returns = np.array(ends) / np.array([budget, *ends[:-1]]) - 1
                score = float(np.median(returns) - 0.5 * metrics["max_drawdown"])
                row.update(
                    score=score,
                    training_block_returns=returns.tolist(),
                    eligible=bool(
                        simulation["trades"] >= 12
                        and (returns > 0).sum() >= 2
                        and metrics["max_drawdown"] <= 0.3
                        and score > 0
                    ),
                )
            candidates.append(row)
    eligible = sorted(
        (row for row in candidates if row["eligible"]),
        key=lambda row: (-row["score"], row["strategy"], row["horizon"]),
    )
    return eligible[0] if eligible else {"strategy": "cash", "horizon": 1, "score": 0.0}, candidates


def _walk_daily(market, budget, currency, progress):
    first_test, n = WARMUP + TRAINING, market["n"]
    accounts = {
        cost: {"state": None, "parts": [], "folds": [], "incomplete": False} for cost in COSTS
    }
    for start in range(first_test, n, TESTING):
        end = min(n - 1, start + TESTING - 1)
        selected, candidates = _choose_daily(market, budget, start - TRAINING, start - 1)
        for cost, account in accounts.items():
            if account["incomplete"]:
                continue
            starting = account["state"]["cash"] if account["state"] is not None else budget
            simulation = _simulate_daily(
                market,
                selected["strategy"],
                selected["horizon"],
                starting,
                cost,
                start,
                end,
                state=account["state"],
                audit=True,
            )
            metrics = _metrics(
                simulation, market["sessions"][start : end + 1], starting, curves=False
            )
            account["parts"].append(simulation)
            account["incomplete"] = simulation["status"] != "complete"
            account["state"] = simulation["state"]
            account["folds"].append(
                {
                    "training_start": market["sessions"][start - TRAINING],
                    "training_end": market["sessions"][start - 1],
                    "test_start": market["sessions"][start],
                    "test_end": market["sessions"][end],
                    "selected_strategy": selected["strategy"],
                    "selected_horizon": selected["horizon"],
                    "training_score": selected["score"],
                    "selection_candidates": candidates,
                    "test_return": metrics["total_return"],
                    "test_status": simulation["status"],
                    "starting_equity": starting,
                    "ending_equity": metrics["ending_equity"],
                }
            )
        _notify(
            progress,
            stage="short_horizon_walk_forward",
            currency=currency,
            budget=budget,
            test_start=market["sessions"][start],
        )
    results = []
    for cost, account in accounts.items():
        parts = account["parts"]
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
            if account["incomplete"]
            else "complete"
            if parts
            else "insufficient_history",
            missing=[missing for part in parts for missing in part["missing"]],
            fees=sum(part["fees"] for part in parts),
            trades=sum(part["trades"] for part in parts),
            traded_notional=sum(part["traded_notional"] for part in parts),
            net_pnl_total=sum(part["net_pnl_total"] for part in parts),
            tallies=tallies,
            activity=dict(activity),
            audit_retained=True,
            trade_records=[record for part in parts for record in part["trade_records"]],
        )
        sessions = market["sessions"][first_test : first_test + len(combined["equity"])]
        reference = _benchmark(market, budget, cost, first_test, n - 1)
        results.append(
            {
                "currency": currency,
                "budget": budget,
                "cost_bps": cost,
                **_summarize(combined, sessions, budget),
                "folds": account["folds"],
                "benchmark": _metrics(reference, market["sessions"][first_test:n], budget),
            }
        )
    return results


def _methodology(budgets):
    return {
        **CONFIG,
        "budgets": list(budgets),
        "cost_bps": list(COSTS),
        "model_signature": "sha256:"
        + hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest(),
        "attempts": [
            {"strategy": strategy, "horizon": horizon, "description": description}
            for strategy, description in FAMILIES.items()
            for horizon in HORIZONS
        ],
        "limitations": [
            "Retrospective study designed after prior research; current membership omits "
            "delisted firms.",
            "Signals use today's adjusted data vintage; availability is imputed at close "
            "plus one minute.",
            "Nominal historical prices are reconstructed from reported splits; missing "
            "actions can distort sizing.",
            "Synthetic total-return marks are anchored to entry notional, not a "
            "corporate-action cash ledger.",
            "Daily close signals fill at the next session close. A one-session hold is "
            "overnight, not intraday.",
            "Each stock exits after 1, 3 or 5 close-to-close intervals. There are no "
            "intraday stops.",
            "Daily screening uses unused settled cash and independent position slots; no "
            "margin or fractional shares.",
            SETTLEMENT_ASSUMPTION,
            "Rank-priority fills share settled cash; entry gaps can reduce quantities in "
            "later planned orders.",
            "A held symbol is not replanned for re-entry until its previous position has closed.",
            "Twenty-percent position limits apply at entry; later price changes can increase "
            "position weights.",
            "Three-year training and one-year rule selection do not change the daily "
            "decision or short holding cadence.",
            "Selection retains the legacy stressed-cost score and 12-trade threshold for a "
            "controlled comparison.",
            "No new position crosses a test-fold boundary; unsettled proceeds carry into the "
            "next fold.",
            "Missing held or required signal data invalidate the account; incomplete "
            "accounts have no profitability aggregates.",
            "Fixed-grid records retain aggregate statistics. evaluate_short_horizon_view "
            "replays one view with trade detail; rolling accounts retain every completed "
            "trade.",
            "Turnover is two-way executed notional divided by average daily equity, "
            "expressed as a multiple.",
            "Weekly and monthly returns include cash; first and last periods may be partial. "
            "Trades per week uses five sessions.",
            "Costs are proportional entry and exit charges; fixed broker fees, taxes, FX, "
            "interest and contributions are excluded.",
            "All attempts are reported; no passing backtest guarantees profit or a 30% "
            "maximum loss.",
        ],
    }


def evaluate_short_horizon(
    frame, universe, *, as_of, budgets=(500, 2000, 10000, 100000), progress=None
):
    """Run fixed hypotheses and rolling selection with daily cash-ledger decisions."""
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
    }
    for currency in BOOKS:
        if not any(spec["currency"] == currency for spec in universe):
            continue
        market = _market_data(frame, universe, current, currency, progress)
        n = market["n"]
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
        for budget in budgets:
            for cost in COSTS:
                for symbol in (market["benchmark_symbol"], "CASH"):
                    simulation = (
                        _benchmark(market, budget, cost, WARMUP, n - 1)
                        if symbol != "CASH"
                        else _simulate_daily(market, "cash", 1, budget, cost, WARMUP, n - 1)
                    )
                    result["benchmarks"].append(
                        {
                            "currency": currency,
                            "budget": budget,
                            "cost_bps": cost,
                            "symbol": symbol,
                            **_metrics(simulation, market["sessions"][WARMUP:n], budget),
                        }
                    )
                for attempt in result["methodology"]["attempts"]:
                    simulation = _simulate_daily(
                        market, attempt["strategy"], attempt["horizon"], budget, cost, WARMUP, n - 1
                    )
                    result["portfolios"].append(
                        {
                            "currency": currency,
                            "budget": budget,
                            "cost_bps": cost,
                            "strategy": attempt["strategy"],
                            "horizon": attempt["horizon"],
                            **_summarize(simulation, market["sessions"][WARMUP:n], budget),
                        }
                    )
            _notify(progress, stage="short_horizon_portfolios", currency=currency, budget=budget)
            result["walk_forward"].extend(_walk_daily(market, budget, currency, progress))
        del market
        gc.collect()
    return result


def evaluate_short_horizon_view(
    frame, universe, *, as_of, currency, budget, cost_bps, strategy, horizon
):
    """Deterministically replay one declared fixed-grid view with complete trade details."""
    if (
        currency not in BOOKS
        or cost_bps not in COSTS
        or strategy not in FAMILIES
        or horizon not in HORIZONS
    ):
        raise ValueError("View must identify a declared currency, cost, strategy and horizon")
    _, specs, current, budgets = _prepare(frame.iloc[:0], universe, as_of, (budget,))
    if set(frame.symbol.unique()) - specs.keys():
        raise ValueError("Data contains symbols outside the declared universe")
    market = _market_data(frame, universe, current, currency, None)
    simulation = _simulate_daily(
        market, strategy, horizon, budgets[0], cost_bps, WARMUP, market["n"] - 1, audit=True
    )
    return {
        "currency": currency,
        "budget": budgets[0],
        "cost_bps": cost_bps,
        "strategy": strategy,
        "horizon": horizon,
        **_summarize(simulation, market["sessions"][WARMUP : market["n"]], budgets[0]),
    }
