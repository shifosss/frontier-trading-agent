"""Frozen daily-exit/weekly-entry paper policy; an engineering baseline, not proven alpha."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class SwingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    name: str = Field(default="weekly-momentum-daily-exits", min_length=1)
    version: str = Field(default="1", min_length=1)
    max_positions: int = Field(default=4, ge=1, strict=True)
    max_position_fraction: float = Field(default=0.2, gt=0, le=1)
    max_gross_fraction: float = Field(default=0.8, gt=0, le=1)
    risk_fraction: float = Field(default=0.005, gt=0, le=1)
    max_drawdown: float = Field(default=0.30, gt=0, le=1)
    maximum_holding_sessions: int = Field(default=20, ge=1, strict=True)
    min_dollar_volume: float = Field(default=5_000_000, ge=0)
    entry_limit_buffer: float = Field(default=0.01, ge=0, le=1)
    commission_per_order: float = Field(default=0, ge=0)


def _time(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("as_of and available_at must include an explicit timezone")
    return timestamp.tz_convert("UTC")


def _amount(value, name):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return amount


def _features(history, expected):
    result = {
        "close": None,
        "mean_50": None,
        "mean_200": None,
        "momentum_20": None,
        "momentum_60": None,
        "annualized_volatility": None,
        "atr_14": None,
        "average_dollar_volume_20": None,
        "score": None,
        "history_complete": False,
    }
    if history.empty or history.session.iloc[-1] != expected[-1]:
        return result, ["Current completed-session history is missing or stale"]
    numeric = history[["close", "adjusted_close", "high", "low", "volume"]].apply(
        pd.to_numeric, errors="coerce"
    )

    def complete(length, columns):
        window = numeric[columns].tail(length).to_numpy(dtype=float)
        return (
            list(history.session.tail(length)) == expected[-length:]
            and len(window) == length
            and np.isfinite(window).all()
            and (window > 0).all()
        )

    if complete(1, ["close", "adjusted_close"]):
        result["close"] = float(numeric.close.iloc[-1])
    if complete(50, ["adjusted_close"]):
        result["mean_50"] = float(numeric.adjusted_close.tail(50).mean())
    if complete(200, ["adjusted_close"]):
        result["mean_200"] = float(numeric.adjusted_close.tail(200).mean())
    if complete(15, ["close", "adjusted_close", "high", "low"]):
        window = numeric.tail(15)
        if ((window.low <= window.close) & (window.close <= window.high)).all():
            factors = window.adjusted_close / window.close
            high, low = window.high * factors, window.low * factors
            previous = window.adjusted_close.shift()
            ranges = pd.concat(
                [high - low, (high - previous).abs(), (low - previous).abs()], axis=1
            )
            result["atr_14"] = float(ranges.max(axis=1).tail(14).mean() / factors.iloc[-1])
    if not complete(201, ["close", "adjusted_close", "high", "low"]):
        return result, ["Entries require 201 consecutive completed sessions with valid prices"]
    window = numeric.tail(201)
    if not ((window.low <= window.close) & (window.close <= window.high)).all():
        return result, ["Invalid high/low bounds in entry history"]
    if not np.isfinite(window.volume).all() or (window.volume < 0).any():
        return result, ["Invalid volume in entry history"]
    result["history_complete"] = True
    prices = window.adjusted_close
    result["momentum_20"] = float(prices.iloc[-1] / prices.iloc[-21] - 1)
    result["momentum_60"] = float(prices.iloc[-1] / prices.iloc[-61] - 1)
    volatility = float(prices.pct_change().tail(20).std(ddof=1) * np.sqrt(252))
    result["annualized_volatility"] = volatility
    result["average_dollar_volume_20"] = float((window.close * window.volume).tail(20).mean())
    if volatility > 1e-12:
        result["score"] = (result["momentum_20"] + result["momentum_60"]) / (2 * volatility)
    return result, []


def plan_portfolio(
    frame,
    universe,
    *,
    as_of,
    positions,
    position_state,
    equity_usd,
    spendable_usd,
    policy: SwingPolicy,
    risk_halted: bool,
):
    """Plan whole-share intents; the caller persists state and supplies actual paper fills.

    Holding age counts completed exchange sessions including the entry session. Price
    exits are close-confirmed and scheduled for a later opening, never intraday stops.
    The caller owns cash-flow-adjusted drawdown and supplies its durable risk halt.
    """
    current = _time(as_of)
    equity = _amount(equity_usd, "equity_usd")
    cash = _amount(spendable_usd, "spendable_usd")
    required = {
        "symbol",
        "session",
        "available_at",
        "close",
        "adjusted_close",
        "high",
        "low",
        "volume",
    }
    if not risk_halted and not required <= set(frame):
        raise ValueError(f"Missing policy columns: {sorted(required - set(frame))}")
    if len({item["symbol"] for item in universe}) != len(universe):
        raise ValueError("Universe symbols must be unique")
    specs = {item["symbol"]: item for item in universe}
    calendar = xcals.get_calendar(
        "XNYS",
        start=str(current.date() - pd.Timedelta(days=730)),
        end=str(current.date() + pd.Timedelta(days=30)),
    )
    closed = calendar.schedule.loc[calendar.schedule["close"] + pd.Timedelta(minutes=1) <= current]
    source = closed.index[-1]
    source_session = source.date().isoformat()
    expected = closed.index[-201:].strftime("%Y-%m-%d").tolist()
    future = calendar.schedule.loc[calendar.schedule["open"] > current]
    eligible_at, expires_at = future.iloc[0]["open"], future.iloc[0]["close"]
    next_session = calendar.next_session(source)
    next_open = calendar.session_open(next_session)
    week_end = source.isocalendar()[:2] != next_session.isocalendar()[:2]
    weekly_window = week_end and current < next_open

    # The durable risk halt exits known holdings even when source capture is unavailable.
    data = pd.DataFrame(columns=sorted(required)) if risk_halted else frame.copy()
    data["available_at"] = pd.to_datetime([_time(value) for value in data.available_at], utc=True)
    data["session"] = pd.to_datetime(data.session, errors="raise").dt.strftime("%Y-%m-%d")
    data = data.loc[(data.available_at <= current) & (data.session <= source_session)]
    if data.duplicated(["symbol", "session"]).any():
        raise ValueError("Policy input must have one row per symbol/session")
    histories = {symbol: rows.sort_values("session") for symbol, rows in data.groupby("symbol")}
    empty = data.iloc[:0]
    features = {
        symbol: _features(histories.get(symbol, empty), expected)
        for symbol in set(specs) | {p["symbol"] for p in positions} | {"SPY"}
    }
    spy, spy_errors = features["SPY"]
    entry_data_complete = spy["history_complete"] and all(
        features[item["symbol"]][0]["history_complete"]
        for item in universe
        if item.get("currency") == "USD" and item.get("asset_type") == "stock"
    )
    spy_history = histories.get("SPY", empty)
    risk_on = (
        spy["history_complete"]
        and spy["mean_200"] is not None
        and float(spy_history.adjusted_close.iloc[-1]) > spy["mean_200"]
    )
    regime = {
        "symbol": "SPY",
        "status": "risk_on" if risk_on else "unavailable" if spy_errors else "risk_off",
        "mean_200": spy["mean_200"],
        "reason": "; ".join(spy_errors)
        if spy_errors
        else "SPY adjusted close above 200-session mean"
        if risk_on
        else "SPY adjusted close at or below 200-session mean",
    }
    decisions, intents, held, groups = [], [], {}, set()
    next_state = {}
    gross = Decimal(0)
    for position in positions:
        symbol = position["symbol"]
        quantity = _amount(position["qty"], "position qty")
        if quantity != quantity.to_integral_value():
            raise ValueError("Policy positions must use whole shares")
        if symbol in held:
            raise ValueError("Positions must be unique by symbol")
        if not quantity:
            continue
        held[symbol] = position
        gross += _amount(position["market_value"], "position market_value")
        spec = specs.get(symbol, {})
        groups.add(spec.get("exposure_group", spec.get("group", symbol)))
        indicators, errors = features[symbol]
        state = dict(position_state.get(symbol, {}))
        reasons, exits = [], []
        history = histories.get(symbol, empty)
        if not spec:
            reasons.append("Holding metadata unavailable; no assumed instrument or entry history")
        entry = state.get("entry_session")
        age = None
        if entry is not None:
            try:
                entry_day = pd.Timestamp(entry)
                if calendar.is_session(entry_day) and entry_day <= source:
                    age = len(calendar.sessions_in_range(entry_day, source))
            except (ValueError, TypeError):
                pass
        if age is None:
            reasons.append("Entry session unknown; time exit cannot be evaluated")
        elif age >= policy.maximum_holding_sessions:
            exits.append(f"Maximum holding period reached: {age} completed sessions")
        close, atr = indicators["close"], indicators["atr_14"]
        peak = state.get("peak_close")
        if peak is not None and (not np.isfinite(peak) or peak <= 0):
            peak = None
            reasons.append("Prior peak invalid; using only observed closes from this cycle")
        if close is not None:
            peak = max(close, peak) if peak is not None else close
            state["peak_close"] = peak
            mean = indicators["mean_50"]
            if mean is not None and float(history.adjusted_close.iloc[-1]) < mean:
                exits.append("Adjusted close below 50-session mean")
            if atr is not None and atr > 0 and close <= peak - 2.5 * atr:
                exits.append("Close-confirmed drawdown from peak exceeds 2.5 ATR")
        elif not risk_halted:
            reasons.append("Fresh close unavailable; price exits cannot be evaluated")
        if risk_halted:
            exits.insert(0, "Portfolio risk halt: exit existing exposure")
        next_state[symbol] = state
        reason = "; ".join(exits + reasons) or "Daily exit conditions not met"
        decisions.append(
            {
                "symbol": symbol,
                "action": "sell" if exits else "hold",
                "reason": reason,
                "indicators": {**indicators, "holding_sessions": age, "peak_close": peak},
            }
        )
        if exits:
            intents.append(
                {
                    "symbol": symbol,
                    "side": "sell",
                    "qty": int(quantity),
                    "type": "market",
                    "time_in_force": "day",
                    "reason": "; ".join(exits),
                }
            )

    candidates = []
    for spec in universe:
        symbol = spec["symbol"]
        if symbol in held or spec.get("currency") != "USD" or spec.get("asset_type") != "stock":
            continue
        indicators, errors = features[symbol]
        reasons = list(errors)
        if spec.get("calendar") != "XNYS":
            reasons.append("USD entries require the XNYS session calendar")
        if risk_halted:
            reasons.append("Portfolio risk halt blocks entries")
        if not risk_on:
            reasons.append("SPY regime does not permit new entries")
        if not entry_data_complete:
            reasons.append(
                "Incomplete declared USD stock universe or SPY history blocks entry ranking"
            )
        if not weekly_window:
            reasons.append("Entries require the final session of the week before the next opening")
        if indicators["history_complete"]:
            if indicators["momentum_20"] <= 0 or indicators["momentum_60"] <= 0:
                reasons.append("Both 20-session and 60-session adjusted momentum must be positive")
            if indicators["score"] is None:
                reasons.append("Realized volatility is zero; score unavailable")
            if indicators["average_dollar_volume_20"] < policy.min_dollar_volume:
                reasons.append("Insufficient average USD dollar volume")
            if indicators["atr_14"] is None or indicators["atr_14"] <= 0:
                reasons.append("Positive ATR required for risk sizing")
        decision = {
            "symbol": symbol,
            "action": "wait",
            "reason": "; ".join(reasons),
            "indicators": indicators,
        }
        decisions.append(decision)
        if not reasons:
            candidates.append((spec, decision))
    candidates.sort(key=lambda item: (-item[1]["indicators"]["score"], item[0]["symbol"]))
    room = max(Decimal(0), equity * Decimal(str(policy.max_gross_fraction)) - gross)
    slots = max(0, policy.max_positions - len(held))
    fee = Decimal(str(policy.commission_per_order))
    for spec, decision in candidates:
        group = spec.get("exposure_group", spec.get("group", spec["symbol"]))
        if not slots or group in groups:
            decision["reason"] = "Position count or existing exposure-group limit reached"
            continue
        indicators = decision["indicators"]
        close = Decimal(str(indicators["close"]))
        limit = (close * (1 + Decimal(str(policy.entry_limit_buffer)))).quantize(
            Decimal("0.01"), rounding=ROUND_CEILING
        )
        budget = min(cash, room, equity * Decimal(str(policy.max_position_fraction)))
        quantity = max(0, int(((budget - fee) / limit).to_integral_value(rounding=ROUND_FLOOR)))
        distance = Decimal("2.5") * Decimal(str(indicators["atr_14"])) + limit - close
        risk_budget = equity * Decimal(str(policy.risk_fraction))
        risk_quantity = max(
            0, int(((risk_budget - fee) / distance).to_integral_value(rounding=ROUND_FLOOR))
        )
        quantity = min(quantity, risk_quantity)
        if not quantity:
            decision["reason"] = (
                "No whole share fits cash, gross, position and buffered ATR risk budgets"
            )
            continue
        reserved = quantity * limit + fee
        cash -= reserved
        room -= reserved
        slots -= 1
        groups.add(group)
        decision.update(
            action="buy",
            reason="Weekly positive 20/60 momentum / volatility rank; capped limit entry",
        )
        intents.append(
            {
                "symbol": spec["symbol"],
                "side": "buy",
                "qty": quantity,
                "type": "limit",
                "limit_price": str(limit),
                "time_in_force": "day",
                "reason": decision["reason"],
            }
        )
    return {
        "source_session": source_session,
        "decision_at": current.isoformat(),
        "eligible_at": eligible_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "policy": policy.model_dump(mode="json"),
        "policy_version": policy.version,
        "regime": regime,
        "entry_data_complete": entry_data_complete,
        "risk_halted": risk_halted,
        "decisions": decisions,
        "intents": intents,
        "next_position_state": next_state,
    }
