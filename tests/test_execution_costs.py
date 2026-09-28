import json
import math
from dataclasses import FrozenInstanceError

import pytest

from frontier.execution_costs import ExecutionCosts, get_cost_profile


@pytest.mark.parametrize("bps", [0, 20, 40, 100, 33.3])
def test_proportional_preserves_exact_float_arithmetic(bps):
    profile = get_cost_profile("proportional", bps)
    for value in [0.1, 19.99, 400, 1739.431513, 1e10]:
        for side in ["buy", "sell"]:
            assert profile.fee(1, value, side) == value * (bps / 20000)


@pytest.mark.parametrize(
    "quantity,notional,buy,sell",
    [
        (1, 10, 1.99, 2.00),
        (200, 2000, 1.99, 2.04),
        (201, 2010, 2.00, 2.05),  # platform 1.005 -> 1.01
        (400, 2000, 3.96, 4.01),
        (500, 100, 1.99, 2.00),
        (2000, 400, 2.00, 2.01),
        (2000, 2000, 19.80, 19.85),  # exactly USD1 uses ordinary rates
        (2000, 1999.99, 2.00, 2.05),
    ],
)
def test_moomoo_independent_tariff_cases(quantity, notional, buy, sell):
    profile = get_cost_profile("moomoo_ca_us", 0)
    assert profile.fee(quantity, notional, "buy") == pytest.approx(buy)
    assert profile.fee(quantity, notional, "sell") == pytest.approx(sell)


def test_declared_friction_added_without_rounding():
    assert get_cost_profile("moomoo_ca_us", 40).fee(39, 390, "buy") == 1.99 + 0.78
    assert get_cost_profile("wealthsimple_usd", 40).fee(39, 390, "buy") == 0.78
    assert get_cost_profile("wealthsimple_usd", 0).fee(39, 390, "sell") == 0


@pytest.mark.parametrize("name", ["proportional", "wealthsimple_usd", "moomoo_ca_us"])
def test_zero_orders_and_cash(name):
    profile = get_cost_profile(name)
    assert profile.fee(0, 0, "buy") == 0
    assert profile.fee(0, 0, "sell") == 0
    for cash in [0, -1, -1000]:
        assert profile.maximum_quantity(100, 10, cash) == 0
    assert profile.maximum_quantity(0, 10, 1000) == 0


@pytest.mark.parametrize(
    "price,quantity", [(1, 396), (5, 79), (10, 39), (50, 7), (100, 3), (400, 0)]
)
def test_independent_four_hundred_dollar_slot(price, quantity):
    assert get_cost_profile("moomoo_ca_us", 0).maximum_quantity(2000, price, 400) == quantity


def test_exact_boundary_and_partial_reservation():
    profile = get_cost_profile("moomoo_ca_us", 0)
    assert profile.maximum_quantity(100, 10, 11.99) == 1
    assert profile.maximum_quantity(100, 10, math.nextafter(11.99, 0)) == 0
    assert profile.maximum_quantity(100, 10, 400 - 391.99) == 0
    assert profile.maximum_quantity(100, 10, 401.99) == 40
    assert profile.maximum_quantity(3, 10, 401.99) == 3
    assert profile.maximum_quantity(100, 10, 402, "sell") == 40


@pytest.mark.parametrize("name", ["proportional", "wealthsimple_usd", "moomoo_ca_us"])
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_binary_search_matches_exhaustive_affordability_and_monotonicity(name, side):
    profile = get_cost_profile(name, 40)
    for price in [0.2, 0.999, 1, 5, 100, 400]:
        costs = [0.0] + [q * price + profile.fee(q, q * price, side) for q in range(1, 251)]
        assert costs == sorted(costs)
        previous = 0
        for budget in [0, 1, 2, 11.99, 100, 400, 2000, 100000]:
            actual = profile.maximum_quantity(250, price, budget, side)
            expected = max(q for q, cost in enumerate(costs) if cost <= budget)
            assert actual == expected
            assert actual >= previous
            previous = actual


def test_identity_is_frozen_serializable_and_returned_dict_is_detached():
    profile = get_cost_profile("moomoo_ca_us")
    with pytest.raises(FrozenInstanceError):
        profile.round_trip_bps = 0
    spec = profile.specification
    assert json.loads(json.dumps(spec)) == profile.to_dict()
    assert spec["historical_tariff"] is False
    assert spec["incomplete_cost_lower_bound"] is True
    assert "original entry whole shares" in spec["action_limitation"]
    spec["source_urls"].clear()
    assert profile.specification["source_urls"]


@pytest.mark.parametrize("bps", [-1, float("nan"), float("inf")])
def test_invalid_friction(bps):
    with pytest.raises(ValueError):
        ExecutionCosts(round_trip_bps=bps)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        get_cost_profile("unknown")
    profile = get_cost_profile("moomoo_ca_us")
    for quantity, notional, side in [
        (0, 1, "buy"),
        (1, 0, "buy"),
        (-1, 1, "buy"),
        (1.5, 2, "buy"),
        (True, 2, "buy"),
        (1, float("nan"), "buy"),
        (1, 1, "short"),
    ]:
        with pytest.raises(ValueError):
            profile.fee(quantity, notional, side)
    for maximum, price, budget, side in [
        (1, 0, 1, "buy"),
        (1, 1, float("inf"), "buy"),
        (-1, 1, 1, "buy"),
        (1, 1, 1, "invalid"),
    ]:
        with pytest.raises(ValueError):
            profile.maximum_quantity(maximum, price, budget, side)
