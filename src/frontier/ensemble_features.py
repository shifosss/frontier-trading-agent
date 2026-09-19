"""Causal daily features, declared relative-return rules, and separate future labels.

No scaling, imputation or fitted transformations happen here. Missing features stay
NaN; any learned preprocessing must be fitted using training observations only.
Outputs use roughly 145 bytes per session/symbol, excluding the caller's market
arrays. Temporary rolling calculations are limited to 128 symbols at a time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 5)
CHUNK_SIZE = 128
FEATURE_NAMES = (
    "return_1",
    "return_2",
    "return_5",
    "return_20",
    "return_60",
    "momentum_12_1",
    "relative_log_return_1",
    "relative_log_return_2",
    "relative_log_return_5",
    "relative_log_return_20",
    "realized_volatility_5",
    "realized_volatility_20",
    "volatility_ratio_5_20",
    "atr_fraction",
    "ma_distance_20",
    "ma_distance_50",
    "ma_distance_200",
    "prior_breakout_distance_55",
    "drawdown_20",
    "dollar_activity_5_prior_20",
    "log_dollar_turnover_20",
    "benchmark_above_ma_200",
    "benchmark_return_5",
    "benchmark_return_20",
    "benchmark_realized_volatility_20",
    "cross_section_relative_rank_5",
    "relative_daily_volatility_20_lagged",
)
LABEL_NAMES = (
    "return_1",
    "return_3",
    "return_5",
    "downside_1",
    "downside_3",
    "downside_5",
)
RULE_NAMES = (
    "relative_reversal_2",
    "relative_reversal_5",
    "relative_volume_continuation_5",
)


def _positive(values):
    return np.isfinite(values) & (values > 0)


def _complete(valid, window):
    return pd.DataFrame(valid).rolling(window, min_periods=window).sum().eq(window).to_numpy()


def _benchmark_features(market, n):
    benchmark = market["benchmark"]
    values = market["adjusted"][:, benchmark] if benchmark is not None else np.full(n, np.nan)
    price = pd.Series(np.where(_positive(values), values, np.nan))
    log_return = np.log(price).diff()
    mean = price.rolling(200).mean()
    features = {
        "benchmark_above_ma_200": price.gt(mean).astype(float).where(mean.notna()),
        "benchmark_return_5": price / price.shift(5) - 1,
        "benchmark_return_20": price / price.shift(20) - 1,
        "benchmark_realized_volatility_20": price.pct_change(fill_method=None)
        .rolling(20)
        .std(ddof=1)
        * np.sqrt(252),
    }
    # The three declared rules require t-21 through t, not a new 200-day gate.
    known = _complete(price.notna().to_numpy()[:, None], 22)[:, 0]
    return log_return, features, known


def _labels(prices):
    n, m = prices.shape
    result = np.full((n, m, len(LABEL_NAMES)), np.nan, dtype=np.float32)
    for k, horizon in enumerate(HORIZONS):
        count = n - horizon - 1
        if count <= 0:
            continue
        entry = prices[1 : count + 1]
        valid = _positive(entry)
        worst = np.zeros_like(entry)
        with np.errstate(divide="ignore", invalid="ignore"):
            for step in range(1, horizon + 1):
                mark = prices[1 + step : count + 1 + step]
                valid &= _positive(mark)
                returns = mark / entry - 1
                worst = np.minimum(worst, returns)
        result[:count, :, k] = np.where(valid, returns, np.nan)
        result[:count, :, k + len(HORIZONS)] = np.where(valid, -worst, np.nan)
    return result


def build_features(market, *, stock_mask, liquidity_floor, turnover, dollar_volume):
    """Build 27 causal features and six unscaled, gross close-to-close outcomes.

    ``eligible`` contains only current stock maturity/liquidity/ATR/volatility
    requirements, independent of future labels and benchmark availability.
    ``benchmark_known`` covers the declared rules' 22-close window. Longer
    benchmark features can still be NaN; they never create an extra rule gate.

    Return features are simple returns except explicitly named relative log
    returns. Realized volatilities are annualized sample standard deviations;
    lagged relative volatility is daily, excluding the signal day's return.
    Cross-sectional ranks are average-tie percentiles in (0, 1], among eligible
    stocks with a finite five-session relative return on that same session.

    Labels at t enter at t+1 close and exit at t+1+h close, for h=1/3/5.
    Downside is max(0, -minimum close-to-entry return through that horizon),
    not an intraday excursion. All future marks must exist for either label.
    ``label_end`` keeps its absolute index even beyond the available history.
    """
    adjusted = np.asarray(market["adjusted"])
    n, m = adjusted.shape
    stock_mask = np.asarray(stock_mask, dtype=bool)
    turnover, dollar_volume = np.asarray(turnover), np.asarray(dollar_volume)
    if stock_mask.shape != (m,) or turnover.shape != (n, m) or dollar_volume.shape != (n, m):
        raise ValueError("Stock mask and dollar-volume arrays must match the market dimensions")
    output = np.full((n, m, len(FEATURE_NAMES)), np.nan, dtype=np.float32)
    eligible = np.zeros((n, m), dtype=bool)
    labels = np.full((n, m, len(LABEL_NAMES)), np.nan, dtype=np.float32)
    scores = {name: np.full((n, m), np.nan, dtype=np.float32) for name in RULE_NAMES}
    feature_index = {name: i for i, name in enumerate(FEATURE_NAMES)}
    benchmark_log, benchmark_features, benchmark_known = _benchmark_features(market, n)

    for start in range(0, m, CHUNK_SIZE):
        columns = slice(start, min(start + CHUNK_SIZE, m))
        raw = adjusted[:, columns]
        close, atr = market["close"][:, columns], market["atr"][:, columns]
        dollars, liquid = dollar_volume[:, columns], turnover[:, columns]
        prices = pd.DataFrame(np.where(_positive(raw), raw, np.nan))
        daily = prices.pct_change(fill_method=None)
        volatility = {h: daily.rolling(h).std(ddof=1) * np.sqrt(252) for h in (5, 20)}
        residual = np.log(prices).diff().sub(benchmark_log, axis=0)
        relative = {h: residual.rolling(h).sum() for h in (1, 2, 5, 20)}
        sigma = residual.shift(1).rolling(20).std(ddof=1)
        volume = pd.DataFrame(np.where(np.isfinite(dollars) & (dollars >= 0), dollars, np.nan))
        prior_volume = volume.shift(5).rolling(20).mean()
        activity = volume.rolling(5).mean() / prior_volume.where(prior_volume.gt(0))
        valid_observation = (
            _positive(raw) & _positive(close) & np.isfinite(dollars) & (dollars >= 0)
        )
        shared = (
            _complete(valid_observation, 201)
            & stock_mask[columns]
            & np.isfinite(liquid)
            & (liquid >= liquidity_floor)
            & _positive(atr)
            & volatility[20].gt(1e-12).to_numpy()
        )
        eligible[:, columns] = shared
        features = {f"return_{h}": prices / prices.shift(h) - 1 for h in (1, 2, 5, 20, 60)}
        features.update(
            momentum_12_1=(prices.shift(21) / prices.shift(252) - 1).where(
                _complete(prices.notna().to_numpy(), 253)
            ),
            volatility_ratio_5_20=volatility[5] / volatility[20].where(volatility[20].gt(0)),
            atr_fraction=np.divide(
                atr, close, out=np.full(atr.shape, np.nan), where=_positive(close)
            ),
            prior_breakout_distance_55=prices / prices.shift(1).rolling(55).max() - 1,
            drawdown_20=prices / prices.rolling(20).max() - 1,
            dollar_activity_5_prior_20=activity,
            log_dollar_turnover_20=np.log(np.where(_positive(liquid), liquid, np.nan)),
            relative_daily_volatility_20_lagged=sigma,
        )
        features.update({f"relative_log_return_{h}": values for h, values in relative.items()})
        features.update({f"realized_volatility_{h}": values for h, values in volatility.items()})
        features.update(
            {f"ma_distance_{h}": prices / prices.rolling(h).mean() - 1 for h in (20, 50, 200)}
        )
        for name, values in features.items():
            output[:, columns, feature_index[name]] = np.asarray(values)
        for name, values in benchmark_features.items():
            output[:, columns, feature_index[name]] = values.to_numpy()[:, None]

        rule_eligible = (
            shared
            & benchmark_known[:, None]
            & np.isfinite(sigma.to_numpy())
            & sigma.gt(0).to_numpy()
            & np.isfinite(activity.to_numpy())
            & prior_volume.gt(0).to_numpy()
        )
        for horizon in (2, 5):
            score = (-relative[horizon] / (sigma * np.sqrt(horizon))).where(
                rule_eligible & relative[horizon].lt(0).to_numpy()
            )
            scores[f"relative_reversal_{horizon}"][:, columns] = score.to_numpy()
        scores["relative_volume_continuation_5"][:, columns] = (
            (relative[5] / (sigma * np.sqrt(5)))
            .where(rule_eligible & relative[5].gt(0).to_numpy() & activity.ge(1.5).to_numpy())
            .to_numpy()
        )
        labels[:, columns] = _labels(raw)

    relative_column = feature_index["relative_log_return_5"]
    rank_column = feature_index["cross_section_relative_rank_5"]
    for start in range(0, n, CHUNK_SIZE):
        rows = slice(start, min(start + CHUNK_SIZE, n))
        values = pd.DataFrame(output[rows, :, relative_column]).where(eligible[rows])
        output[rows, :, rank_column] = values.rank(axis=1, method="average", pct=True).to_numpy()
    return {
        "X": output,
        "feature_names": list(FEATURE_NAMES),
        "eligible": eligible,
        "benchmark_known": benchmark_known,
        "labels": labels,
        "label_names": list(LABEL_NAMES),
        "label_end": np.arange(n)[:, None] + 1 + np.asarray(HORIZONS)[None, :],
        "rule_scores": scores,
    }
