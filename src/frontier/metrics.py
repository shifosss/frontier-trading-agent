"""Descriptive FX-aware metrics, never independent execution/accounting."""

import numpy as np
import pandas as pd


def calculate_metrics(curve, fills, config, incomplete=False):
    frame = pd.DataFrame(curve)
    nav = frame.nav.to_numpy(dtype=float)
    daily = frame.assign(day=pd.to_datetime(frame.timestamp).dt.date).groupby("day").nav.last()
    # Preserve pre-trade initial NAV, including all first-day costs.
    daily_nav = np.r_[nav[0], daily.to_numpy()]
    returns = daily_nav[1:] / daily_nav[:-1] - 1
    daily_return_std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0
    fees = {c: sum(f["commission"] for f in fills if f["currency"] == c) for c in ("USD", "CAD")}
    slippage = {
        c: sum(f["slippage_cost"] for f in fills if f["currency"] == c) for c in ("USD", "CAD")
    }
    turnover = 0.0
    contribution = {"USD": 0.0, "CAD": 0.0}
    for fill in fills:
        timestamp = fill["timestamp"]
        at = frame.loc[frame.timestamp <= timestamp].iloc[-1]
        conversion = at.usd_cad if fill["currency"] == "USD" else 1.0
        if config.base_currency == "USD":
            conversion /= at.usd_cad
        turnover += fill["quantity"] * fill["price"] * conversion
    final = frame.iloc[-1]
    contribution["USD"] = float(
        final.cash_usd
        + final.positions_value_usd
        + final.get("dividend_receivable_usd", 0)
        - config.initial_cash_usd
    )
    contribution["CAD"] = float(
        final.cash_cad
        + final.positions_value_cad
        + final.get("dividend_receivable_cad", 0)
        - config.initial_cash_cad
    )
    ci = None
    if len(returns) >= 10:
        block = min(5, len(returns))
        rng = np.random.default_rng(config.seed)
        samples = []
        for _ in range(500):
            indices = np.concatenate(
                [
                    (start + np.arange(block)) % len(returns)
                    for start in rng.integers(
                        0, len(returns), size=int(np.ceil(len(returns) / block))
                    )
                ]
            )
            samples.append(float(np.prod(1 + returns[indices[: len(returns)]]) - 1))
        low, high = np.quantile(samples, [0.025, 0.975])
        ci = {
            "low": float(low),
            "high": float(high),
            "seed": config.seed,
            "block_length": block,
            "resamples": 500,
            "method": "circular daily block bootstrap",
            "interpretation": "descriptive short-sample raw NAV return; no predictive guarantee",
        }
    result = {
        "initial_nav": float(nav[0]),
        "final_nav": float(nav[-1]),
        "total_return": None if incomplete else float(nav[-1] / nav[0] - 1),
        "raw_price_return": float(nav[-1] / nav[0] - 1),
        "max_drawdown": float(np.min(nav / np.maximum.accumulate(nav) - 1)),
        "annualized_volatility": daily_return_std * np.sqrt(252)
        if daily_return_std > 1e-14
        else None,
        "sharpe": float(np.mean(returns) / daily_return_std * np.sqrt(252))
        if daily_return_std > 1e-14
        else None,
        "trade_count": len(fills),
        "turnover": turnover / nav[0],
        "average_exposure": float(frame.gross_exposure.mean()),
        "fees": fees,
        "slippage": slippage,
        "bootstrap_ci": ci,
        "native_market_contribution": contribution,
        "metric_basis": (
            "daily marked NAV including recorded gross dividend receivables and cash payments; "
            "zero risk-free rate, 252 sessions; unrecorded actions remain excluded"
        ),
    }
    return result
