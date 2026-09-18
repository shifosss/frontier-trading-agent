import json

import numpy as np
import pandas as pd
import pytest

from frontier.short_horizon_study import (
    FAMILIES,
    _choose_daily,
    _simulate_daily,
    _summarize,
    evaluate_short_horizon,
    evaluate_short_horizon_view,
)


def market(n=20, count=6, lag=1):
    dates = pd.bdate_range("2024-06-03", periods=n)
    close = np.full((n, count), 10.0)
    bases = [name for name in FAMILIES if not name.endswith("_market_trend")]
    return {
        "n": n,
        "symbols": [f"S{i}" for i in range(count - 1)] + ["SPY"],
        "sessions": dates.strftime("%Y-%m-%d").tolist(),
        "dates": dates.to_numpy(dtype="datetime64[D]"),
        "close": close,
        "adjusted": close.copy(),
        "atr": np.full(close.shape, 0.125),
        "ranking": {name: np.tile(np.arange(count - 1), (n, 1)) for name in bases},
        "counts": {name: np.zeros(n, dtype=int) for name in bases},
        "benchmark": count - 1,
        "benchmark_symbol": "SPY",
        "market_trend": np.ones(n, dtype=bool),
        "market_trend_known": np.ones(n, dtype=bool),
        "settlement_index": np.arange(n) + lag,
    }


def signal(data, day, symbols, family="momentum"):
    data["counts"][family][day] = len(symbols)
    data["ranking"][family][day, : len(symbols)] = symbols


def simulate(data, *, horizon=1, cost=20, budget=1000, start=0, end=None, **kwargs):
    return _simulate_daily(
        data,
        "momentum",
        horizon,
        budget,
        cost,
        start,
        data["n"] - 1 if end is None else end,
        audit=True,
        **kwargs,
    )


def test_daily_idle_screen_and_no_same_close_entry():
    data = market()
    signal(data, 1, [0])
    result = simulate(data)
    trade = result["trade_records"][0]
    assert trade["signal_session"] == data["sessions"][1]
    assert trade["entry_session"] == data["sessions"][2]
    assert trade["exit_session"] == data["sessions"][3]
    assert trade["holding_sessions"] == 1
    assert result["activity"]["screened_sessions"] == 18


def test_positions_have_independent_entry_and_exit_ages():
    data = market()
    signal(data, 0, [0])
    signal(data, 1, [1])
    result = simulate(data, horizon=3)
    first, second = result["trade_records"]
    assert first["entry_session"] == data["sessions"][1]
    assert second["entry_session"] == data["sessions"][2]
    assert first["exit_session"] == data["sessions"][4]
    assert second["exit_session"] == data["sessions"][5]
    assert first["holding_sessions"] == second["holding_sessions"] == 3


def test_unsettled_sales_cannot_fund_entries_but_next_open_release_can():
    data = market(lag=3)
    data["counts"]["momentum"][:] = 5
    result = simulate(data, cost=0)
    dates = {value: i for i, value in enumerate(data["sessions"])}
    assert [dates[row["entry_session"]] for row in result["trade_records"][:10]] == [1] * 5 + [
        5
    ] * 5
    assert result["cash"][3] == 1000
    assert result["settled_cash"][3] == 0
    assert result["unsettled_cash"][3] == 1000
    np.testing.assert_allclose(result["cash"], result["settled_cash"] + result["unsettled_cash"])


def test_unused_settled_cash_can_trade_while_other_proceeds_are_unsettled():
    data = market(lag=3)
    signal(data, 0, [0])
    signal(data, 2, [1])
    result = simulate(data)
    assert result["trade_records"][1]["entry_session"] == data["sessions"][3]
    assert result["unsettled_cash"][3] > 0
    assert result["settled_cash"][3] > 0


def test_settlement_state_survives_walk_forward_boundary():
    data = market(lag=3)
    data["counts"]["momentum"][:] = 5
    first = simulate(data, cost=0, end=2)
    assert first["state"]["settled_cash"] == 0
    second = simulate(data, cost=0, start=3, state=first["state"])
    assert second["trade_records"][0]["entry_session"] == data["sessions"][5]
    assert second["settled_cash"][0] == 0


def test_gap_reductions_zero_fills_and_missing_future_marks():
    data = market()
    signal(data, 0, [0])
    data["close"][1, 0] = 1000
    data["adjusted"][1:, 0] = np.nan
    result = simulate(data)
    assert result["status"] == "complete"
    assert result["trades"] == 0
    assert result["activity"]["zero_fill_orders"] == 1
    assert result["equity"][-1] == 1000


def test_missing_held_marks_invalidate_all_profitability_aggregates():
    data = market()
    signal(data, 0, [0])
    signal(data, 4, [1])
    data["adjusted"][6, 1] = np.nan
    result = simulate(data)
    summary = _summarize(result, data["sessions"], 1000)
    assert summary["status"] == "incomplete"
    assert summary["trade_metrics"]["completed_trades"] == 1
    assert summary["trade_metrics"]["net_expectancy_native"] is None
    assert summary["trade_metrics"]["net_pnl_total"] is None
    assert summary["period_metrics"] == {}
    assert summary["total_return"] is None
    assert summary["missing"] == [f"S1:{data['sessions'][6]}:mark"]
    json.dumps(summary, allow_nan=False)


def test_net_trade_pnl_fees_equity_and_turnover_reconcile():
    data = market()
    signal(data, 0, [0, 1])
    signal(data, 4, [0])
    data["adjusted"][2:, 0] = 12
    data["adjusted"][2:, 1] = 9
    result = simulate(data, cost=100)
    summary = _summarize(result, data["sessions"], 1000)
    trades = result["trade_records"]
    assert result["equity"][-1] - 1000 == pytest.approx(sum(row["net_pnl"] for row in trades))
    assert result["fees"] == pytest.approx(
        sum(row["entry_fee"] + row["exit_fee"] for row in trades)
    )
    stats = summary["trade_metrics"]
    assert stats["net_expectancy_native"] == pytest.approx(
        np.mean([row["net_pnl"] for row in trades])
    )
    assert stats["turnover"] == pytest.approx(
        sum(row["entry_notional"] + row["exit_notional"] for row in trades)
        / result["equity"].mean()
    )
    assert stats["max_holding_sessions"] == 1
    assert min(result["settled_cash"]) >= 0
    assert min(result["cash"]) >= 0
    weekly = summary["period_returns"]["weekly"]
    assert np.prod([1 + row["return"] for row in weekly]) == pytest.approx(
        result["equity"][-1] / 1000
    )


def test_signal_orders_are_unchanged_by_future_price_changes():
    data = market()
    signal(data, 0, [0])
    first = simulate(data, horizon=3)["trade_records"][0]
    data["adjusted"][3:, 0] *= 0.1
    second = simulate(data, horizon=3)["trade_records"][0]
    for key in ("symbol", "signal_session", "entry_session", "quantity", "entry_notional"):
        assert first[key] == second[key]
    assert first["net_pnl"] != second["net_pnl"]


def test_training_selection_does_not_see_test_outcomes():
    data = market(n=1000)
    for family in data["counts"]:
        data["counts"][family][:] = 3
    first, candidates = _choose_daily(data, 1000, 200, 955)
    data["adjusted"][956:] *= 100
    second, changed = _choose_daily(data, 1000, 200, 955)
    assert first == second
    assert candidates == changed
    assert len(candidates) == 30


def test_fixed_grid_audit_is_bounded_and_one_view_replay_agrees():
    import runpy

    helper = runpy.run_path("tests/test_historical_study.py")
    frame, universe, as_of = helper["_history"](350)
    report = evaluate_short_horizon(frame, universe, as_of=as_of, budgets=(500,))
    assert len(report["portfolios"]) == 90
    assert len(report["methodology"]["attempts"]) == 30
    assert report["methodology"]["horizons"] == [1, 3, 5]
    assert all(
        not row["audit_retained"] and "trade_records" not in row for row in report["portfolios"]
    )
    row = next(
        row
        for row in report["portfolios"]
        if row["strategy"] == "momentum" and row["horizon"] == 1 and row["cost_bps"] == 20
    )
    detail = evaluate_short_horizon_view(
        frame,
        universe,
        as_of=as_of,
        currency="USD",
        budget=500,
        cost_bps=20,
        strategy="momentum",
        horizon=1,
    )
    assert detail["audit_retained"]
    assert detail["trade_records"]
    assert detail["trade_metrics"] == row["trade_metrics"]
    assert detail["total_return"] == row["total_return"]
    json.dumps(report, allow_nan=False)


def test_rolling_accounts_keep_all_trades_and_cash_across_two_folds(monkeypatch):
    from frontier.short_horizon_study import _walk_daily

    data = market(n=1300, lag=3)
    data["counts"]["momentum"][:] = 5
    monkeypatch.setattr(
        "frontier.short_horizon_study._choose_daily",
        lambda *args: ({"strategy": "momentum", "horizon": 1, "score": 0.1}, []),
    )
    rows = _walk_daily(data, 1000, "USD", None)
    for row in rows:
        assert row["status"] == "complete"
        assert len(row["folds"]) == 2
        assert row["trade_records"]
        assert row["audit_retained"]
        assert row["ending_equity"] - 1000 == pytest.approx(
            sum(record["net_pnl"] for record in row["trade_records"])
        )
        assert row["folds"][1]["starting_equity"] == row["folds"][0]["ending_equity"]
        assert all(point["settled_cash"] >= 0 for point in row["equity_curve"])
        assert row["trade_metrics"]["max_holding_sessions"] == 1
        assert row["period_metrics"]["weekly"]["count"] > 50
        json.dumps(row, allow_nan=False)
