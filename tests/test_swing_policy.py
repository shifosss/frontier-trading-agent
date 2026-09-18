"""Counterexamples for the pure daily-exit / weekly-entry portfolio planner."""

from decimal import Decimal

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from frontier.swing_policy import SwingPolicy, plan_portfolio

AS_OF = "2025-04-17T20:01:00Z"  # Thursday before Good Friday.


def spec(symbol, **overrides):
    return {
        "symbol": symbol,
        "currency": "USD",
        "calendar": "XNYS",
        "asset_type": "etf" if symbol == "SPY" else "stock",
        "exposure_group": symbol,
        **overrides,
    }


@pytest.fixture
def market():
    calendar = xcals.get_calendar("XNYS", start="2024-01-01", end="2025-05-01")
    sessions = calendar.sessions_in_range("2024-01-02", "2025-04-22")
    index = np.arange(len(sessions))
    close = 40 * np.exp(0.0015 * index + 0.004 * np.sin(index))
    frames = []
    for symbol in ("SPY", "AAA", "BBB", "CCC", "DDD", "EEE"):
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "session": sessions.strftime("%Y-%m-%d"),
                    "available_at": [
                        calendar.session_close(day) + pd.Timedelta(minutes=1) for day in sessions
                    ],
                    "close": close,
                    "adjusted_close": close,
                    "high": close * 1.006,
                    "low": close * 0.994,
                    "volume": 1_000_000,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def plan(frame, symbols=("SPY", "AAA"), **kwargs):
    arguments = {
        "as_of": AS_OF,
        "positions": [],
        "position_state": {},
        "equity_usd": 10_000,
        "spendable_usd": 10_000,
        "policy": SwingPolicy(),
        "risk_halted": False,
    }
    arguments.update(kwargs)
    return plan_portfolio(frame, [spec(symbol) for symbol in symbols], **arguments)


def holding(symbol="AAA", **overrides):
    return {"symbol": symbol, "qty": 3, "avg_entry_price": 50, "market_value": 180, **overrides}


def test_friday_holiday_weekly_entry_uses_next_open_and_cannot_move_after_missed_open(market):
    result = plan(market)
    assert result["source_session"] == "2025-04-17"
    assert result["eligible_at"] == "2025-04-21T13:30:00+00:00"
    assert result["expires_at"] == "2025-04-21T20:00:00+00:00"
    assert result["regime"]["status"] == "risk_on"
    assert result["entry_data_complete"] is True
    assert result["intents"][0]["side"] == "buy"
    assert result["intents"][0]["type"] == "limit"
    assert result["intents"][0]["time_in_force"] == "day"
    assert result["next_position_state"] == {}  # An intent is not a filled position.
    missed = plan(market, as_of="2025-04-21T13:30:00Z")
    assert missed["eligible_at"] == "2025-04-22T13:30:00+00:00"
    assert not missed["intents"]
    assert "final session" in missed["decisions"][0]["reason"]


def test_future_values_and_unfinished_session_do_not_change_decisions(market):
    before = plan(market)
    future = market.available_at > pd.Timestamp(AS_OF)
    changed = market.copy()
    changed.loc[future, ["close", "adjusted_close", "high", "low", "volume"]] *= 100
    assert plan(changed) == before
    changed.loc[future, "available_at"] = pd.Timestamp(AS_OF)
    assert plan(changed) == before


@pytest.mark.parametrize("symbol", ["SPY", "AAA"])
def test_stale_and_missing_lookback_history_cannot_create_buy(market, symbol):
    stale = market.loc[~((market.symbol == symbol) & (market.session == "2025-04-17"))]
    assert not plan(stale)["intents"]
    missing = market.loc[~((market.symbol == symbol) & (market.session == "2025-03-05"))]
    assert not plan(missing)["intents"]


def test_missing_top_ranked_stock_blocks_runner_up_but_preserves_holding_exits(market):
    ranked = market.copy()
    leader = ranked.symbol == "AAA"
    prices = ["close", "adjusted_close", "high", "low"]
    ranked.loc[leader, prices] *= np.exp(0.001 * np.arange(leader.sum()))[:, None]
    symbols = ("SPY", "AAA", "BBB", "CCC")
    policy = SwingPolicy(max_positions=1)
    complete = plan(ranked, symbols=symbols, policy=policy)
    scores = {row["symbol"]: row["indicators"]["score"] for row in complete["decisions"]}
    assert scores["AAA"] > scores["BBB"]
    assert complete["entry_data_complete"] is True
    assert [intent["symbol"] for intent in complete["intents"]] == ["AAA"]

    missing = ranked.loc[~(leader & (ranked.session == "2025-04-17"))]
    incomplete = plan(missing, symbols=symbols, policy=policy)
    assert incomplete["entry_data_complete"] is False
    assert not incomplete["intents"]
    runner_up = next(row for row in incomplete["decisions"] if row["symbol"] == "BBB")
    assert runner_up["indicators"]["history_complete"] is True
    assert runner_up["action"] == "wait"
    assert "Incomplete declared USD stock universe" in runner_up["reason"]

    exits = plan(
        missing,
        symbols=symbols,
        positions=[holding("CCC")],
        position_state={"CCC": {"peak_close": 500}},
    )
    assert exits["entry_data_complete"] is False
    assert [(intent["symbol"], intent["side"]) for intent in exits["intents"]] == [("CCC", "sell")]


def test_buy_reserves_limit_price_fees_and_book_caps(market):
    policy = SwingPolicy(
        max_positions=4, max_gross_fraction=0.3, risk_fraction=0.1, commission_per_order=1.25
    )
    result = plan(
        market,
        symbols=("SPY", "AAA", "BBB", "CCC", "DDD", "EEE"),
        equity_usd=1000,
        spendable_usd=275,
        policy=policy,
    )
    buys = [intent for intent in result["intents"] if intent["side"] == "buy"]
    assert buys
    costs = []
    for intent in buys:
        assert type(intent["qty"]) is int and intent["qty"] > 0
        limit = Decimal(intent["limit_price"])
        assert limit.as_tuple().exponent == -2
        cost = intent["qty"] * limit + Decimal("1.25")
        costs.append(cost)
        assert cost <= Decimal("200")
    assert sum(costs) <= Decimal("275")
    assert sum(costs) <= Decimal("300")
    assert len(buys) <= 4


def test_default_risk_sizing_accounts_for_buffer_and_commission(market):
    policy = SwingPolicy(commission_per_order=1)
    result = plan(market, policy=policy)
    intent = result["intents"][0]
    indicators = result["decisions"][0]["indicators"]
    distance = 2.5 * indicators["atr_14"] + float(intent["limit_price"]) - indicators["close"]
    assert intent["qty"] * distance + 1 <= 50


def test_daily_trend_exit_works_without_entry_metadata_and_does_not_spend_sale_proceeds(market):
    changed = market.copy()
    today = (changed.symbol == "AAA") & (changed.session == "2025-04-16")
    changed.loc[today, ["close", "adjusted_close", "low"]] = 35
    result = plan(
        changed,
        symbols=("SPY", "BBB"),
        as_of="2025-04-16T20:01:00Z",
        positions=[holding(market_value=900)],
        equity_usd=1000,
        spendable_usd=0,
    )
    assert result["intents"] == [
        {
            "symbol": "AAA",
            "side": "sell",
            "qty": 3,
            "type": "market",
            "time_in_force": "day",
            "reason": "Adjusted close below 50-session mean",
        }
    ]
    decision = next(row for row in result["decisions"] if row["symbol"] == "AAA")
    assert "metadata unavailable" in decision["reason"]
    assert "Entry session unknown" in decision["reason"]
    assert decision["indicators"]["holding_sessions"] is None
    assert "entry_session" not in result["next_position_state"]["AAA"]
    assert result["eligible_at"] == "2025-04-17T13:30:00+00:00"


def test_close_confirmed_peak_exit_and_twenty_completed_session_exit(market):
    result = plan(
        market,
        positions=[holding()],
        position_state={"AAA": {"peak_close": 100}},
        as_of="2025-04-16T20:01:00Z",
    )
    assert result["intents"][0]["side"] == "sell"
    assert "Close-confirmed" in result["intents"][0]["reason"]
    assert "intraday" not in result["intents"][0]["reason"]
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-03-01", "2025-04-16")
    entry = sessions[-20].date().isoformat()
    result = plan(
        market,
        positions=[holding()],
        position_state={"AAA": {"entry_session": entry}},
        as_of="2025-04-16T20:01:00Z",
    )
    assert result["intents"][0]["side"] == "sell"
    assert "20 completed sessions" in result["intents"][0]["reason"]


def test_risk_halt_exits_all_positions_without_prices_and_never_buys(market):
    empty = pd.DataFrame()
    result = plan(
        empty,
        positions=[holding(), holding("UNKNOWN", qty=2, market_value=20)],
        risk_halted=True,
        position_state={"CLOSED": {"entry_session": "2020-01-01"}},
    )
    assert {(intent["symbol"], intent["qty"], intent["side"]) for intent in result["intents"]} == {
        ("AAA", 3, "sell"),
        ("UNKNOWN", 2, "sell"),
    }
    assert all(intent["type"] == "market" for intent in result["intents"])
    assert "CLOSED" not in result["next_position_state"]
    assert all("risk halt" in intent["reason"] for intent in result["intents"])


def test_pending_sales_do_not_release_position_slots_or_gross_room(market):
    result = plan(
        market,
        symbols=("SPY", "AAA", "BBB"),
        positions=[holding(market_value=900)],
        position_state={"AAA": {"peak_close": 100}},
        equity_usd=1000,
        spendable_usd=0,
        policy=SwingPolicy(max_positions=1),
    )
    assert result["intents"] and all(intent["side"] == "sell" for intent in result["intents"])


def test_policy_is_frozen_strict_and_group_entries_are_unique(market):
    with pytest.raises(ValidationError):
        SwingPolicy(extra_mode=True)
    policy = SwingPolicy()
    with pytest.raises(ValidationError):
        policy.max_drawdown = 0.5
    universe = [
        spec("SPY"),
        spec("AAA", exposure_group="shared"),
        spec("BBB", exposure_group="shared"),
        spec("CCC", currency="CAD"),
    ]
    result = plan_portfolio(
        market,
        universe,
        as_of=AS_OF,
        positions=[],
        position_state={},
        equity_usd=10_000,
        spendable_usd=10_000,
        policy=policy,
        risk_halted=False,
    )
    assert [intent["symbol"] for intent in result["intents"]] == ["AAA"]
