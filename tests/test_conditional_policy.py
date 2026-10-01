"""Economic behavior of conditional ranking inside the existing cash engine."""
import importlib
import json
import runpy

import numpy as np
import pytest

from frontier.execution_costs import ExecutionCosts
from frontier.short_horizon_study import _simulate_daily

helpers = runpy.run_path("tests/test_short_horizon_study.py")


def policy(predictions, mode="dollars", identity="fixture"):
    module = importlib.import_module("frontier.conditional_policy")
    return module.ConditionalPolicy(
        lambda signal, symbol: predictions[symbol],
        ranking_mode=mode,
        forecast_identity=identity,
    )


def plan(selector, *, prices=(10, 10), atrs=(0.05, 1.25), nav=1000,
         cash=1000, slots=1, costs=None):
    return selector.plan_entries(
        signal_index=0, symbols=[chr(65+i) for i in range(len(prices))],
        ranking=np.arange(len(prices)), prices=np.array(prices), atrs=np.array(atrs),
        nav=nav, available_cash=cash, slots=slots, cost_bps=0,
        cost_model=costs or ExecutionCosts("proportional", 0),
    )


def test_fraction_and_dollars_rank_the_same_forecasts_at_actual_allowed_sizes():
    forecasts = [(0.02, 0), (0.10, 0)]
    fractional = plan(policy(forecasts, "fraction"))
    dollars = plan(policy(forecasts, "dollars"))
    assert fractional["orders"][0]["symbol"] == "B"  # 10% of USD20 = USD2
    assert dollars["orders"][0]["symbol"] == "A"  # 2% of USD200 = USD4
    assert dollars["orders"][0]["projection"]["utility"] == pytest.approx(4)
    assert fractional["orders"][0]["projection"]["utility"] == pytest.approx(2)


def test_cash_reservation_changes_fixed_fee_ranking_and_whole_quantity():
    result = plan(
        policy([(0.50, 0), (0.03, 0), (0.10, 0)]),
        prices=(10, 100, 10), atrs=(0.01, 0.01, 1),
        nav=2000, cash=500, slots=3, costs=ExecutionCosts("moomoo_ca_us", 0),
    )
    assert [(o["symbol"], o["quantity"]) for o in result["orders"]] == [("A", 39), ("C", 5)]
    assert result["remaining_cash"] == pytest.approx(56.02)
    assert result["rejection_counts"]["nonpositive_utility"] >= 1
    # B initially earns USD9 less fees, but USD3 at its later affordable one share loses to fees.
    assert any(r["symbol"] == "B" and r.get("quantity") == 1
               and r["reason"] == "nonpositive_utility" for r in result["decisions"])


def test_cap_dominated_proposals_reuse_sizing_without_changing_reservations(monkeypatch):
    module = importlib.import_module("frontier.conditional_policy")
    original = module.plan_entries
    seen = []

    def observed(**kwargs):
        seen.append(len(kwargs["symbols"]))
        return original(**kwargs)

    monkeypatch.setattr(module, "plan_entries", observed)
    result = plan(policy([(0.20-i/100, 0) for i in range(6)]),
                  prices=(10,)*6, atrs=(0.01,)*6, nav=2000, cash=2000, slots=5)
    assert [o["symbol"] for o in result["orders"]] == ["A", "B", "C", "D", "E"]
    assert [o["quantity"] for o in result["orders"]] == [40]*5
    assert result["remaining_cash"] == 0
    assert seen == [1]*6


@pytest.mark.parametrize("forecast", [(float("nan"), 0), (0.1, float("inf")),
                                       (0.1, -0.1), (-1, 0), (-2, 0), (1e308, 0)])
def test_invalid_forecast_or_nonpositive_exit_value_abstains(forecast):
    result = plan(policy([forecast]), prices=(10,), atrs=(0.1,))
    assert result["orders"] == []
    assert result["rejection_counts"]["invalid_forecast"] == 1
    json.dumps(result, allow_nan=False)


def test_projected_exit_fee_uses_predicted_sale_notional_and_downside_penalty():
    result = plan(policy([(0.10, 0.04)]), prices=(10,), atrs=(0.1,),
                  costs=ExecutionCosts("proportional", 40))
    projection = result["orders"][0]["projection"]
    assert projection["quantity"] == 19
    assert projection["notional"] == 190
    assert projection["projected_exit_notional"] == pytest.approx(209)
    assert projection["entry_fee"] == pytest.approx(0.38)
    assert projection["exit_fee"] == pytest.approx(0.418)
    assert projection["utility"] == pytest.approx(14.402)


def test_alphabetical_ties_and_held_names_never_reenter():
    selector = policy([(0.1, 0)]*3)
    result = selector.plan_entries(
        signal_index=0, symbols=["Z", "A", "B"], ranking=[0, 2, 1],
        prices=[10]*3, atrs=[0.01]*3, nav=1000, available_cash=1000,
        held_symbols=["B"], slots=2, cost_bps=0,
    )
    assert [o["symbol"] for o in result["orders"]] == ["A", "Z"]
    assert result["rejection_counts"]["held"] == 1


def simulate(data, selector=None, costs=None, **kwargs):
    return _simulate_daily(
        data, "momentum", 1, 2000, 0, 0, data["n"]-1, audit=True,
        entry_policy=selector, cost_model=costs, **kwargs,
    )


def test_fill_gap_rechecks_reduced_quantity_without_replacing_rejected_order():
    data = helpers["market"](n=5, count=3)
    helpers["signal"](data, 0, [0, 1])
    data["atr"][:] = 0.01
    data["close"][1, 0] = 210  # one share at USD210 leaves negative utility after minimum fees
    data["adjusted"][1:, 0] = 210
    selector = policy([(0.015, 0), (-0.1, 0), (0, 0)])
    result = simulate(data, selector, ExecutionCosts("moomoo_ca_us", 0))
    assert result["trades"] == 0
    assert result["equity"][-1] == 2000
    rejected = [r for r in result["policy_audit"] if r["phase"] == "fill"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "nonpositive_utility"
    assert rejected[0]["quantity"] == 1
    assert rejected[0]["planned_quantity"] == 39


def test_fill_never_increases_quantity_and_trade_reports_realized_fee_error():
    data = helpers["market"](n=5, count=2)
    helpers["signal"](data, 0, [0])
    data["atr"][:] = 0.01
    data["close"][1:, 0] = 5
    data["adjusted"][1, 0] = 5
    data["adjusted"][2:, 0] = 6
    result = simulate(data, policy([(0.1, 0), (0, 0)]), ExecutionCosts("proportional", 40))
    trade = result["trade_records"][0]
    assert trade["quantity"] == 39  # lower price never doubles the original reservation's shares
    assert trade["entry_notional"] == 195
    assert trade["exit_notional"] == pytest.approx(234)
    fill_projection = trade["conditional"]["fill_projection"]
    assert fill_projection["projected_exit_notional"] == pytest.approx(214.5)
    assert trade["conditional"]["realized_minus_fill_projected_fees"] == pytest.approx(0.039)
    assert result["equity"][-1]-2000 == pytest.approx(trade["net_pnl"])


def test_default_engine_outputs_remain_exact_without_policy():
    data = helpers["market"](n=8)
    helpers["signal"](data, 0, [0, 1])
    helpers["signal"](data, 3, [2])
    before = helpers["simulate"](data, budget=2000, cost=0)
    after = simulate(data)
    for name in ("equity", "cash", "settled_cash", "unsettled_cash"):
        np.testing.assert_array_equal(before.pop(name), after.pop(name))
    assert before == after
    assert "policy_audit" not in after


def test_streaming_rejects_different_frozen_forecast_identity():
    data = helpers["market"](n=8, count=2)
    helpers["signal"](data, 0, [0])
    first = simulate(data, policy([(0.1, 0), (0, 0)], identity="frozen-A"), process_through=0)
    with pytest.raises(ValueError, match="differs"):
        _simulate_daily(data, "momentum", 1, 2000, 0, 1, 7, audit=True,
                        entry_policy=policy([(0.1, 0), (0, 0)], identity="frozen-B"),
                        state=first["state"], process_through=7)
