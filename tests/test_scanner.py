"""Counterexamples for temporal ranking, constrained sizing and cohort semantics."""

import json

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from frontier.scanner import build_scan, forward_diagnostics


def _spec(symbol="AAA", currency="USD", group=None, asset_type="stock"):
    return {
        "symbol": symbol,
        "name": symbol,
        "currency": currency,
        "calendar": "XTSE" if currency == "CAD" else "XNYS",
        "group": group or symbol,
        "asset_type": asset_type,
    }


def _frame(spec, start="2025-01-02", end="2025-07-01", constant=False):
    calendar = xcals.get_calendar(
        spec["calendar"], start=start, end=str(pd.Timestamp(end).date() + pd.Timedelta(days=7))
    )
    sessions = calendar.sessions_in_range(start, end)
    changes = 0.002 + 0.002 * np.sin(np.arange(len(sessions)) * 1.7)
    prices = np.full(len(sessions), 100.0) if constant else 100 * np.cumprod(1 + changes)
    return pd.DataFrame(
        {
            "symbol": spec["symbol"],
            "session": sessions.strftime("%Y-%m-%d"),
            "available_at": [
                calendar.session_close(day) + pd.Timedelta(minutes=1) for day in sessions
            ],
            "close": prices,
            "adjusted_close": prices,
            "high": prices * 1.004,
            "low": prices * 0.996,
            "volume": 1_000_000,
        }
    )


def test_future_bars_and_unfinished_session_do_not_change_scan():
    spec = _spec()
    frame = _frame(spec)
    current = frame.available_at.iloc[80]
    original = build_scan(frame, [spec], current)
    mutated = frame.copy()
    future = mutated.available_at > current
    mutated.loc[future, ["close", "adjusted_close", "high", "low", "volume"]] *= 100
    assert build_scan(mutated, [spec], current) == original
    # A provider timestamp that arrives early does not make an unfinished session complete.
    unfinished = frame.iloc[[81]].copy()
    unfinished["available_at"] = current
    changed = pd.concat([frame.iloc[:81], unfinished], ignore_index=True)
    assert build_scan(changed, [spec], current) == original
    json.dumps(original, allow_nan=False)


def test_exchange_holiday_is_fresh_and_missing_expected_session_is_stale():
    us, ca = _spec(), _spec("CAN.TO", "CAD")
    frame = pd.concat([_frame(us), _frame(ca)], ignore_index=True)
    current = "2025-07-01T21:00:00Z"
    result = build_scan(frame, [us, ca], current, {"USD": 10_000, "CAD": 10_000})
    by_symbol = {row["symbol"]: row for row in result["rows"]}
    assert by_symbol[us["symbol"]]["last_session"] == "2025-07-01"
    assert by_symbol[ca["symbol"]]["last_session"] == "2025-06-30"
    assert len(result["selected"]) == 2
    stale = frame.loc[~((frame.symbol == us["symbol"]) & (frame.session == "2025-07-01"))]
    excluded = next(
        row for row in build_scan(stale, [us, ca], current)["rows"] if row["symbol"] == "AAA"
    )
    assert excluded["status"] == "excluded"
    assert any("Stale" in reason for reason in excluded["reasons"])


def test_zero_volatility_and_insufficient_history_produce_no_trade():
    constant, short = _spec("FLAT"), _spec("NEW")
    frame = pd.concat([_frame(constant, constant=True), _frame(short).tail(20)], ignore_index=True)
    result = build_scan(frame, [constant, short], "2025-07-01T21:00:00Z")
    assert result["status"] == "no_trade"
    assert result["unallocated_cash"] == {"USD": 0, "CAD": 700}
    assert any("Zero realized" in reason for row in result["rows"] for reason in row["reasons"])
    assert any(
        "Insufficient history" in reason for row in result["rows"] for reason in row["reasons"]
    )


def test_group_caps_native_cash_and_stock_only_selection():
    specs = [
        _spec("AAA", group="shared"),
        _spec("BBB", group="shared"),
        _spec("CAN.TO", "CAD"),
        _spec("SPY", asset_type="etf"),
    ]
    frame = pd.concat([_frame(spec) for spec in specs], ignore_index=True)
    budgets = {"USD": 10_000, "CAD": 1_000}
    result = build_scan(frame, specs, "2025-07-01T21:00:00Z", budgets)
    assert {row["symbol"] for row in result["selected"]} == {"AAA", "CAN.TO"}
    assert len({row["group"] for row in result["selected"]}) == len(result["selected"])
    for currency, budget in budgets.items():
        selected = [row for row in result["selected"] if row["currency"] == currency]
        spent = sum(row["estimated_notional"] + row["estimated_cost"] for row in selected)
        assert result["unallocated_cash"][currency] == pytest.approx(budget - spent)
        for row in selected:
            assert row["quantity"] == int(row["quantity"])
            assert row["estimated_notional"] <= budget * 0.2
            assert row["quantity"] * 2 * row["atr_14"] <= budget * 0.005
    no_us = build_scan(frame, specs, "2025-07-01T21:00:00Z", {"USD": 0, "CAD": 1_000})
    assert all(row["currency"] == "CAD" for row in no_us["selected"])
    us_row = next(row for row in no_us["rows"] if row["symbol"] == "AAA")
    assert us_row["status"] == "eligible" and us_row["quantity"] == 0
    assert any("cash and risk budgets" in reason for reason in us_row["reasons"])
    etf = next(row for row in result["rows"] if row["symbol"] == "SPY")
    assert any("ETF retained" in reason for reason in etf["reasons"])


def test_diagnostic_uses_next_close_five_session_horizon_and_separate_costs():
    stock, benchmark = _spec(), _spec("SPY", asset_type="etf")
    frame = pd.concat([_frame(stock), _frame(benchmark)], ignore_index=True)
    result = forward_diagnostics(frame, [stock, benchmark], "2025-07-01T21:00:00Z", {"USD": 10_000})
    first, second = result["cohorts"][:2]
    candidate = first["candidates"][0]
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(first["selection_session"], first["exit_session"])
    assert candidate["entry_session"] == sessions[1].date().isoformat()
    assert candidate["exit_session"] == sessions[6].date().isoformat()
    assert second["entry_session"] == first["exit_session"]
    indexed = frame.loc[frame.symbol == "AAA"].set_index("session")
    gross = (
        indexed.loc[candidate["exit_session"], "adjusted_close"]
        / indexed.loc[candidate["entry_session"], "adjusted_close"]
        - 1
    )
    assert candidate["gross_return"] == pytest.approx(gross)
    assert candidate["net_return"] == pytest.approx(gross - 0.002)
    assert candidate["stressed_return"] == pytest.approx(gross - 0.004)
    assert first["excess_return"] == pytest.approx(0)
    assert result["summary"]["CAD"]["cohort_count"] == 0
    json.dumps(result, allow_nan=False)


def test_missing_future_endpoint_cannot_be_replaced_with_later_close():
    stock, benchmark = _spec(), _spec("SPY", asset_type="etf")
    frame = pd.concat([_frame(stock), _frame(benchmark)], ignore_index=True)
    complete = forward_diagnostics(
        frame, [stock, benchmark], "2025-07-01T21:00:00Z", {"USD": 10_000}
    )
    missing = complete["cohorts"][0]["exit_session"]
    reduced = frame.loc[~((frame.symbol == "AAA") & (frame.session == missing))]
    result = forward_diagnostics(
        reduced, [stock, benchmark], "2025-07-01T21:00:00Z", {"USD": 10_000}
    )
    assert result["cohorts"][0]["status"] == "incomplete"
    assert result["cohorts"][0]["net_return"] is None
    assert "Missing expected" in result["cohorts"][0]["candidates"][0]["error"]


def test_delayed_benchmark_is_not_silently_used_for_excess_return():
    stock, benchmark = _spec(), _spec("SPY", asset_type="etf")
    frame = pd.concat([_frame(stock), _frame(benchmark)], ignore_index=True)
    original = forward_diagnostics(
        frame, [stock, benchmark], "2025-07-01T21:00:00Z", {"USD": 10_000}
    )
    first = original["cohorts"][0]
    delayed = (frame.symbol == "SPY") & (frame.session == first["entry_session"])
    frame.loc[delayed, "available_at"] += pd.Timedelta(days=1)
    result = forward_diagnostics(frame, [stock, benchmark], "2025-07-01T21:00:00Z", {"USD": 10_000})
    assert result["cohorts"][0]["status"] == "complete"
    assert result["cohorts"][0]["benchmark_return"] is None
    assert result["cohorts"][0]["excess_return"] is None
    assert "delayed" in result["cohorts"][0]["benchmark_error"]
    assert (
        result["summary"]["USD"]["paired_cohort_count"]
        == original["summary"]["USD"]["paired_cohort_count"] - 1
    )


def test_unfunded_currency_is_not_studied_but_funded_cash_cohorts_are_retained():
    us, ca = _spec(), _spec("CAN.TO", "CAD")
    frame = pd.concat([_frame(us), _frame(ca, constant=True)], ignore_index=True)
    result = forward_diagnostics(frame, [us, ca], "2025-07-01T21:00:00Z")
    assert result["summary"]["USD"]["status"] == "unfunded"
    assert result["summary"]["USD"]["cohort_count"] == 0
    assert result["summary"]["USD"]["mean_return"] is None
    assert result["summary"]["USD"]["mean_cash_return"] is None
    assert all(row["currency"] == "CAD" for row in result["cohorts"])
    assert all(row["status"] == "cash" for row in result["cohorts"])
    assert result["summary"]["CAD"]["status"] == "studied"
    assert result["summary"]["CAD"]["cohort_count"] > 0
    assert result["summary"]["CAD"]["mean_return"] == 0.0


@pytest.mark.parametrize("partial", [False, True])
def test_unavailable_stock_history_is_not_reported_as_studied_cash(partial):
    missing = _spec("MISSING.TO", "CAD")
    present = _spec("PRESENT.TO", "CAD")
    benchmark = _spec("XIU.TO", "CAD", asset_type="etf")
    universe = [missing, benchmark]
    frame = _frame(benchmark)
    if partial:
        universe.append(present)
        frame = pd.concat([frame, _frame(present)], ignore_index=True)
    cash = {"USD": 0, "CAD": 10_000}
    current = "2025-07-01T21:00:00Z"
    scan = build_scan(frame, universe, current, cash)
    assert scan["selection_coverage"]["CAD"] == {
        "declared_stock_count": 2 if partial else 1,
        "evaluable_stock_count": 1 if partial else 0,
        "unavailable_symbols": ["MISSING.TO"],
    }
    study = forward_diagnostics(frame, universe, current, cash)
    summary = study["summary"]["CAD"]
    assert summary["status"] == "insufficient_history"
    assert summary["cohort_count"] == 0
    assert summary["total_cohort_count"] > 0
    assert summary["incomplete_cohort_count"] == summary["total_cohort_count"]
    assert summary["mean_return"] is None
    assert summary["mean_excess_return"] is None
    assert all(cohort["status"] == "incomplete" for cohort in study["cohorts"])
    assert all(cohort["net_return"] is None for cohort in study["cohorts"])
    # Known benchmark observations cannot establish missing stock-selection outcomes.
    assert all(cohort["benchmark_return"] is not None for cohort in study["cohorts"])
