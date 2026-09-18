"""One-time CAD-to-USD funding previews; never a broker conversion or order."""

import hashlib
import math
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from frontier.sources import boc_rows, fetch_boc_fx


def plan_usd_funding(workspace, cash, convert_cad, as_of):
    if set(cash) != {"USD", "CAD"}:
        raise ValueError("Cash must contain exactly USD and CAD balances")
    try:
        amounts = {key: Decimal(str(value)) for key, value in cash.items()}
        amount = Decimal(str(convert_cad))
    except InvalidOperation as exc:
        raise ValueError("Cash and conversion amounts must be finite nonnegative numbers") from exc
    if any(
        not value.is_finite() or not math.isfinite(float(value)) or value < 0
        for value in [*amounts.values(), amount]
    ):
        raise ValueError("Cash and conversion amounts must be finite nonnegative numbers")
    if amount > amounts["CAD"]:
        raise ValueError("Planned conversion cannot exceed the CAD cash balance")
    before = {currency: float(value) for currency, value in amounts.items()}
    plan = {
        "mode": "existing_cash",
        "cash_before": before,
        "cash_after": dict(before),
        "convert_cad": float(amount),
        "estimated_fee_cad": 0.0,
        "estimated_usd_credit": 0.0,
        "fee_profile": "Wealthsimple existing USD account; tiered one-time cash conversion fee",
        "fee_rate": 0.0,
        "reference": None,
        "limitations": ["Cash inputs are planning assumptions, not reconciled broker balances."],
    }
    if not amount:
        return plan
    timestamp = pd.Timestamp(as_of)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("Funding as_of must include an explicit timezone")
    timestamp = timestamp.tz_convert("UTC")
    capture = fetch_boc_fx(
        str((timestamp - pd.Timedelta(days=14)).date()),
        str(timestamp.date()),
        Path(workspace) / "artifacts/sources/cache",
        # A pre-publication cached response could omit today's newly published fixing.
        refresh=True,
    )
    rows = boc_rows(capture["payload"], capture["retrieved_at"])
    available = rows.loc[pd.to_datetime(rows.available_at, utc=True) <= timestamp]
    if available.empty:
        raise ValueError("No published USD/CAD reference rate is available before funding as_of")
    row = available.sort_values(["available_at", "event_time"]).iloc[-1]
    rate = Decimal(str(row.usd_cad))
    if not rate.is_finite() or rate <= 0:
        raise ValueError("USD/CAD reference rate must be finite and positive")
    # Per-transaction CAD tiers: https://www.wealthsimple.com/en-ca/legal/fees/trade
    if amount >= 100_000:
        fee_rate = Decimal("0")
    elif amount >= 25_000:
        fee_rate = Decimal("0.005")
    elif amount >= 10_000:
        fee_rate = Decimal("0.01")
    else:
        fee_rate = Decimal("0.015")
    fee = amount * fee_rate
    credit = ((amount - fee) / rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    plan.update(
        mode="planned_cad_to_usd",
        cash_after={"CAD": float(amounts["CAD"] - amount), "USD": float(amounts["USD"] + credit)},
        estimated_fee_cad=float(fee),
        fee_rate=float(fee_rate),
        estimated_usd_credit=float(credit),
        reference={
            "usd_cad": float(rate),
            "event_time": row.event_time,
            "available_at": row.available_at,
            "source_url": capture["request"]["url"],
            "request": capture["request"],
            "captured_at": capture["retrieved_at"],
            "raw_path": capture["raw_path"],
            "sha256": hashlib.sha256(Path(capture["raw_path"]).read_bytes()).hexdigest(),
        },
    )
    plan["limitations"].extend(
        [
            "Indicative Bank of Canada rate, not an executable broker quote; "
            "no conversion performed.",
            "Excludes the unknown broker exchange-rate spread, subscription costs "
            "and applicable taxes.",
            "An existing USD account and its permissions are assumed, not verified.",
            "Estimated USD credit is rounded down to cents; CAD is debited once including the fee.",
            "Retained USD funds do not incur a conversion fee on each USD stock trade.",
        ]
    )
    return plan
