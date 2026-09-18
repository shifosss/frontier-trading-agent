import json

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from frontier.strategy_study import evaluate_strategies


@pytest.fixture
def history():
    calendar = xcals.get_calendar("XNYS", start="2023-01-01", end="2025-12-31")
    sessions = calendar.sessions[:450]
    t = np.arange(len(sessions))
    records = []
    universe = []
    for symbol, base, kind in (("BBB", 10, "stock"), ("AAA", 10, "stock"), ("SPY", 300, "etf")):
        close = base + 0.04 * t + 0.2 * np.sin(0.45 * t)
        universe.append(
            {"symbol": symbol, "currency": "USD", "calendar": "XNYS", "asset_type": kind}
        )
        records.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "session": sessions.strftime("%Y-%m-%d"),
                    "available_at": [
                        calendar.session_close(day) + pd.Timedelta(minutes=1) for day in sessions
                    ],
                    "close": close,
                    "adjusted_close": close,
                    "high": close * 1.002,
                    "low": close * 0.998,
                    "volume": 1_000_000,
                }
            )
        )
    return (
        pd.concat(records, ignore_index=True),
        universe,
        calendar.session_close(sessions[-1]) + pd.Timedelta(minutes=2),
    )


def _study(history, budgets=(500,)):
    frame, universe, as_of = history
    return evaluate_strategies(frame, universe, as_of=as_of, budgets=budgets)


def _first_selected(study, horizon=5):
    return next(
        row
        for row in study["cohorts"]
        if row["strategy"] == "momentum"
        and row["horizon"] == horizon
        and row["status"] == "complete"
        and row["selected"]
    )


def test_fixed_attempts_ties_costs_and_whole_share_cash_weights(history):
    result = _study(history)
    assert len(result["attempts"]) == 12
    assert len(result["summaries"]) == 12 * 3 * 3
    json.dumps(result, allow_nan=False)
    row = _first_selected(result)
    assert row["selected"] == ["AAA", "BBB"]
    frame = history[0].set_index(["symbol", "session"])
    entry = frame.loc[("AAA", row["entry_session"]), "close"]
    exit_ = frame.loc[("AAA", row["exit_session"]), "adjusted_close"]
    base = row["returns_by_cost"]["20"]
    quantity = base["filled_quantities"][0]
    assert isinstance(quantity, int)
    assert base["invested_fraction"] == pytest.approx(2 * quantity * entry / 500)
    assert base["invested_fraction"] < 0.4
    assert base["return"] == pytest.approx(2 * quantity * entry / 500 * (exit_ / entry - 1 - 0.002))
    assert base["estimated_round_trip_cost"] == pytest.approx(2 * quantity * entry * 0.002)
    assert base["benchmark_quantity"] == 1
    assert row["returns_by_cost"]["100"]["return"] < base["return"]
    assert result == _study(
        (history[0].sample(frac=1, random_state=8), history[1][::-1], history[2])
    )


def test_earlier_decisions_do_not_depend_on_future_prices_or_future_liquidity(history):
    baseline = _study(history)
    earlier = _first_selected(baseline)
    frame, universe, as_of = history
    changed = frame.copy()
    future = (changed.session > earlier["signal_session"]) & (changed.symbol == "AAA")
    changed.loc[future, ["close", "adjusted_close", "high", "low"]] *= 3
    changed.loc[future, "volume"] = 0
    altered = _study((changed, universe, as_of))
    after = next(
        row
        for row in altered["cohorts"]
        if all(
            row[key] == earlier[key] for key in ("strategy", "horizon", "budget", "signal_session")
        )
    )
    assert after["selected"] == earlier["selected"]
    assert after["planned_quantities"] == earlier["planned_quantities"]


def test_selected_missing_exit_invalidates_entire_cohort_instead_of_dropping_name(history):
    initial = _study(history)
    selected = _first_selected(initial)
    frame, universe, as_of = history
    missing = frame.loc[~((frame.symbol == "AAA") & (frame.session == selected["exit_session"]))]
    result = _study((missing, universe, as_of))
    row = next(
        row
        for row in result["cohorts"]
        if all(
            row[key] == selected[key] for key in ("strategy", "horizon", "budget", "signal_session")
        )
    )
    assert row["status"] == "incomplete"
    assert row["selected"] == ["AAA", "BBB"]
    assert row["missing"] == ["AAA:exit"]
    assert row["returns_by_cost"] == {}
    summary = next(
        row
        for row in result["summaries"]
        if row["strategy"] == "momentum"
        and row["horizon"] == 5
        and row["period"] == selected["period"]
        and row["cost_bps"] == 20
    )
    # The next cohort enters at this same close, so it too is incomplete.
    assert summary["incomplete_cohorts"] == 2
    assert (
        summary["complete_cohorts"] + summary["incomplete_cohorts"] + summary["purged_cohorts"]
        == summary["scheduled_cohorts"]
    )
    bbb = next(row for row in result["coverage"]["instruments"] if row["symbol"] == "BBB")
    assert bbb["latest_201_complete"]


def test_partitions_purge_crossing_cohorts_and_no_compounded_metrics(history):
    result = _study(history)
    periods = result["methodology"]["periods"]["USD"]
    assert [period["sessions"] for period in periods.values()] == [270, 90, 90]
    assert any(row["status"] == "purged_boundary" for row in result["cohorts"])
    assert any(row["status"] == "pending" for row in result["cohorts"])
    for row in result["cohorts"]:
        period = periods[row["period"]]
        if row["status"] == "complete":
            assert period["first_session"] <= row["signal_session"] < row["entry_session"]
            assert row["entry_session"] < row["exit_session"] <= period["last_session"]
        elif row["status"] == "purged_boundary":
            assert row["exit_session"] > period["last_session"]
            assert not row["returns_by_cost"]
    assert not any("cagr" in key or "drawdown" in key for row in result["summaries"] for key in row)


def test_small_cash_can_have_zero_positions_and_different_results(history):
    result = _study(history, budgets=(1, 500, 100000))
    tiny = [row for row in result["cohorts"] if row["budget"] == 1 and row["status"] == "complete"]
    assert tiny
    assert all(not row["selected"] for row in tiny)
    assert all(
        value["return"] == value["benchmark_return"] == value["estimated_round_trip_cost"] == 0
        for row in tiny
        for value in row["returns_by_cost"].values()
    )
    small = _first_selected(result)
    big = next(
        row
        for row in result["cohorts"]
        if row["budget"] == 100000
        and all(row[key] == small[key] for key in ("strategy", "horizon", "signal_session"))
    )
    assert small["returns_by_cost"]["20"]["return"] != big["returns_by_cost"]["20"]["return"]


def test_recent_ipo_and_late_or_invalid_rows_do_not_block_other_symbols(history):
    frame, universe, as_of = history
    altered = frame.copy()
    aaa = altered.symbol == "AAA"
    last_aaa = altered.loc[aaa].index[-1]
    altered.loc[last_aaa, "available_at"] = as_of + pd.Timedelta(days=1)
    altered.loc[altered.loc[aaa].index[-2], "close"] = np.nan
    ipo = frame.loc[frame.symbol == "BBB"].tail(20).copy()
    ipo["symbol"] = "IPO"
    specs = [
        *universe,
        {"symbol": "IPO", "currency": "USD", "calendar": "XNYS", "asset_type": "stock"},
    ]
    result = _study((pd.concat([altered, ipo]), specs, as_of))
    coverage = {row["symbol"]: row for row in result["coverage"]["instruments"]}
    assert not coverage["AAA"]["latest_201_complete"]
    assert coverage["BBB"]["latest_201_complete"]
    assert not coverage["IPO"]["latest_201_complete"]
    assert coverage["IPO"]["missing_sessions_between_first_and_last"] == 0
    assert any(row["symbol"] == "BBB" for row in result["latest_candidates"])
    assert all(row["symbol"] != "AAA" for row in result["latest_candidates"])


def test_missing_benchmark_is_counted_even_for_cash_only_cohort(history):
    frame, universe, as_of = history
    result = _study((frame.loc[frame.symbol != "SPY"], universe, as_of), budgets=(1,))
    incomplete = [row for row in result["cohorts"] if row["status"] == "incomplete"]
    assert incomplete and all(not row["selected"] for row in incomplete)
    assert all("SPY:entry" in row["missing"] for row in incomplete)
    assert all(row["complete_cohorts"] == 0 for row in result["summaries"])


def test_separate_native_currency_books(history):
    frame, universe, as_of = history
    calendar = xcals.get_calendar("XTSE", start="2023-01-01", end="2025-12-31")
    sessions = calendar.sessions[calendar.sessions <= pd.Timestamp(as_of.date())]
    t = np.arange(len(sessions))
    added = []
    specs = list(universe)
    for symbol, kind in (("CCC.TO", "stock"), ("XIU.TO", "etf")):
        price = 10 + t * 0.04 + 0.2 * np.sin(t * 0.45)
        added.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "session": sessions.strftime("%Y-%m-%d"),
                    "available_at": [
                        calendar.session_close(s) + pd.Timedelta(minutes=1) for s in sessions
                    ],
                    "close": price,
                    "adjusted_close": price,
                    "high": price * 1.002,
                    "low": price * 0.998,
                    "volume": 1_000_000,
                }
            )
        )
        specs.append({"symbol": symbol, "currency": "CAD", "calendar": "XTSE", "asset_type": kind})
    result = _study((pd.concat([frame, *added]), specs, as_of))
    assert {row["currency"] for row in result["summaries"]} == {"USD", "CAD"}
    assert all(
        all(symbol.endswith(".TO") for symbol in row["selected"])
        for row in result["cohorts"]
        if row["currency"] == "CAD"
    )
    assert any(row["status"] == "complete" for row in result["cohorts"] if row["currency"] == "CAD")


def test_input_contract_rejects_duplicates_and_invalid_budget(history):
    frame, universe, as_of = history
    with pytest.raises(ValueError, match="one observation"):
        _study((pd.concat([frame, frame.head(1)]), universe, as_of))
    with pytest.raises(ValueError, match="positive"):
        _study(history, budgets=(0,))
    with pytest.raises(ValueError, match="timezone"):
        _study((frame, universe, pd.Timestamp(as_of).tz_localize(None)))
