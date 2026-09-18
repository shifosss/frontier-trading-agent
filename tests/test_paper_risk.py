"""Cash-only paper accounting counterexamples, without broker requests."""

import pytest

from frontier.paper_risk import settlement_balance, update_risk


def test_deposits_and_withdrawals_preserve_drawdown_and_halt_is_latched():
    initial = update_risk(None, 1000)
    deposited = update_risk(initial, 1500, flow_cad=500)
    assert deposited["unit_nav"] == 1
    assert deposited["units"] == 1500
    assert deposited["drawdown"] == 0
    lost = update_risk(deposited, 1200)
    withdrawn = update_risk(lost, 1000, flow_cad=-200)
    assert withdrawn["unit_nav"] == pytest.approx(0.8)
    assert withdrawn["drawdown"] == pytest.approx(0.2)
    # Adding capital at the same observation cannot hide a 30% investment loss.
    breached = update_risk(withdrawn, 1875, flow_cad=1000)
    assert breached["unit_nav"] == pytest.approx(0.7)
    assert breached["drawdown"] == pytest.approx(0.3)
    assert breached["halted"]
    recovered = update_risk(breached, breached["units"] * 1.1)
    assert recovered["drawdown"] == 0
    assert recovered["halted"]


def test_full_withdrawal_and_recapitalizing_depleted_account_require_new_mandate():
    initial = update_risk(None, 100)
    with pytest.raises(ValueError, match="Full withdrawal"):
        update_risk(initial, 0, flow_cad=-100)
    depleted = update_risk(initial, 0)
    assert depleted["halted"] and depleted["drawdown"] == 1
    with pytest.raises(ValueError, match="recapitalize"):
        update_risk(depleted, 100, flow_cad=100)


def _order(side, qty, filled, price, stamp, *, status="filled", limit=100):
    return {
        "payload": {"symbol": "AAPL", "side": side, "qty": str(qty), "limit_price": str(limit)},
        "broker": {
            "filled_qty": str(filled),
            "filled_avg_price": str(price),
            "filled_at": stamp,
            "status": status,
        },
    }


@pytest.mark.parametrize(
    "sold_at, blocked_at, settled_at",
    [
        ("2026-10-09T18:00Z", "2026-10-12T14:00Z", "2026-10-13T13:30Z"),
        ("2026-11-10T18:00Z", "2026-11-11T15:00Z", "2026-11-12T14:30Z"),
        ("2026-06-18T18:00Z", "2026-06-19T14:00Z", "2026-06-22T13:30Z"),
        ("2026-09-18T18:00Z", "2026-09-21T13:29Z", "2026-09-21T13:30Z"),
        # Federal Juneteenth observance must not be applied retroactively.
        ("2020-06-18T18:00Z", "2020-06-19T13:29Z", "2020-06-19T13:30Z"),
        # Good Friday is not federal, but the exchange is closed.
        ("2026-04-02T18:00Z", "2026-04-03T14:00Z", "2026-04-06T13:30Z"),
    ],
)
def test_sale_waits_for_next_bank_and_exchange_business_day(sold_at, blocked_at, settled_at):
    orders = [
        _order("buy", 1, 1, 100, sold_at),
        _order("sell", 1, 1, 110, sold_at),
    ]
    pending = settlement_balance(100, [], orders, blocked_at)
    assert pending == {"expected_cash": 110, "spendable": 0, "positions": {}}
    settled = settlement_balance(100, [], orders, settled_at)
    assert settled == {"expected_cash": 110, "spendable": 110, "positions": {}}


def test_partly_filled_buy_reserves_remainder_until_canceled():
    order = _order("buy", 5, 2, 90, "2026-09-18T15:00Z", status="partially_filled")
    pending = settlement_balance(1000, [], [order], "2026-09-18T16:00Z")
    assert pending == {"expected_cash": 820, "spendable": 520, "positions": {"AAPL": 2}}
    order["broker"]["status"] = "canceled"
    canceled = settlement_balance(1000, [], [order], "2026-09-18T16:00Z")
    assert canceled == {"expected_cash": 820, "spendable": 820, "positions": {"AAPL": 2}}


def test_partial_sale_uses_latest_observed_update_for_all_proceeds():
    sale = _order("sell", 3, 2, 110, None, status="partially_filled")
    sale["broker"]["updated_at"] = "2026-09-18T15:00Z"
    orders = [_order("buy", 3, 3, 100, "2026-09-17T15:00Z"), sale]
    pending = settlement_balance(300, [], orders, "2026-09-18T16:00Z")
    assert pending == {"expected_cash": 220, "spendable": 0, "positions": {"AAPL": 1}}
    settled = settlement_balance(300, [], orders, "2026-09-21T14:00Z")
    assert settled["spendable"] == 220


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("stamp", ["2026-09-21T15:00Z", "2026-09-18T15:00", None])
def test_future_naive_or_missing_fill_timestamp_is_not_cash_or_position_evidence(side, stamp):
    with pytest.raises(ValueError, match="valid observed timestamp"):
        settlement_balance(100, [], [_order(side, 1, 1, 100, stamp)], "2026-09-18T16:00Z")


def test_weekend_status_update_does_not_invalidate_a_partial_fill():
    sale = _order("sell", 3, 2, 110, None, status="canceled")
    sale["broker"]["updated_at"] = "2026-09-20T15:00Z"
    orders = [_order("buy", 3, 3, 100, "2026-09-18T15:00Z"), sale]
    pending = settlement_balance(300, [], orders, "2026-09-20T16:00Z")
    assert pending == {"expected_cash": 220, "spendable": 0, "positions": {"AAPL": 1}}
    settled = settlement_balance(300, [], orders, "2026-09-21T13:30Z")
    assert settled["spendable"] == 220
