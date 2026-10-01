"""Synthetic chronology, delayed fills, settlement and minute-NAV checks."""
import copy
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import exchange_calendars as xcals
import pytest


SPEC = importlib.util.spec_from_file_location("opening_strategy", Path(__file__).with_name("strategy.py"))
strategy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(strategy)


def calendar(start="2024-05-01", count=24):
    cal = xcals.get_calendar("XNYS", start=start, end="2025-01-31")
    return [{"session": str(s.date()), "open": cal.session_open(s).isoformat(),
             "close": cal.session_close(s).isoformat(),
             "minutes": int((cal.session_close(s)-cal.session_open(s)).total_seconds()/60)}
            for s in cal.sessions[:count]]


def bars(*, direction=1, activity=100, entry=None, exit_=None, narrow=False):
    result = {}
    for symbol in (*strategy.STOCKS, "SPY"):
        sign = 0 if symbol == "SPY" else direction
        delta = 0.003 if narrow else 0.3
        close = 10 + sign * delta
        width = 0.004 if narrow else 0.4
        low, high = (10-width/2, 10+width) if sign >= 0 else (10-width, 10+width/2)
        result[symbol] = {i: {"o": 10, "h": high, "l": low, "c": close,
                              "v": activity, "n": 5} for i in range(60)}
        for i in range(76, 197):
            price = close if entry is None else entry
            result[symbol][i] = {"o": price, "h": price, "l": price, "c": price, "v": 100, "n": 5}
        if exit_ is not None:
            result[symbol][196] = {"o": exit_, "h": exit_, "l": exit_, "c": exit_, "v": 100, "n": 5}
    return result


def fixture(**kwargs):
    sessions = calendar()
    data = [bars(**kwargs) for _ in sessions]
    for day in data[20:]:
        for symbol in strategy.STOCKS:
            for i in range(60):
                day[symbol][i]["v"] *= 2
    return sessions, data


def run(sessions, data, **kwargs):
    return strategy.simulate(sessions, data, arm=kwargs.pop("arm", "continuation"),
                             cost_profile=kwargs.pop("cost_profile", "proportional"),
                             first_signal=sessions[20]["session"], last_session=sessions[-1]["session"], **kwargs)


def test_opening_dollar_activity_and_causal_20_consecutive_sessions():
    current = strategy.opening_features(bars(activity=200))
    previous = {s: [60 * 10.3 * 100] * 20 for s in strategy.STOCKS}
    assert len(strategy.select_signals(current, previous, "continuation")) == 6
    assert strategy.select_signals(current, previous, "reversal") == []
    previous["AAPL"][5] = None
    assert "AAPL" not in [x["symbol"] for x in strategy.select_signals(current, previous, "continuation")]
    split = bars(activity=200)
    for row in split["MSFT"].values():
        for key in ("o", "h", "l", "c"):
            row[key] /= 4
        row["v"] *= 4
    changed = strategy.opening_features(split)
    assert changed["MSFT"]["activity"] == pytest.approx(current["MSFT"]["activity"])
    assert changed["MSFT"]["relative_return"] == pytest.approx(current["MSFT"]["relative_return"])


def test_future_execution_and_outcome_cannot_change_signals_or_planned_orders():
    sessions, data = fixture()
    changed = copy.deepcopy(data)
    for day in changed[20:]:
        for symbol in strategy.STOCKS:
            day[symbol][76]["o"] *= 2
            day[symbol][196]["o"] *= 2
            day[symbol][150]["c"] *= 3
    first = run(sessions[:21], data[:21])
    later = run(sessions[:21], changed[:21])
    assert first["orders"] == later["orders"]
    assert first["trades"] != later["trades"]
    assert first["event_reference"][0]["eligible_symbols"] == later["event_reference"][0]["eligible_symbols"]


def test_current_missing_benchmark_blocks_both_arms_and_reversal_trades_when_available():
    sessions, data = fixture(direction=-1)
    result = run(sessions[:21], data[:21], arm="reversal")
    assert result["status"] == "complete" and len(result["trades"]) == 5
    del data[20]["SPY"][59]
    result = run(sessions[:21], data[:21], arm="reversal")
    assert result["status"] == "complete" and result["orders"] == []
    assert result["event_reference"][0]["eligible_symbols"] == []


def test_unaffordable_gap_cancels_only_planned_orders_without_new_candidates():
    sessions, data = fixture(entry=1000)
    result = run(sessions[:21], data[:21], cost_profile="moomoo_ca_us")
    assert result["status"] == "complete" and len(result["orders"]) == 5
    assert len(result["fills"]) == 5 and all(row["cancelled_for_affordability"] for row in result["fills"])
    assert result["trades"] == [] and result["ending_equity"] == 2000


def test_strict_opening_missingness_abstains_but_missing_exit_invalidates_after_entry():
    sessions, data = fixture()
    del data[20]["AAPL"][10]
    result = run(sessions[:21], data[:21])
    assert result["status"] == "complete"
    assert "AAPL" not in [x["symbol"] for x in result["orders"]]
    sessions, data = fixture()
    del data[20]["AAPL"][196]
    result = run(sessions[:21], data[:21])
    assert result["status"] == "invalid"
    assert result["failure"]["reason"] == "missing_required_exit"
    assert result["open_positions"] and any(x["symbol"] == "AAPL" for x in result["orders"])
    assert result["total_return"] is None


def test_missing_planned_entry_is_invalid_not_replaced_by_sixth_name():
    sessions, data = fixture()
    del data[20]["AAPL"][76]
    result = run(sessions[:21], data[:21])
    assert result["status"] == "invalid" and result["failure"]["reason"] == "missing_required_entry"
    assert len(result["orders"]) == 5
    assert result["orders"][0]["symbol"] == "AAPL"


def test_gap_reduces_quantity_and_fees_are_inside_reserved_budget():
    sessions, data = fixture(entry=20, exit_=20)
    result = run(sessions[:21], data[:21], cost_profile="moomoo_ca_us")
    assert result["status"] == "complete" and result["trades"]
    by_symbol = {row["symbol"]: row for row in result["orders"]}
    for trade in result["trades"]:
        plan = by_symbol[trade["symbol"]]
        assert 0 < trade["quantity"] < plan["planned_quantity"]
        assert trade["entry_notional"] + trade["entry_fee"] <= plan["reserved_cash"]
        assert plan["reserved_cash"] <= 400
        assert trade["entry_fee"] >= 1.99 and trade["exit_fee"] >= 2.00


def test_settled_cash_only_and_historical_t3_no_daily_cash_reset():
    sessions = calendar("2017-01-03", count=23)
    data = [bars(narrow=True) for _ in sessions]
    for day in data[20:]:
        for symbol in strategy.STOCKS:
            for i in range(60):
                day[symbol][i]["v"] *= 2
    result = run(sessions, data)
    assert result["status"] == "complete"
    first, second = result["daily_equity"][:2]
    assert first["unsettled_cash"] > 1500
    second_orders = [x for x in result["orders"] if x["session"] == second["session"]]
    assert sum(x["reserved_cash"] for x in second_orders) <= first["settled_cash"] + 1e-9
    assert all(x["settlement_index"] == 23 for x in result["trades"] if x["session"] == sessions[20]["session"])
    assert result["ending_equity"] == pytest.approx(2000 + sum(x["net_pnl"] for x in result["trades"]))


def test_minute_drawdown_and_stale_valuation_are_not_day_end_drawdown():
    sessions, data = fixture(exit_=10.3)
    for symbol in strategy.STOCKS:
        data[20][symbol][100]["c"] = 5
        data[20][symbol][100]["l"] = 5
    del data[20]["MSFT"][101]
    result = run(sessions[:21], data[:21])
    assert result["status"] == "complete"
    assert result["sampled_mark_max_drawdown"] > 0.1
    assert result["total_return"] > -0.01
    assert result["stale_mark_observations"] > 0
    assert result["max_mark_age_seconds"] >= 60
    assert any(row["phase"] == "minute_close" and row["stale_positions"] for row in result["intraday_equity"])


def test_exact_entry_delay_dst_and_early_close_offsets():
    cal = xcals.get_calendar("XNYS", start="2024-10-01", end="2024-11-29")
    sessions = [{"session": str(s.date()), "open": cal.session_open(s).isoformat(),
                 "close": cal.session_close(s).isoformat(),
                 "minutes": int((cal.session_close(s)-cal.session_open(s)).total_seconds()/60)} for s in cal.sessions]
    data = [bars() for _ in sessions]
    for symbol in strategy.STOCKS:
        for i in range(60):
            data[-1][symbol][i]["v"] *= 2
    result = strategy.simulate(sessions, data, arm="continuation", cost_profile="proportional",
                               first_signal="2024-11-29", last_session="2024-11-29")
    assert result["trades"]
    for trade in result["trades"]:
        assert trade["entry_time"] == "2024-11-29T15:46:00+00:00"
        assert trade["exit_time"] == "2024-11-29T17:46:00+00:00"
        assert datetime.fromisoformat(trade["exit_time"]) < datetime.fromisoformat(sessions[-1]["close"])


def test_reference_counts_missing_endpoints_without_changing_eligibility():
    sessions, data = fixture(direction=-1)
    del data[20]["T"][76]
    del data[20]["T"][196]
    result = run(sessions[:21], data[:21], arm="continuation")
    assert result["status"] == "complete" and result["trades"] == []
    reference = result["event_reference"][0]
    assert len(reference["eligible_symbols"]) == 6
    assert reference["missing_entry"] == ["T"] and reference["missing_exit"] == ["T"]
    assert reference["paired_events"] == 5


def test_monthly_returns_chain_from_prior_month_close_without_resetting_capital():
    curve = [{"session": "2024-01-31", "equity": 2100},
             {"session": "2024-02-01", "equity": 2050},
             {"session": "2024-02-29", "equity": 2200}]
    monthly = strategy._period_returns(curve, 2000, "monthly")
    assert [row["period"] for row in monthly] == ["2024-01", "2024-02"]
    assert monthly[0]["return_"] == pytest.approx(0.05)
    assert monthly[1]["starting_equity"] == 2100
    assert monthly[1]["return_"] == pytest.approx(2200/2100-1)
    assert (1+monthly[0]["return_"])*(1+monthly[1]["return_"]) == pytest.approx(2200/2000)
