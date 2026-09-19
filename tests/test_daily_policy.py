import runpy

import numpy as np
import pytest

from frontier.daily_policy import forecast_score, plan_entries
from frontier.short_horizon_study import _simulate_daily


def plan(**kwargs):
    args = dict(
        symbols=["A", "B", "C", "D", "E", "F"],
        ranking=list(range(6)),
        prices=np.full(6, 10.0),
        atrs=np.full(6, 0.125),
        nav=2000,
        available_cash=2000,
        cost_bps=40,
    )
    return plan_entries(**(args | kwargs))


def test_whole_shares_entry_cost_and_slots_are_reserved_once():
    result = plan(ranking=[0, 0, 1, 2, 3, 4, 5])
    assert [row["quantity"] for row in result["orders"]] == [39] * 5
    assert len({row["symbol"] for row in result["orders"]}) == 5
    assert result["remaining_cash"] == pytest.approx(46.1)
    assert result["decisions"][1]["reason"] == "duplicate"
    assert result["decisions"][-1]["reason"] == "position_limit"
    assert all(row["reserved_cash"] <= 400 for row in result["orders"])


def test_atr_and_settled_available_cash_limit_order_independently():
    result = plan(atrs=np.ones(6), available_cash=75)
    assert [(r["symbol"], r["quantity"]) for r in result["orders"]] == [("A", 5), ("B", 2)]
    assert result["remaining_cash"] == pytest.approx(4.86)
    assert all(r["reason"] == "insufficient_cash" for r in result["decisions"][2:])
    assert plan(available_cash=0)["orders"] == []


def test_holdings_and_existing_order_reservations_consume_capacity():
    result = plan(held_symbols=["A", "B"], reserved_symbols=["C"])
    assert [row["symbol"] for row in result["orders"]] == ["D", "E"]
    assert [r["reason"] for r in result["decisions"]] == [
        "held",
        "held",
        "reserved",
        "planned",
        "planned",
        "position_limit",
    ]
    # The caller has reconciled tomorrow's exits; held names remain excluded.
    result = plan(held_symbols=["A", "B"], reserved_symbols=["C"], slots=3)
    assert [row["symbol"] for row in result["orders"]] == ["D", "E", "F"]


def test_correlation_receives_existing_and_newly_reserved_peers():
    calls = []

    def allowed(candidate, peers):
        calls.append((candidate, list(peers)))
        return candidate != 2

    result = plan(held_symbols=["A"], correlation_allowed=allowed)
    assert calls[:3] == [(1, [0]), (2, [0, 1]), (3, [0, 1])]
    assert result["decisions"][2]["reason"] == "correlation"
    assert len(result["orders"]) == 4


def test_invalid_quote_is_explained_without_spending_cash():
    result = plan(prices=[np.nan, 0, 1000, 10, 10, 10], atrs=[1, 1, 1, 100, 1, 1])
    assert [r["reason"] for r in result["decisions"]][:4] == [
        "invalid_quote",
        "invalid_quote",
        "position_budget_or_atr",
        "position_budget_or_atr",
    ]
    assert [(r["symbol"], r["quantity"]) for r in result["orders"]] == [("E", 5), ("F", 5)]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"nav": float("nan")},
        {"available_cash": -1},
        {"cost_bps": -1},
        {"symbols": ["A"] * 6},
        {"ranking": [-1]},
        {"ranking": [1.5]},
        {"held_symbols": ["UNKNOWN"]},
        {"slots": 6},
        {"prices": [1]},
    ],
)
def test_inconsistent_account_and_market_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        plan(**kwargs)


def test_shared_forecast_score_prices_both_legs_and_downside():
    forecast = np.array([[0.1, 0.2, 0.3, 0.04, 0.02, -0.01]])
    np.testing.assert_allclose(forecast_score(forecast, 0, 40), [0.0758])
    np.testing.assert_allclose(forecast_score(forecast, 2, 40), [0.2954])


def test_daily_preview_quantity_matches_next_close_engine_without_price_gap():
    helper = runpy.run_path("tests/test_short_horizon_study.py")
    data = helper["market"]()
    helper["signal"](data, 0, [0, 1, 2, 3, 4])
    preview = plan_entries(
        symbols=data["symbols"],
        ranking=np.arange(5),
        prices=data["close"][0],
        atrs=data["atr"][0],
        nav=2000,
        available_cash=2000,
        cost_bps=40,
    )
    result = _simulate_daily(data, "momentum", 3, 2000, 40, 0, 19, audit=True)
    assert [(r["symbol"], r["quantity"]) for r in preview["orders"]] == [
        (r["symbol"], r["quantity"]) for r in result["trade_records"]
    ]
    assert result["settled_cash"][1] == pytest.approx(preview["remaining_cash"])
