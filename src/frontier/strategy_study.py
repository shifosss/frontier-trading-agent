"""Fixed-rule, cash-weighted forward cohorts; never a portfolio backtest or order engine."""

from __future__ import annotations

import hashlib
import json
import math

import exchange_calendars as xcals
import numpy as np
import pandas as pd

STRATEGIES = {
    "momentum": "Positive 20/60-session momentum, above 50-day mean; momentum / volatility rank",
    "trend_pullback": "Above 200-day mean with negative 5-day momentum; pullback / volatility rank",
    "mean_reversion": "Above 200-day mean and 20-day z-score below -1.5; lowest z-score first",
    "breakout": "Close at or above the previous 55-session maximum close; breakout distance rank",
}
HORIZONS = (5, 10, 20)
COSTS = (20, 40, 100)
BOOKS = {"USD": ("XNYS", "SPY", 5_000_000), "CAD": ("XTSE", "XIU.TO", 1_000_000)}
FIELDS = ("close", "adjusted_close", "high", "low", "volume")
CONFIG = {
    "version": "broad-cohort-study-v1",
    "minimum_consecutive_sessions": 201,
    "maximum_names": 5,
    "position_budget_fraction": 0.20,
    "atr_risk_budget_fraction": 0.005,
    "atr_sessions": 14,
    "atr_risk_multiple": 2,
    "liquidity_sessions": 20,
    "minimum_native_dollar_volume": {currency: book[2] for currency, book in BOOKS.items()},
    "horizons": list(HORIZONS),
    "round_trip_cost_bps": list(COSTS),
    "chronological_partition_fractions": [0.60, 0.20, 0.20],
    "strategies": STRATEGIES,
}

MODEL_SIGNATURE = (
    "sha256:"
    + hashlib.sha256(json.dumps(CONFIG, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
)


def _prepare(frame, universe, as_of, budgets):
    current = pd.Timestamp(as_of)
    if pd.isna(current) or current.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    current = current.tz_convert("UTC")
    budgets = tuple(float(value) for value in budgets)
    if not budgets or len(set(budgets)) != len(budgets):
        raise ValueError("Specify distinct positive native-currency budgets")
    if any(not math.isfinite(value) or value <= 0 for value in budgets):
        raise ValueError("Budgets must be finite and positive")
    specs = {spec["symbol"]: spec for spec in universe}
    if len(specs) != len(universe) or not specs:
        raise ValueError("Universe must contain distinct symbols")
    for spec in universe:
        if spec["currency"] not in BOOKS or spec["calendar"] != BOOKS[spec["currency"]][0]:
            raise ValueError("Supported books are USD/XNYS and CAD/XTSE")
        if spec["asset_type"] not in {"stock", "etf"}:
            raise ValueError("Study instruments must be stocks or ETF benchmarks")
    required = {"symbol", "session", "available_at", *FIELDS}
    if not required <= set(frame):
        raise ValueError(f"Missing study columns: {sorted(required - set(frame))}")
    data = frame.loc[:, sorted(required)].copy()
    if set(data.symbol) - specs.keys():
        raise ValueError("Data contains symbols outside the declared universe")
    data["session"] = pd.to_datetime(data.session, errors="raise").dt.strftime("%Y-%m-%d")
    if data.duplicated(["symbol", "session"]).any():
        raise ValueError("Study requires one observation per symbol/session")
    aware = data.available_at.astype(str).str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    data["available_at"] = pd.to_datetime(data.available_at, utc=True, errors="coerce")
    data[list(FIELDS)] = data[list(FIELDS)].apply(pd.to_numeric, errors="coerce")
    values = data[list(FIELDS)].to_numpy(dtype=float)
    valid = (
        np.isfinite(values).all(axis=1)
        & (values[:, :4] > 0).all(axis=1)
        & (values[:, 4] >= 0)
        & (data.low <= data.close)
        & (data.close <= data.high)
        & aware
        & data.available_at.notna()
    )
    data["valid"] = valid
    data["available"] = data.available_at <= current
    return data, specs, current, budgets


def _market(data, specs, current, currency):
    calendar_name, benchmark, liquidity = BOOKS[currency]
    symbols = sorted(symbol for symbol, spec in specs.items() if spec["currency"] == currency)
    history = data.loc[data.symbol.isin(symbols)]
    dated = history.loc[history.available & (history.session <= current.date().isoformat())]
    first = dated.session.min() if len(dated) else current.date().isoformat()
    calendar = xcals.get_calendar(
        calendar_name,
        start=str(pd.Timestamp(first).date() - pd.Timedelta(days=400)),
        end=str(current.date() + pd.Timedelta(days=90)),
    )
    schedule = calendar.schedule.loc[first:]
    available = schedule["close"] + pd.Timedelta(minutes=1)
    completed = available <= current
    sessions = schedule.index.strftime("%Y-%m-%d")
    n = int(completed.sum())
    index = pd.Index(sessions[:n], name="session")
    closes = pd.Series(available.to_numpy(), index=sessions)
    expected = pd.to_datetime(history.session.map(closes), utc=True)
    # A delayed/invalid daily observation never silently becomes a historical signal input.
    accepted = history.loc[
        history.valid & history.available & expected.notna() & (history.available_at <= expected)
    ]
    matrices = {
        field: accepted.pivot(index="session", columns="symbol", values=field).reindex(
            index=index, columns=symbols
        )
        for field in FIELDS
    }
    close, prices = matrices["close"], matrices["adjusted_close"]
    complete = prices.notna().rolling(201, min_periods=201).sum().eq(201)
    turnover = (close * matrices["volume"]).rolling(20, min_periods=20).mean()
    volatility = prices.pct_change(fill_method=None).rolling(20).std() * np.sqrt(252)
    factor = prices / close
    high, low = matrices["high"] * factor, matrices["low"] * factor
    previous = prices.shift()
    true_range = np.maximum.reduce(
        [
            (high - low).to_numpy(),
            (high - previous).abs().to_numpy(),
            (low - previous).abs().to_numpy(),
        ]
    )
    atr = pd.DataFrame(true_range, index=index, columns=symbols).rolling(14).mean() / factor
    stock = np.array([specs[symbol]["asset_type"] == "stock" for symbol in symbols])
    eligible = complete & turnover.ge(liquidity) & atr.gt(0) & volatility.gt(1e-12) & stock
    m5, m20, m60 = (prices / prices.shift(days) - 1 for days in (5, 20, 60))
    ma20, ma50, ma200 = (prices.rolling(days).mean() for days in (20, 50, 200))
    zscore = (prices - ma20) / prices.rolling(20).std()
    prior_max = prices.shift().rolling(55).max()
    scores = {
        "momentum": ((m20 + m60) / (2 * volatility))
        .where(eligible & m20.gt(0) & m60.gt(0) & prices.gt(ma50))
        .to_numpy(),
        "trend_pullback": (-m5 / volatility)
        .where(eligible & prices.gt(ma200) & m5.lt(0))
        .to_numpy(),
        "mean_reversion": (-zscore).where(eligible & prices.gt(ma200) & zscore.lt(-1.5)).to_numpy(),
        "breakout": (prices / prior_max - 1).where(eligible & prices.ge(prior_max)).to_numpy(),
    }
    coverage = []
    present = close.notna().to_numpy()
    for j, symbol in enumerate(symbols):
        positions = np.flatnonzero(present[:, j])
        count = len(positions)
        coverage.append(
            {
                "symbol": symbol,
                "currency": currency,
                "valid_completed_rows": count,
                "first_session": sessions[positions[0]] if count else None,
                "last_session": sessions[positions[-1]] if count else None,
                "missing_sessions_between_first_and_last": (
                    int(positions[-1] - positions[0] + 1 - count) if count else 0
                ),
                "latest_201_complete": bool(complete.iloc[-1, j]) if n else False,
                "latest_liquid": bool(turnover.iloc[-1, j] >= liquidity) if n else False,
            }
        )
    cuts = (int(n * 0.6), int(n * 0.8))
    boundaries = (0, *cuts, n)
    periods = {
        name: {
            "first_session": sessions[a] if a < b else None,
            "last_session": sessions[b - 1] if a < b else None,
            "sessions": b - a,
        }
        for name, a, b in zip(
            ("development", "validation", "evaluation"), boundaries, boundaries[1:]
        )
    }
    return {
        "symbols": symbols,
        "sessions": sessions.tolist(),
        "n": n,
        "cuts": cuts,
        "close": close.to_numpy(),
        "adjusted": prices.to_numpy(),
        "atr": atr.to_numpy(),
        "turnover": turnover.to_numpy(),
        "scores": scores,
        "coverage": coverage,
        "periods": periods,
        "benchmark": symbols.index(benchmark) if benchmark in symbols else None,
        "benchmark_symbol": benchmark,
        "discarded_rows": len(history) - len(accepted.loc[accepted.session.isin(index)]),
    }


def _ranking(scores):
    # Symbol columns are alphabetical: stable sorting gives a reproducible tie break.
    return np.argsort(-np.where(np.isfinite(scores), scores, -np.inf), kind="stable")[
        : np.isfinite(scores).sum()
    ]


def _quantities(budget, close, atr):
    with np.errstate(divide="ignore", invalid="ignore"):
        quantities = np.floor(
            np.minimum(0.2 * budget / (close * 1.001), 0.005 * budget / (2 * atr))
        )
    return np.where(np.isfinite(quantities) & (quantities > 0), quantities, 0).astype(np.int64)


def _cohort(market, strategy, horizon, i, budget, selected, planned):
    n, sessions = market["n"], market["sessions"]
    entry, exit_ = i + 1, i + 1 + horizon
    period_id = int(np.searchsorted(market["cuts"], i, side="right"))
    result = {
        "strategy": strategy,
        "horizon": horizon,
        "budget": budget,
        "signal_session": sessions[i],
        "entry_session": sessions[entry],
        "exit_session": sessions[exit_],
        "period": ("development", "validation", "evaluation")[period_id],
        "selected": [market["symbols"][j] for j in selected],
        "planned_quantities": planned.tolist(),
        "status": "complete",
        "missing": [],
        "returns_by_cost": {},
    }
    if exit_ >= n:
        result["status"] = "pending"
        return result
    if period_id != np.searchsorted(market["cuts"], exit_, side="right"):
        result["status"] = "purged_boundary"
        return result
    raw, adjusted = market["close"], market["adjusted"]
    needed = list(selected)
    benchmark = market["benchmark"]
    if benchmark is None:
        result["missing"].append(market["benchmark_symbol"] + ":benchmark_absent")
    else:
        needed.append(benchmark)
    for j in needed:
        for when, label in ((entry, "entry"), (exit_, "exit")):
            if not np.isfinite(raw[when, j]) or not np.isfinite(adjusted[when, j]):
                result["missing"].append(market["symbols"][j] + ":" + label)
    if result["missing"]:
        result["status"] = "incomplete"
        return result
    entry_price = raw[entry, selected]
    adjusted_returns = adjusted[exit_, selected] / adjusted[entry, selected] - 1
    benchmark_price = raw[entry, benchmark]
    benchmark_return = adjusted[exit_, benchmark] / adjusted[entry, benchmark] - 1
    result["returns_by_cost"] = cash_weighted_returns(
        budget, planned, entry_price, adjusted_returns, benchmark_price, benchmark_return
    )
    return result


def cash_weighted_returns(
    budget, planned, entry_prices, adjusted_returns, benchmark_price, benchmark_return
):
    """Shared historical/forward arithmetic; callers validate observation completeness."""
    entry_prices = np.asarray(entry_prices, dtype=float)
    adjusted_returns = np.asarray(adjusted_returns, dtype=float)
    planned = np.asarray(planned, dtype=int)
    result = {}
    for cost in COSTS:
        fraction = cost / 10_000
        # Orders were sized at the signal. At entry, only reduce for price gaps and fees.
        filled = np.minimum(planned, np.floor(0.2 * budget / (entry_prices * (1 + fraction / 2))))
        weights = filled * entry_prices / budget
        benchmark_quantity = math.floor(budget / (benchmark_price * (1 + fraction / 2)))
        benchmark_weight = benchmark_quantity * benchmark_price / budget
        net = float(np.sum(weights * (adjusted_returns - fraction)))
        bench = float(benchmark_weight * (benchmark_return - fraction))
        result[str(cost)] = {
            "return": net,
            "benchmark_return": bench,
            "excess_return": net - bench,
            "invested_fraction": float(weights.sum()),
            "estimated_round_trip_cost": float(weights.sum() * budget * fraction),
            "filled_quantities": filled.astype(int).tolist(),
            "benchmark_quantity": benchmark_quantity,
        }
    return result


def _summaries(cohorts, currencies, budgets):
    groups = {}
    for row in cohorts:
        key = (row["currency"], row["strategy"], row["horizon"], row["budget"], row["period"])
        groups.setdefault(key, []).append(row)
    summaries = []
    for currency in currencies:
        for strategy in STRATEGIES:
            for horizon in HORIZONS:
                for budget in budgets:
                    for period in ("development", "validation", "evaluation"):
                        rows = groups.get((currency, strategy, horizon, budget, period), [])
                        complete = [row for row in rows if row["status"] == "complete"]
                        for cost in COSTS:
                            values = [row["returns_by_cost"][str(cost)] for row in complete]
                            summaries.append(
                                {
                                    "currency": currency,
                                    "strategy": strategy,
                                    "horizon": horizon,
                                    "budget": budget,
                                    "period": period,
                                    "cost_bps": cost,
                                    "scheduled_cohorts": len(rows),
                                    "complete_cohorts": len(complete),
                                    "incomplete_cohorts": sum(
                                        r["status"] == "incomplete" for r in rows
                                    ),
                                    "purged_cohorts": sum(
                                        r["status"] == "purged_boundary" for r in rows
                                    ),
                                    "pending_cohorts": sum(r["status"] == "pending" for r in rows),
                                    "cash_only_cohorts": sum(
                                        not any(v["filled_quantities"]) for v in values
                                    ),
                                    "mean_return": _mean(values, "return"),
                                    "mean_benchmark_return": _mean(values, "benchmark_return"),
                                    "mean_excess_return": _mean(values, "excess_return"),
                                    "mean_invested_fraction": _mean(values, "invested_fraction"),
                                    "win_rate": float(np.mean([v["return"] > 0 for v in values]))
                                    if values
                                    else None,
                                    "benchmark_win_rate": float(
                                        np.mean([v["excess_return"] > 0 for v in values])
                                    )
                                    if values
                                    else None,
                                }
                            )
    return summaries


def _mean(values, key):
    return float(np.mean([value[key] for value in values])) if values else None


def evaluate_strategies(frame, universe, *, as_of, budgets=(500, 2000, 10000, 100000)):
    """Evaluate all fixed attempts with independent native-currency cash budgets.

    Return JSON-serializable methodology, coverage, summaries, cohort audit records and
    latest candidates. Each cohort starts with fresh cash; returns must not be compounded
    or annualized as if they describe an executable portfolio.
    """
    data, specs, current, budgets = _prepare(frame, universe, as_of, budgets)
    currencies = [
        currency for currency in BOOKS if any(s["currency"] == currency for s in universe)
    ]
    cohorts, latest, coverage, periods = [], [], [], {}
    market_coverage = []
    for currency in currencies:
        market = _market(data, specs, current, currency)
        coverage.extend(market["coverage"])
        periods[currency] = market["periods"]
        n = market["n"]
        market_coverage.append(
            {
                "currency": currency,
                "calendar_sessions": n,
                "latest_completed_session": market["sessions"][n - 1] if n else None,
                "discarded_or_unavailable_rows": market["discarded_rows"],
                "stock_count": sum(specs[s]["asset_type"] == "stock" for s in market["symbols"]),
            }
        )
        for strategy, scores in market["scores"].items():
            if n:
                ranking = _ranking(scores[-1])
                current_quantities = {
                    str(int(budget) if budget.is_integer() else budget): _quantities(
                        budget, market["close"][-1], market["atr"][-1]
                    )
                    for budget in budgets
                }
                for rank, j in enumerate(ranking, 1):
                    latest.append(
                        {
                            "currency": currency,
                            "strategy": strategy,
                            "symbol": market["symbols"][j],
                            "session": market["sessions"][n - 1],
                            "rank": rank,
                            "score": float(scores[-1, j]),
                            "price": float(market["close"][-1, j]),
                            "atr_14": float(market["atr"][-1, j]),
                            "average_dollar_volume_20": float(market["turnover"][-1, j]),
                            "quantities_by_budget": {
                                key: int(q[j]) for key, q in current_quantities.items()
                            },
                        }
                    )
            rankings = {i: _ranking(scores[i]) for i in range(200, n, 5)}
            for horizon in HORIZONS:
                for i in range(200, n, horizon):
                    ranking = rankings[i]
                    for budget in budgets:
                        quantities = _quantities(budget, market["close"][i], market["atr"][i])
                        selected = ranking[quantities[ranking] > 0][:5]
                        row = _cohort(
                            market, strategy, horizon, i, budget, selected, quantities[selected]
                        )
                        row["currency"] = currency
                        cohorts.append(row)
    return {
        "schema_version": 1,
        "as_of": current.isoformat(),
        "methodology": {
            "model_signature": MODEL_SIGNATURE,
            "config": CONFIG,
            "budgets": list(budgets),
            "periods": periods,
            "kind": "cash-weighted non-overlapping forward cohorts, not portfolio P&L",
            "entry": "Signal at completed close; buy next-session close; exit H sessions later",
            "sizing": "Rank at signal, select first five affordable stocks; whole shares, 20% "
            "cap and 0.5% budget / 2ATR risk; reduce only at entry for gap/fee affordability",
            "costs": "20/40/100 bps round trip on entry notional, half reserved for entry; "
            "zero fixed commission; same names and planned quantities in each stress",
            "benchmark": "SPY for USD and XIU.TO for CAD; whole-share full-budget cohort, "
            "same entry/exit and cost; uninvested cash earns zero",
            "partition": "Fixed calendar 60/20/20; purge signal-to-exit intervals "
            "crossing boundaries",
            "missing_data": "201 consecutive valid sessions per stock; no cross-stock completeness "
            "requirement. Missing selected entry/exit or benchmark invalidates "
            "the entire paired cohort; never drop just the losing/missing name",
            "limitations": [
                "Current-vintage adjusted data and current listing membership have revision and "
                "survivorship bias; this is not point-in-time or delisting-complete evidence.",
                "All chronological folds are exposed by this study; evaluation is not an "
                "untouched holdout.",
                "Historical whole-share affordability is unqualified before splits because "
                "provider "
                "OHLC can already be split-adjusted; adjusted returns are total-return proxies.",
                "Independent fixed-cash cohorts are not a continuous trading account; no CAGR, "
                "portfolio drawdown, financing, FX, taxes, intraday stops or execution guarantee.",
                "Four fixed families times three horizons are all disclosed; multiple testing "
                "does not establish edge and no winner is automatically promoted to the operator.",
                "Late/invalid/non-session data is excluded; a recent IPO or one gapped symbol "
                "does not block other stocks, but missing delisted histories remain unmeasured.",
            ],
        },
        "coverage": {"input_rows": len(data), "markets": market_coverage, "instruments": coverage},
        "attempts": [
            {"strategy": strategy, "horizon": horizon, "description": description}
            for strategy, description in STRATEGIES.items()
            for horizon in HORIZONS
        ],
        "summaries": _summaries(cohorts, currencies, budgets),
        "cohorts": cohorts,
        "latest_candidates": latest,
    }
