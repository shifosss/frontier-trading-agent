"""Fixed-policy watchlists and forward-return diagnostics, never broker instructions."""

from __future__ import annotations

import math
from collections import Counter

import exchange_calendars as xcals
import numpy as np
import pandas as pd

POLICY = {
    "version": "momentum-watchlist-v1",
    "score": "equal blend of 20/60-session adjusted momentum / 20-session annualized volatility",
    "momentum_sessions": [20, 60],
    "volatility_sessions": 20,
    "trend_sessions": 50,
    "minimum_sessions": 63,
    "active_asset_type": "stock",
    "minimum_average_dollar_volume": {"USD": 5_000_000, "CAD": 1_000_000},
    "maximum_per_currency": 5,
    "maximum_book_fraction": 0.20,
    "risk_book_fraction": 0.005,
    "atr_multiple": 2,
    "commission": 0.0,
    "fee_profile": "Wealthsimple listed stocks, existing currency balance",
    "fee_verified_at": "2026-09-18",
    "diagnostic_holding_sessions": 5,
    "diagnostic_entry": "next-session close",
    "diagnostic_round_trip_cost_bps": 20,
    "diagnostic_stressed_cost_bps": 40,
    "sizing_slippage_bps": 5,
}
LIMITATIONS = [
    "Watchlist and hypothetical sizing only; no executable quote, broker order or live readiness.",
    "Provider-adjusted historical prices and a current selected universe are retrospective, "
    "not point-in-time membership or an untouched holdout.",
    "Scores rank one fixed technical rule; they are not expected returns or profit probabilities.",
    "ATR is an adjusted-price range proxy scaled to the latest provider close; "
    "its risk distance is not a guaranteed stop execution price.",
    "One selection per declared exposure group does not establish correlation diversification.",
    "Stock selection only; ETF benchmarks do not change reserved ETF holdings. "
    "Options are not evaluated.",
]
REQUIRED_COLUMNS = {
    "symbol",
    "session",
    "available_at",
    "close",
    "adjusted_close",
    "high",
    "low",
    "volume",
}


def _timestamp(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("as_of must include an explicit timezone")
    return timestamp.tz_convert("UTC")


def _prepare(frame, universe, as_of, cash_by_currency):
    current = _timestamp(as_of)
    if not REQUIRED_COLUMNS <= set(frame.columns):
        raise ValueError(
            f"Missing scanner columns: {sorted(REQUIRED_COLUMNS - set(frame.columns))}"
        )
    if len({item["symbol"] for item in universe}) != len(universe):
        raise ValueError("Universe symbols must be unique")
    cash = {"USD": 0.0, "CAD": 700.0}
    if cash_by_currency is not None:
        if set(cash_by_currency) - set(cash):
            raise ValueError("Only USD and CAD cash books are supported")
        cash.update(cash_by_currency)
    cash = {currency: float(amount) for currency, amount in cash.items()}
    if any(not math.isfinite(amount) or amount < 0 for amount in cash.values()):
        raise ValueError("Cash budgets must be finite and nonnegative")
    data = frame.copy()
    data["session"] = pd.to_datetime(data.session, errors="raise").dt.strftime("%Y-%m-%d")
    data["available_at"] = pd.to_datetime(data.available_at, utc=True, errors="raise")
    if data.duplicated(["symbol", "session"]).any():
        raise ValueError("Scanner input must have one row per symbol/session")
    for column in ("close", "adjusted_close", "high", "low", "volume"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    data = data.loc[data.available_at <= current].sort_values(["symbol", "session"])
    start = (
        min(data.session.min(), current.date().isoformat())
        if len(data)
        else current.date().isoformat()
    )
    calendars = {
        name: xcals.get_calendar(
            name,
            start=str(pd.Timestamp(start).date() - pd.Timedelta(days=370)),
            end=str(current.date() + pd.Timedelta(days=30)),
        )
        for name in {item["calendar"] for item in universe} | {"XNYS", "XTSE"}
    }
    histories = {symbol: history for symbol, history in data.groupby("symbol", sort=False)}
    return data, current, cash, calendars, histories


def _expected_session(calendar, current):
    closed = calendar.schedule.loc[calendar.schedule["close"] + pd.Timedelta(minutes=1) <= current]
    return closed.index[-1].date().isoformat()


def _rank_rows(histories, universe, current, calendars):
    rows = []
    expected_histories = {
        name: calendar.schedule.index[
            calendar.schedule["close"] + pd.Timedelta(minutes=1) <= current
        ][-POLICY["minimum_sessions"] :]
        .strftime("%Y-%m-%d")
        .tolist()
        for name, calendar in calendars.items()
    }
    for spec in universe:
        if spec["currency"] not in {"USD", "CAD"}:
            raise ValueError("Universe currency must be USD or CAD")
        expected_history = expected_histories[spec["calendar"]]
        expected = expected_history[-1]
        history = histories.get(spec["symbol"])
        if history is not None:
            history = history.loc[
                (history.available_at <= current) & (history.session <= expected)
            ].tail(POLICY["minimum_sessions"])
        row = {
            **spec,
            "status": "excluded",
            "reasons": [],
            "last_session": None,
            "available_at": None,
            "expected_session": expected,
            "history_complete": False,
            "price": None,
            "momentum_20": None,
            "momentum_60": None,
            "annualized_volatility": None,
            "average_dollar_volume_20": None,
            "atr_14": None,
            "score": None,
            "rank": None,
            "quantity": 0,
            "estimated_notional": 0.0,
            "estimated_cost": 0.0,
            "allocation_fraction": 0.0,
            "sizing_reason": None,
        }
        rows.append(row)
        if history is None or history.empty:
            row["reasons"].append("No available completed-session observations")
            continue
        row["last_session"] = history.session.iloc[-1]
        row["available_at"] = history.available_at.iloc[-1].isoformat()
        if row["last_session"] != expected:
            row["reasons"].append(f"Stale data: expected completed session {expected}")
        if len(history) < POLICY["minimum_sessions"]:
            row["reasons"].append("Insufficient history: 63 completed sessions required")
            continue
        if expected_history != list(history.session):
            row["reasons"].append("Missing exchange sessions in the lookback window")
        required = history[["close", "adjusted_close", "volume"]].to_numpy(dtype=float)
        if (
            not np.isfinite(required).all()
            or (required[:, :2] <= 0).any()
            or (required[:, 2] < 0).any()
        ):
            row["reasons"].append("Invalid price or volume in lookback window")
            continue
        # Only data-quality reasons exist here; technical filters follow below.
        row["history_complete"] = not row["reasons"]
        prices = history.adjusted_close
        row["price"] = float(history.close.iloc[-1])
        row["momentum_20"] = float(prices.iloc[-1] / prices.iloc[-21] - 1)
        row["momentum_60"] = float(prices.iloc[-1] / prices.iloc[-61] - 1)
        volatility = float(prices.pct_change().iloc[-20:].std(ddof=1) * np.sqrt(252))
        row["annualized_volatility"] = volatility
        row["average_dollar_volume_20"] = float((history.close * history.volume).iloc[-20:].mean())
        if volatility <= 1e-12:
            row["reasons"].append("Zero realized volatility: ranking is undefined")
        else:
            row["score"] = (row["momentum_20"] + row["momentum_60"]) / (2 * volatility)
        if row["momentum_20"] <= 0 or row["momentum_60"] <= 0:
            row["reasons"].append("Both 20-session and 60-session momentum must be positive")
        if prices.iloc[-1] <= prices.iloc[-50:].mean():
            row["reasons"].append("Adjusted close is not above its 50-session mean")
        minimum = POLICY["minimum_average_dollar_volume"][spec["currency"]]
        if row["average_dollar_volume_20"] < minimum:
            row["reasons"].append(f"Average native dollar volume is below {minimum:,.0f}")
        ranges = history[["high", "low"]].to_numpy(dtype=float)
        if (
            np.isfinite(ranges).all()
            and (history.low > 0).all()
            and (history.high >= history.low).all()
        ):
            factors = prices / history.close
            high, low = history.high * factors, history.low * factors
            true_range = pd.concat(
                [high - low, (high - prices.shift()).abs(), (low - prices.shift()).abs()], axis=1
            ).max(axis=1)
            row["atr_14"] = float(true_range.iloc[-14:].mean() / factors.iloc[-1])
        if spec["asset_type"] != "stock":
            row["reasons"].append(
                "ETF retained as benchmark/context; active selection is stocks only"
            )
        if not row["reasons"]:
            row["status"] = "eligible"
    rows.sort(key=lambda row: (row["status"] == "excluded", -(row["score"] or 0), row["symbol"]))
    for rank, row in enumerate((row for row in rows if row["status"] == "eligible"), 1):
        row["rank"] = rank
    return rows


def _scan(histories, universe, current, cash, calendars):
    rows = _rank_rows(histories, universe, current, calendars)
    selection_coverage = {}
    for currency in cash:
        stocks = [
            row for row in rows if row["currency"] == currency and row["asset_type"] == "stock"
        ]
        unavailable = [row["symbol"] for row in stocks if not row["history_complete"]]
        selection_coverage[currency] = {
            "declared_stock_count": len(stocks),
            "evaluable_stock_count": len(stocks) - len(unavailable),
            "unavailable_symbols": unavailable,
        }
    remaining, counts, selected, groups = cash.copy(), Counter(), [], set()
    for row in rows:
        if row["status"] != "eligible":
            continue
        currency, price = row["currency"], row["price"]
        if row["group"] in groups:
            row["reasons"].append(
                "A higher-ranked instrument already represents this exposure group"
            )
            continue
        if counts[currency] >= POLICY["maximum_per_currency"]:
            row["reasons"].append("Maximum selections for this currency book reached")
            continue
        budget = min(remaining[currency], cash[currency] * POLICY["maximum_book_fraction"])
        quantity = max(
            0,
            math.floor(
                (budget - POLICY["commission"])
                / (price * (1 + POLICY["sizing_slippage_bps"] / 10_000))
            ),
        )
        sizing = "20% native-book cap, whole shares, estimated commission and slippage"
        if row["atr_14"] is not None and row["atr_14"] > 0:
            risk_quantity = math.floor(
                cash[currency]
                * POLICY["risk_book_fraction"]
                / (POLICY["atr_multiple"] * row["atr_14"])
            )
            quantity = min(quantity, risk_quantity)
            sizing += "; 0.5% native-book risk budget at 2 ATR"
        else:
            sizing += "; ATR unavailable, notional cap only"
        row["sizing_reason"] = sizing
        if quantity == 0:
            row["reasons"].append("No whole share fits the hypothetical cash and risk budgets")
            continue
        notional = quantity * price
        costs = POLICY["commission"] + notional * POLICY["sizing_slippage_bps"] / 10_000
        row.update(
            status="selected",
            quantity=quantity,
            estimated_notional=notional,
            estimated_cost=costs,
            allocation_fraction=notional / cash[currency],
        )
        remaining[currency] -= notional + costs
        counts[currency] += 1
        groups.add(row["group"])
        selected.append(row)
    return {
        "as_of": current.isoformat(),
        "status": "watchlist" if selected else "no_trade",
        "policy": dict(POLICY),
        "universe_size": len(universe),
        "cash_by_currency": cash,
        "selection_coverage": selection_coverage,
        "rows": rows,
        "selected": selected,
        "unallocated_cash": remaining,
        "limitations": list(LIMITATIONS),
    }


def build_scan(frame, universe, as_of, cash_by_currency=None):
    """Rank completed observations and size a hypothetical, separately funded watchlist."""
    data, current, cash, calendars, histories = _prepare(frame, universe, as_of, cash_by_currency)
    return _scan(histories, universe, current, cash, calendars)


def _cohort_return(prices, symbol, entry, exit_session, calendar):
    entry_date, exit_date = entry.date().isoformat(), exit_session.date().isoformat()
    entry_key, exit_key = (symbol, entry_date), (symbol, exit_date)
    if entry_key not in prices.index or exit_key not in prices.index:
        return {"symbol": symbol, "error": "Missing expected entry or exit session"}
    first, last = prices.loc[entry_key], prices.loc[exit_key]
    for bar, session in ((first, entry), (last, exit_session)):
        if bar.available_at > calendar.session_close(session) + pd.Timedelta(minutes=1):
            return {"symbol": symbol, "error": "Entry or exit observation was delayed"}
        if not math.isfinite(bar.adjusted_close) or bar.adjusted_close <= 0:
            return {"symbol": symbol, "error": "Invalid entry or exit adjusted close"}
    gross = float(last.adjusted_close / first.adjusted_close - 1)
    return {
        "symbol": symbol,
        "entry_session": entry_date,
        "exit_session": exit_date,
        "entry_adjusted_close": float(first.adjusted_close),
        "exit_adjusted_close": float(last.adjusted_close),
        "gross_return": gross,
        "net_return": gross - POLICY["diagnostic_round_trip_cost_bps"] / 10_000,
        "stressed_return": gross - POLICY["diagnostic_stressed_cost_bps"] / 10_000,
    }


def forward_diagnostics(frame, universe, as_of, cash_by_currency=None):
    """Nonoverlapping five-session close-to-close cohorts; not an execution backtest."""
    data, current, cash, calendars, histories = _prepare(frame, universe, as_of, cash_by_currency)
    cohorts = []
    prices = data.set_index(["symbol", "session"])
    for currency, benchmark, calendar_name in (("USD", "SPY", "XNYS"), ("CAD", "XIU.TO", "XTSE")):
        specs = [item for item in universe if item["currency"] == currency]
        if cash[currency] == 0 or not specs or data.empty:
            continue
        calendar = calendars[calendar_name]
        expected = _expected_session(calendar, current)
        sessions = calendar.sessions_in_range(data.session.min(), expected)
        # ponytail: fixed cohorts; use the qualified execution engine for portfolio P&L.
        for index in range(
            POLICY["minimum_sessions"] - 1, len(sessions) - 6, POLICY["diagnostic_holding_sessions"]
        ):
            selection, entry, exit_session = (
                sessions[index],
                sessions[index + 1],
                sessions[index + 6],
            )
            decision = calendar.session_close(selection) + pd.Timedelta(minutes=1)
            scan = _scan(histories, universe, decision, cash, calendars)
            selected = [row for row in scan["selected"] if row["currency"] == currency]
            coverage = scan["selection_coverage"][currency]
            selection_complete = (
                coverage["declared_stock_count"] > 0 and not coverage["unavailable_symbols"]
            )
            entry_date, exit_date = entry.date().isoformat(), exit_session.date().isoformat()
            cohort = {
                "currency": currency,
                "selection_session": selection.date().isoformat(),
                "as_of": decision.isoformat(),
                "entry_session": entry_date,
                "exit_session": exit_date,
                "status": "complete" if selection_complete else "incomplete",
                "selection_coverage": coverage,
                "candidates": [],
                "net_return": 0.0,
                "stressed_return": 0.0,
                "benchmark_symbol": benchmark,
                "benchmark_return": None,
                "excess_return": None,
                "cash_return": 0.0,
            }
            for candidate in selected:
                detail = _cohort_return(prices, candidate["symbol"], entry, exit_session, calendar)
                detail["score"] = candidate["score"]
                if "error" in detail:
                    cohort["status"] = "incomplete"
                cohort["candidates"].append(detail)
            if cohort["status"] == "incomplete":
                cohort["net_return"] = cohort["stressed_return"] = None
            elif selected:
                cohort["net_return"] = float(
                    np.mean([row["net_return"] for row in cohort["candidates"]])
                )
                cohort["stressed_return"] = float(
                    np.mean([row["stressed_return"] for row in cohort["candidates"]])
                )
            else:
                cohort["status"] = "cash"
            benchmark_detail = _cohort_return(prices, benchmark, entry, exit_session, calendar)
            if "error" in benchmark_detail:
                cohort["benchmark_error"] = benchmark_detail["error"]
            else:
                cohort["benchmark_return"] = benchmark_detail["net_return"]
                if cohort["net_return"] is not None:
                    cohort["excess_return"] = cohort["net_return"] - cohort["benchmark_return"]
            cohorts.append(cohort)
    summary = {}
    for currency in cash:
        attempted = [row for row in cohorts if row["currency"] == currency]
        complete = [row for row in attempted if row["status"] != "incomplete"]
        returns = [row["net_return"] for row in complete]
        paired = [row for row in complete if row["benchmark_return"] is not None]
        summary[currency] = {
            "status": "unfunded"
            if cash[currency] == 0
            else "studied"
            if complete
            else "insufficient_history",
            "reason": f"No {currency} cash allocated; currency not studied"
            if cash[currency] == 0
            else None,
            "total_cohort_count": len(attempted),
            "incomplete_cohort_count": len(attempted) - len(complete),
            "cohort_count": len(complete),
            "candidate_count": sum(len(row["candidates"]) for row in complete),
            "paired_cohort_count": len(paired),
            "mean_return": float(np.mean(returns)) if returns else None,
            "median_return": float(np.median(returns)) if returns else None,
            "win_rate": float(np.mean(np.array(returns) > 0)) if returns else None,
            "mean_benchmark_return": float(np.mean([row["benchmark_return"] for row in paired]))
            if paired
            else None,
            "mean_excess_return": float(np.mean([row["excess_return"] for row in paired]))
            if paired
            else None,
            "mean_stressed_return": float(np.mean([row["stressed_return"] for row in complete]))
            if complete
            else None,
            "mean_cash_return": 0.0 if complete else None,
        }
    return {
        "as_of": current.isoformat(),
        "kind": "forward_return_diagnostic",
        "policy": dict(POLICY),
        "cash_by_currency": cash,
        "cohorts": cohorts,
        "summary": summary,
        "limitations": list(LIMITATIONS)
        + [
            "Equal-weight candidate cohort returns; not a cash/holdings portfolio "
            "or Nautilus backtest.",
            "Cohorts missing any declared stock's required selection history or a selected "
            "entry/exit observation are incomplete and excluded from performance summaries.",
            "Entry uses the next exchange session CLOSE; exit is five sessions after entry. "
            "A fixed 20 basis-point round-trip cost, stressed at 40, is subtracted from returns.",
            "Cash cohorts earn zero in their own currency; "
            "no FX conversion or cash interest is modeled.",
            "No compounding, CAGR or Sharpe is inferred from cohort averages; "
            "this is exposed historical data.",
        ],
    }
