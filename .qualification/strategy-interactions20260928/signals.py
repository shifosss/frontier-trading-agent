"""Predeclared strategy-only signals; no model fitting, broker calls or price repair."""
from __future__ import annotations

import numpy as np
import pandas as pd

POLICIES = (
    "relative_reversal_2",
    "relative_reversal_5",
    "trend_pullback",
    "relative_volume_continuation_5",
    "beta_residual_reversal_2",
    "trend_conditioned_reversal_5",
    "compression_continuation_5",
    "equal_percentile_blend",
    "volatility_regime_selector",
)
SPECIFICATION = {
    "version": "strategy-interactions-20260928-v1",
    "policies": list(POLICIES),
    "beta_estimation_sessions": 60,
    "beta_estimation_lag": 1,
    "residual_volatility_sessions": 20,
    "residual_volatility_lag": 1,
    "trend_mean_sessions": 200,
    "relative_trend_sessions": 20,
    "compression_volatility_ratio": "annualized_rv5 / annualized_rv20 < 1",
    "regime_realized_volatility_sessions": 20,
    "regime_median_prior_observations": 252,
    "regime_median_lag": 1,
    "regime_rule": "continuation if benchmark above MA200 and RV20 <= prior-252 median; reversal otherwise; unknown abstains",
    "score_dtype": "float32; intermediate price calculations float64",
    "ties": "alphabetical symbol order via stable descending sort",
    "forward_labels_read": False,
    "source_repairs": None,
}


def _preserved_trend_order(market):
    order = market["ranking"]["trend_pullback"]
    counts = market["counts"]["trend_pullback"]
    scores = np.full(order.shape, np.nan, dtype=np.float32)
    for row, count in enumerate(counts):
        count = int(count)
        scores[row, order[row, :count]] = np.arange(count, 0, -1, dtype=np.float32)
    return scores


def _beta_reversal(market, features):
    prices = np.asarray(market["adjusted"], dtype=float)
    benchmark = pd.Series(prices[:, market["benchmark"]])
    benchmark_return = np.log(benchmark).diff()
    beta_variance = benchmark_return.rolling(60).var(ddof=1).shift(1)
    variance20 = benchmark_return.rolling(20).var(ddof=1).shift(1)
    benchmark_two = benchmark_return.rolling(2).sum()
    scores = np.full(prices.shape, np.nan, dtype=np.float32)
    # Preserve the same shared eligibility and prior-volume availability as the old rule.
    X = features["X"]
    names = {name: i for i, name in enumerate(features["feature_names"])}
    rule_known = (
        features["eligible"]
        & features["benchmark_known"][:, None]
        & np.isfinite(X[:, :, names["relative_daily_volatility_20_lagged"]])
        & (X[:, :, names["relative_daily_volatility_20_lagged"]] > 0)
        & np.isfinite(X[:, :, names["dollar_activity_5_prior_20"]])
    )
    for start in range(0, prices.shape[1], 128):
        columns = slice(start, min(start + 128, prices.shape[1]))
        returns = np.log(pd.DataFrame(prices[:, columns])).diff()
        beta = returns.rolling(60).cov(benchmark_return).shift(1).div(beta_variance, axis=0)
        variance = returns.rolling(20).var(ddof=1).shift(1)
        covariance = returns.rolling(20).cov(benchmark_return).shift(1)
        residual_variance = variance + beta.pow(2).mul(variance20, axis=0) - 2 * beta * covariance
        residual_two = returns.rolling(2).sum() - beta.mul(benchmark_two, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            scaled = -residual_two / np.sqrt(2 * residual_variance)
        valid = (
            rule_known[:, columns]
            & beta.notna().to_numpy()
            & residual_variance.gt(0).to_numpy()
            & residual_two.lt(0).to_numpy()
        )
        scores[:, columns] = scaled.where(valid).to_numpy(dtype=np.float32)
    return scores


def build_strategy_signals(market, features):
    """Return nine date-by-symbol score arrays and observable regime diagnostics.

    Required market keys: adjusted, benchmark, ranking/trend_pullback,
    counts/trend_pullback. Features are an unchanged build_features result.
    No target, outcome, realized trade or future action field is used.
    """
    base = features["rule_scores"]
    scores = {name: base[name].copy() for name in (
        "relative_reversal_2", "relative_reversal_5", "relative_volume_continuation_5"
    )}
    scores["trend_pullback"] = _preserved_trend_order(market)
    scores["beta_residual_reversal_2"] = _beta_reversal(market, features)
    names = {name: i for i, name in enumerate(features["feature_names"])}
    X = features["X"]
    trend = (X[:, :, names["ma_distance_200"]] > 0) & (
        X[:, :, names["relative_log_return_20"]] > 0
    )
    scores["trend_conditioned_reversal_5"] = np.where(
        trend, base["relative_reversal_5"], np.nan
    ).astype(np.float32)
    compressed = (X[:, :, names["volatility_ratio_5_20"]] < 1) & (
        X[:, :, names["relative_log_return_20"]] > 0
    )
    scores["compression_continuation_5"] = np.where(
        compressed, base["relative_volume_continuation_5"], np.nan
    ).astype(np.float32)
    reversal, continuation = base["relative_reversal_5"], base["relative_volume_continuation_5"]
    reversal_rank = pd.DataFrame(reversal).rank(axis=1, method="average", pct=True).to_numpy()
    continuation_rank = pd.DataFrame(continuation).rank(axis=1, method="average", pct=True).to_numpy()
    known = np.isfinite(reversal) | np.isfinite(continuation)
    blend = (np.nan_to_num(reversal_rank) + np.nan_to_num(continuation_rank)) / 2
    scores["equal_percentile_blend"] = np.where(known, blend, np.nan).astype(np.float32)
    benchmark = pd.Series(np.asarray(market["adjusted"], dtype=float)[:, market["benchmark"]])
    volatility = benchmark.pct_change(fill_method=None).rolling(20).std(ddof=1) * np.sqrt(252)
    threshold = volatility.shift(1).rolling(252, min_periods=252).median()
    average = benchmark.rolling(200, min_periods=200).mean()
    regime_known = (volatility.notna() & threshold.notna() & average.notna()).to_numpy()
    uptrend = benchmark.gt(average).to_numpy()
    calm = volatility.le(threshold).to_numpy()
    continuation_state = regime_known & uptrend & calm
    state = np.where(regime_known, np.where(continuation_state, 1, 2), 0).astype(np.int8)
    scores["volatility_regime_selector"] = np.where(
        regime_known[:, None], np.where(continuation_state[:, None], continuation, reversal), np.nan
    ).astype(np.float32)
    return {
        "scores": {name: scores[name] for name in POLICIES},
        "context": {
            "regime_state": state,
            "benchmark_volatility20": volatility.to_numpy(),
            "benchmark_prior252_volatility_median": threshold.to_numpy(),
            "benchmark_above_ma200": uptrend,
            "regime_known": regime_known,
        },
        "specification": SPECIFICATION,
    }


def self_check():
    """Independent synthetic arithmetic, gate, control and chronology checks."""
    from frontier.ensemble_features import build_features

    n, m = 360, 4
    t = np.arange(n, dtype=float)
    amplitude = np.where(t < 250, 0.012, 0.001)
    bm_returns = 0.001 + amplitude * np.sin(t * 1.43)
    stock_returns = np.column_stack((
        bm_returns,
        1.6 * bm_returns + 0.008 * np.sin(t * 0.91),
        0.6 * bm_returns + 0.011 * np.cos(t * 0.69),
        1.1 * bm_returns + 0.006 * np.sin(t * 0.37),
    ))
    prices = 50 * np.exp(np.cumsum(stock_returns, axis=0))
    volume = np.full((n, m), 10_000_000.0)
    market = {
        "adjusted": prices, "close": prices.copy(), "atr": prices * 0.015,
        "benchmark": 0, "n": n, "symbols": ["BENCH", "ONE", "THREE", "TWO"],
        "ranking": {"trend_pullback": np.tile(np.array([2, 1, 3, 0]), (n, 1))},
        "counts": {"trend_pullback": np.full(n, 2)},
    }
    def features_for(value):
        return build_features(value, stock_mask=np.array([False, True, True, True]),
                              liquidity_floor=5_000_000, turnover=volume, dollar_volume=volume)
    features = features_for(market)
    result = build_strategy_signals(market, features)
    assert tuple(result["scores"]) == POLICIES
    for values in result["scores"].values():
        assert values.shape == (n, m) and values.dtype == np.float32
    assert np.array_equal(np.argsort(-result["scores"]["trend_pullback"], axis=1)[:, :2],
                          market["ranking"]["trend_pullback"][:, :2])
    for name in ("relative_reversal_2", "relative_reversal_5", "relative_volume_continuation_5"):
        np.testing.assert_array_equal(result["scores"][name], features["rule_scores"][name])
    finite = np.argwhere(np.isfinite(result["scores"]["beta_residual_reversal_2"]))
    assert len(finite)
    row, col = map(int, finite[-1])
    returns = np.diff(np.log(prices), axis=0)
    prior60, prior20 = returns[row - 61:row - 1], returns[row - 21:row - 1]
    beta = np.cov(prior60[:, col], prior60[:, 0], ddof=1)[0, 1] / np.var(prior60[:, 0], ddof=1)
    residual20 = prior20[:, col] - beta * prior20[:, 0]
    shock = np.sum(returns[row - 2:row, col] - beta * returns[row - 2:row, 0])
    expected = -shock / (np.std(residual20, ddof=1) * np.sqrt(2))
    np.testing.assert_allclose(result["scores"]["beta_residual_reversal_2"][row, col], expected,
                               rtol=2e-6, atol=1e-7)
    context = result["context"]
    assert not context["regime_known"][:272].any() and context["regime_known"][272]
    assert (context["regime_state"] == 1).any()
    rv = context["benchmark_volatility20"]
    np.testing.assert_allclose(context["benchmark_prior252_volatility_median"][300],
                               np.median(rv[48:300]), rtol=1e-12)
    # Future source changes must leave every earlier score and regime unchanged.
    cutoff = 310
    mutated = dict(market)
    mutated["adjusted"] = prices.copy()
    mutated["adjusted"][cutoff:] *= np.linspace(0.2, 1.8, n-cutoff)[:, None]
    mutated["close"] = mutated["adjusted"].copy()
    mutated["atr"] = mutated["close"] * 0.015
    changed = build_strategy_signals(mutated, features_for(mutated))
    for name in POLICIES:
        np.testing.assert_array_equal(result["scores"][name][:cutoff], changed["scores"][name][:cutoff])
    for name in context:
        np.testing.assert_array_equal(context[name][:cutoff], changed["context"][name][:cutoff])
    assert (changed["context"]["regime_state"][cutoff:] == 2).any()
    # Labels are explicitly poisonable without affecting these strategy-only signals.
    features["labels"][:] = 123456789.0
    poisoned = build_strategy_signals(market, features)
    for name in POLICIES:
        np.testing.assert_array_equal(result["scores"][name], poisoned["scores"][name])
    # Isolate interaction gates and rank blend with hand-specified current features.
    row = 300
    fidx = {name: i for i, name in enumerate(features["feature_names"])}
    for name in ("relative_reversal_5", "relative_volume_continuation_5"):
        features["rule_scores"][name][row] = np.nan
    features["rule_scores"]["relative_reversal_5"][row, 1:3] = [2, 1]
    features["rule_scores"]["relative_volume_continuation_5"][row, 3] = 3
    features["X"][row, :, fidx["relative_log_return_20"]] = 0.1
    features["X"][row, :, fidx["ma_distance_200"]] = [0.1, 0.1, -0.1, 0.1]
    features["X"][row, :, fidx["volatility_ratio_5_20"]] = 0.8
    gates = build_strategy_signals(market, features)["scores"]
    assert gates["trend_conditioned_reversal_5"][row, 1] == 2
    assert np.isnan(gates["trend_conditioned_reversal_5"][row, 2])
    assert gates["compression_continuation_5"][row, 3] == 3
    np.testing.assert_array_equal(gates["equal_percentile_blend"][row, 1:], [0.5, 0.25, 0.5])
    return {"status": "passed", "checks": ["nine shapes and dtypes", "original controls preserved",
        "independent beta residual arithmetic", "273-close regime warmup", "lagged median arithmetic",
        "both regime branches", "future perturbation invariance", "unused labels poison test",
        "trend/compression gates", "equal percentile mixture"], "synthetic_observations": n*m}


if __name__ == "__main__":
    import json
    print(json.dumps(self_check(), indent=2))
