"""Resume continuity and cash costs tested with an independent saved-state boundary."""

import json
import runpy
from collections import Counter

import numpy as np
import pytest

from frontier.daily_policy import plan_entries
from frontier.execution_costs import get_cost_profile
from frontier.short_horizon_study import _simulate_daily


def sample(seed=12):
    data = runpy.run_path("tests/test_short_horizon_study.py")["market"](100, 16, lag=3)
    rng = np.random.default_rng(seed)
    data["close"] = 10 * np.cumprod(1 + rng.normal(0, 0.035, (100, 16)), axis=0)
    data["adjusted"] = data["close"].copy()
    data["atr"] = 0.012 * data["close"]
    ranking = np.stack([rng.permutation(15) for _ in range(100)])
    return data, ranking


@pytest.mark.parametrize("horizon", [1, 3, 5])
@pytest.mark.parametrize("chunk_size", [1, 7, 21])
@pytest.mark.parametrize("profile", [None, "proportional", "wealthsimple_usd", "moomoo_ca_us"])
def test_chunked_json_resumes_match_monolithic_cash_and_all_trades(horizon, chunk_size, profile):
    data, ranking = sample()
    cost = get_cost_profile(profile, 40) if profile else None
    kwargs = dict(
        audit=True, signal_ranking=ranking, signal_counts=np.full(100, 15), cost_model=cost
    )
    expected = _simulate_daily(
        data, "learned", horizon, 2000, 40, 0, 99, process_through=99, **kwargs
    )
    assert expected["status"] == "complete"
    parts, state = [], None
    for start in range(0, 100, chunk_size):
        result = _simulate_daily(
            data,
            "learned",
            horizon,
            2000,
            40,
            start,
            99,
            process_through=min(99, start + chunk_size - 1),
            state=state,
            **kwargs,
        )
        assert result["status"] == "complete"
        assert min(result["settled_cash"]) >= -1e-9
        state = json.loads(json.dumps(result["state"], sort_keys=True, allow_nan=False))
        parts.append(result)
    for key in ("equity", "cash", "settled_cash", "unsettled_cash"):
        np.testing.assert_array_equal(np.concatenate([p[key] for p in parts]), expected[key])
    assert [t for p in parts for t in p["trade_records"]] == expected["trade_records"]
    assert sum(p["trades"] for p in parts) == expected["trades"]
    assert sum(p["fees"] for p in parts) == pytest.approx(expected["fees"], abs=1e-9)
    assert sum((Counter(p["activity"]) for p in parts), Counter()) == expected["activity"]
    assert state == json.loads(json.dumps(expected["state"]))
    assert not state["held"] and not state["pending"]


def test_cursor_policy_and_market_changes_cannot_resume_saved_account():
    data, ranking = sample()
    kwargs = dict(signal_ranking=ranking, signal_counts=np.full(100, 15), process_through=0)
    first = _simulate_daily(data, "learned", 5, 2000, 40, 0, 99, **kwargs)
    assert first["state"]["pending"]
    for start, horizon, cost in [(0, 5, 40), (2, 5, 40), (1, 3, 40), (1, 5, 20)]:
        with pytest.raises(ValueError, match="Resume"):
            _simulate_daily(
                data,
                "learned",
                horizon,
                2000,
                cost,
                start,
                99,
                state=first["state"],
                **(kwargs | {"process_through": 2}),
            )
    data["symbols"] = list(reversed(data["symbols"]))
    with pytest.raises(ValueError, match="Resume"):
        _simulate_daily(
            data,
            "learned",
            5,
            2000,
            40,
            1,
            99,
            state=first["state"],
            **(kwargs | {"process_through": 2}),
        )


def test_missing_required_mark_stops_with_nonresumable_cursor():
    data, ranking = sample()
    data["adjusted"][2] = np.nan
    result = _simulate_daily(
        data,
        "learned",
        5,
        2000,
        40,
        0,
        99,
        signal_ranking=ranking,
        signal_counts=np.full(100, 15),
        process_through=7,
    )
    assert result["status"] == "incomplete"
    assert result["state"]["next_session_index"] is None
    assert result["missing"]


def test_fixed_commission_changes_affordability_and_ledger_cost_independently():
    fees = get_cost_profile("moomoo_ca_us", 0)
    plan = plan_entries(
        symbols=["A", "B"],
        ranking=[0, 1],
        prices=[10, 400],
        atrs=[0.1, 0.1],
        nav=2000,
        available_cash=2000,
        cost_model=fees,
    )
    assert plan["orders"][0]["quantity"] == 39
    assert plan["orders"][0]["reserved_cash"] == pytest.approx(391.99)
    assert plan["decisions"][1]["reason"] == "position_budget_or_atr"
    data = runpy.run_path("tests/test_short_horizon_study.py")["market"]()
    data["counts"]["momentum"][0] = 1
    result = _simulate_daily(
        data, "momentum", 1, 2000, 0, 0, 19, cost_model=fees, audit=True, process_through=19
    )
    trade = result["trade_records"][0]
    assert trade["quantity"] == 39
    assert trade["entry_fee"] == pytest.approx(1.99)
    assert trade["exit_fee"] == pytest.approx(2.0)
    assert result["equity"][-1] == pytest.approx(1996.01)


def test_fee_shortfall_uses_settled_cash_without_negative_receivable():
    fees = get_cost_profile("moomoo_ca_us", 0)
    data = runpy.run_path("tests/test_short_horizon_study.py")["market"]()
    data["counts"]["momentum"][0] = 1
    data["adjusted"][2, 0] = 0.001
    result = _simulate_daily(
        data, "momentum", 1, 2000, 0, 0, 19, cost_model=fees, audit=True, process_through=2
    )
    assert result["status"] == "complete"
    assert result["state"]["receivables"] == []
    assert result["cash"][-1] == result["settled_cash"][-1]
    assert result["cash"][-1] == pytest.approx(1608.01 + 0.039 - 2.0)


def test_unfunded_exit_fees_invalidate_account_instead_of_borrowing():
    fees = get_cost_profile("moomoo_ca_us", 0)
    data = runpy.run_path("tests/test_short_horizon_study.py")["market"]()
    data["close"][:] = 1.0
    data["adjusted"][:] = 1.0
    data["atr"][:] = 0.001
    data["counts"]["momentum"][0] = 5
    data["adjusted"][2] = 0.001
    first = _simulate_daily(
        data,
        "momentum",
        1,
        20,
        0,
        0,
        19,
        cost_model=fees,
        audit=True,
        process_through=1,
    )
    # A fully invested starting account cannot fund a fee above liquidation proceeds.
    state = first["state"] | {"cash": 0.0, "settled_cash": 0.0}
    result = _simulate_daily(
        data,
        "momentum",
        1,
        20,
        0,
        2,
        19,
        state=state,
        cost_model=fees,
        audit=True,
        process_through=3,
    )
    assert result["status"] == "incomplete"
    assert result["state"]["cash"] >= 0
    assert result["state"]["settled_cash"] >= 0
    assert result["state"]["next_session_index"] is None
    assert result["missing"][0].endswith(":unfunded_exit_cost")
    assert result["trades"] == 0
