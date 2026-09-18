"""CAD risk measurement and conservative US cash settlement for the paper operator."""

import math
from decimal import Decimal

import exchange_calendars as xcals
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

US_BANK_DAY = pd.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())


def update_risk(previous, equity_cad, *, flow_cad=0.0, maximum_drawdown=0.30):
    """Value a declared external flow at this observation, before issuing/redeeming units.

    Observations measure sampled drawdown, not an intraday loss guarantee. Flow timing
    is explicit: this valuation treats the recorded flow as occurring at observation.
    """
    if not all(math.isfinite(v) for v in (equity_cad, flow_cad, maximum_drawdown)):
        raise ValueError("Risk inputs must be finite")
    if equity_cad < 0 or not 0 < maximum_drawdown < 1:
        raise ValueError("Invalid equity or drawdown limit")
    if previous is None:
        if equity_cad <= 0 or flow_cad:
            raise ValueError("Initialize risk with positive reconciled capital, without a flow")
        units, unit_nav, high, halted = equity_cad, 1.0, 1.0, False
    else:
        before_flow = equity_cad - flow_cad
        if before_flow < 0 or previous["units"] <= 0:
            raise ValueError("Flow exceeds pre-flow equity or account has no units")
        unit_nav = before_flow / previous["units"]
        if unit_nav <= 0 and flow_cad:
            raise ValueError("Cannot recapitalize a depleted paper account without a new mandate")
        units = previous["units"] + (flow_cad / unit_nav if flow_cad else 0)
        if units <= 0:
            raise ValueError("Full withdrawal requires closing this paper mandate")
        high = max(previous["high_watermark"], unit_nav)
        halted = previous["halted"]
    drawdown = max(0.0, 1 - unit_nav / high)
    return {
        "equity_cad": equity_cad,
        "units": units,
        "unit_nav": unit_nav,
        "high_watermark": high,
        "drawdown": drawdown,
        "halted": halted or drawdown >= maximum_drawdown - 1e-12,
        "valuation": "broker USD equity times observed Bank of Canada reference",
        "flow_timing": "external flow at this observation; not a reconstructed intraday path",
    }


def settlement_balance(initial_cash, flows, orders, as_of):
    """Release sales at the next banking business day that is also an XNYS session.

    This conservative T+1 model waits until that session opens. A partly filled sale's
    entire proceeds wait until T+1 after its latest observed update. It can understate
    availability; it never treats margin buying power as settled cash.
    """
    available = Decimal(str(initial_cash)) + sum(
        (Decimal(str(flow["amount_usd"])) for flow in flows), Decimal(0)
    )
    expected_cash = available
    positions = {}
    reserved = Decimal(0)
    cal = xcals.get_calendar("XNYS")
    timestamp = pd.Timestamp(as_of)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("Settlement as_of must include an explicit timezone")
    for record in orders:
        payload, broker = record["payload"], record.get("broker")
        if broker is None:
            continue
        quantity = Decimal(str(broker.get("filled_qty", "0")))
        if quantity < 0 or quantity > Decimal(str(payload["qty"])):
            raise ValueError("Broker fill quantity is outside the submitted order")
        value = quantity * Decimal(str(broker.get("filled_avg_price") or "0"))
        if quantity and value <= 0:
            raise ValueError("Filled order has no positive broker fill price")
        if quantity:
            stamp = pd.Timestamp(broker.get("filled_at") or broker.get("updated_at"))
            if pd.isna(stamp) or stamp.tzinfo is None or stamp > timestamp:
                raise ValueError("Fill lacks a valid observed timestamp")
            day = stamp.tz_convert("America/New_York").date().isoformat()
            # A partial fill may only have updated_at, including a later weekend
            # cancellation. Its proceeds still wait until the next business day.
            if broker.get("filled_at") and not cal.is_session(day):
                raise ValueError("Fill is outside a regular trading session")
        sign = 1 if payload["side"] == "buy" else -1
        symbol = payload["symbol"]
        positions[symbol] = positions.get(symbol, Decimal(0)) + sign * quantity
        expected_cash -= sign * value
        if sign == 1:
            available -= value
        elif quantity:
            # DTC has no settlement on Columbus/Veterans Day despite open exchanges:
            # https://www.dtcc.com/-/media/Files/pdf/2025/10/15/23036-25.pdf
            settlement_day = pd.Timestamp(day) + US_BANK_DAY
            while not cal.is_session(settlement_day):
                settlement_day += US_BANK_DAY
            settles = cal.session_open(settlement_day)
            if timestamp >= settles:
                available += value
        if payload["side"] == "buy" and broker.get("status") not in {
            "filled",
            "canceled",
            "expired",
            "rejected",
            "replaced",
        }:
            reserved += (Decimal(str(payload["qty"])) - quantity) * Decimal(
                str(payload["limit_price"])
            )
    return {
        "expected_cash": float(expected_cash),
        "spendable": float(max(Decimal(0), available - reserved)),
        "positions": {key: float(value) for key, value in positions.items() if value},
    }
