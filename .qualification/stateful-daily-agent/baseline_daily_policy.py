"""Shared next-close stock ranking and cash reservation rules.

This module plans whole-share candidates. It neither submits orders nor assumes
that reference-price quantities will fill at the following close.
"""

from __future__ import annotations

import math

import numpy as np

POLICY = {
    "version": "daily-model-decision-v1",
    "maximum_positions": 5,
    "position_budget_fraction": 0.2,
    "atr_risk_budget_fraction": 0.005,
    "atr_multiple": 2,
    "predicted_downside_penalty": 0.5,
    "execution": "next_session_close",
    "horizons": [1, 3, 5],
}


def forecast_score(predicted, head, cost_bps):
    """Expected return net of both proportional legs and predicted close downside."""
    half_cost = cost_bps / 20000
    return (
        predicted[:, head] * (1 - half_cost)
        - 2 * half_cost
        - POLICY["predicted_downside_penalty"] * np.maximum(0, predicted[:, head + 3])
    )


def plan_entries(
    *,
    symbols,
    ranking,
    prices,
    atrs,
    nav,
    available_cash,
    held_symbols=(),
    reserved_symbols=(),
    slots=None,
    cost_bps=40,
    correlation_allowed=None,
    audit=True,
):
    """Reserve settled-by-fill cash in rank order, with independent positions.

    ``available_cash`` excludes existing order reservations. If ``slots`` is
    omitted, holdings and reserved symbols consume the five slots. An explicit
    value is the caller's free capacity at the planned fill (allowing scheduled
    exits), already net of reserved orders. Held names still cannot be re-entered.
    The caller must derive these values from a reconciled account snapshot.
    """
    if not np.isfinite([nav, available_cash, cost_bps]).all():
        raise ValueError("NAV, available cash and costs must be finite")
    if nav < 0 or available_cash < 0 or not 0 <= cost_bps < 20000:
        raise ValueError("NAV/cash must be nonnegative and costs in [0, 20000)")
    if len(prices) != len(symbols) or len(atrs) != len(symbols):
        raise ValueError("Prices and ATRs must follow the symbol order")
    if len(set(symbols)) != len(symbols):
        raise ValueError("Symbol order must be unique")
    held, reserved = set(held_symbols), set(reserved_symbols)
    symbol_indices = {symbol: i for i, symbol in enumerate(symbols)}
    if (held | reserved) - symbol_indices.keys():
        raise ValueError("Every held/reserved symbol requires a market input")
    if slots is None:
        slots = max(0, POLICY["maximum_positions"] - len(held | reserved))
    if not isinstance(slots, (int, np.integer)) or not 0 <= slots <= 5:
        raise ValueError("Free slots must be an integer in [0, 5]")
    half_cost = cost_bps / 20000
    available = float(available_cash)
    orders, decisions, seen = [], [], set()
    peers = [symbol_indices[name] for name in symbols if name in held | reserved]
    for rank, raw_index in enumerate(ranking, 1):
        j = int(raw_index)
        if j != raw_index or not 0 <= j < len(symbols):
            raise ValueError("Ranking contains an invalid symbol index")
        symbol = symbols[j]
        row = {"rank": rank, "symbol": symbol, "symbol_index": j}
        reason = None
        if j in seen:
            reason = "duplicate"
        elif symbol in held:
            reason = "held"
        elif symbol in reserved:
            reason = "reserved"
        elif len(orders) >= slots:
            reason = "position_limit"
        seen.add(j)
        if reason is None:
            price, atr = float(prices[j]), float(atrs[j])
            if not np.isfinite([price, atr]).all() or min(price, atr) <= 0:
                reason = "invalid_quote"
            else:
                unit_cost = price * (1 + half_cost)
                planned = math.floor(
                    min(
                        POLICY["position_budget_fraction"] * nav / unit_cost,
                        POLICY["atr_risk_budget_fraction"] * nav / (POLICY["atr_multiple"] * atr),
                    )
                )
                if planned <= 0:
                    reason = "position_budget_or_atr"
                elif unit_cost > available:
                    reason = "insufficient_cash"
                elif correlation_allowed is not None and not correlation_allowed(j, peers):
                    reason = "correlation"
                else:
                    quantity = math.floor(min(planned, available / unit_cost))
                    reservation = quantity * price * (1 + half_cost)
                    orders.append(
                        {
                            "symbol_index": j,
                            "symbol": symbol,
                            "quantity": quantity,
                            "reference_price": price,
                            "reserved_cash": reservation,
                        }
                    )
                    available -= reservation
                    peers.append(j)
                    row.update(quantity=quantity, reserved_cash=reservation)
                    reason = "planned"
        row["reason"] = reason
        if audit or reason == "correlation":
            decisions.append(row)
        if not audit and len(orders) >= slots:
            break
    return {"orders": orders, "decisions": decisions, "remaining_cash": available}
