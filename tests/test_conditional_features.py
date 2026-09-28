from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from frontier.conditional_features import FEATURE_NAMES, SETUP_NAMES, build_context, gather_rows
from frontier.ensemble_features import FEATURE_NAMES as BASE_FEATURE_NAMES
from frontier.ensemble_features import build_features


def inputs(n=360):
    t = np.arange(n)
    benchmark = 0.0007 + 0.006 * np.sin(t / 8)
    residuals = np.column_stack(
        (0.004 * np.sin(t / 3), 0.005 * np.cos(t / 6), 0.003 * np.sin(t / 5), np.zeros(n))
    )
    prices = np.exp(np.cumsum(benchmark[:, None] + residuals, axis=0)) * [30, 50, 70, 100]
    market = {
        "symbols": ["AAA", "BBB", "CCC", "SPY"],
        "adjusted": prices,
        "close": prices.copy(),
        "atr": prices * 0.02,
        "benchmark": 3,
    }
    dollars = np.repeat((10_000_000 * (1 + 3 * ((t // 7) % 5 == 0)))[:, None], 4, axis=1)
    options = {
        "stock_mask": np.array([True, True, True, False]),
        "liquidity_floor": 5_000_000,
        "dollar_volume": dollars.astype(float),
        "turnover": pd.DataFrame(dollars).rolling(20).mean().to_numpy(),
    }
    return market, options


def test_union_overlap_control_ranks_and_ordered_row_gather():
    market, options = inputs()
    features = build_features(market, **options)
    t = 300
    names = {name: i for i, name in enumerate(features["feature_names"])}
    features["rule_scores"]["relative_reversal_5"][t] = [2, 2, np.nan, np.nan]
    features["rule_scores"]["relative_volume_continuation_5"][t] = [np.nan, np.nan, 4, np.nan]
    features["X"][t, 2, names["volatility_ratio_5_20"]] = 0.8
    features["X"][t, 2, names["relative_log_return_20"]] = 0.1
    features["benchmark_known"] = features["benchmark_known"].copy()
    features["benchmark_known"][t + 1] = False
    original = features["X"]
    context = build_context(market, features)
    assert SETUP_NAMES == (
        "relative_reversal_5",
        "relative_volume_continuation_5",
        "compression_continuation_5",
    )
    assert FEATURE_NAMES == (
        *BASE_FEATURE_NAMES,
        "setup_reversal_5",
        "setup_volume_continuation_5",
        "setup_compression_continuation_5",
        "percentile_reversal_5",
        "percentile_volume_continuation_5",
        "percentile_compression_continuation_5",
        "context_benchmark_distance_ma200",
        "context_benchmark_rv20",
        "context_benchmark_rv20_to_prior252_median",
        "context_stock_rv5_to_rv20",
    )
    assert context["feature_names"] == list(FEATURE_NAMES)
    assert features["X"] is original and "X" not in context
    np.testing.assert_array_equal(context["eligible"][t], [True, True, True, False])
    assert not context["eligible"][t + 1].any()
    np.testing.assert_array_equal(
        context["setup_indicators"][t, :3], [[1, 0, 0], [1, 0, 0], [0, 1, 1]]
    )
    np.testing.assert_allclose(
        context["setup_ranks"][t, :3], [[0.75, 0, 0], [0.75, 0, 0], [0, 1, 1]]
    )
    np.testing.assert_allclose(context["static_scores"][t, :3], [0.25, 0.25, 2 / 3])
    assert np.isnan(context["static_scores"][t, 3])
    assert np.isnan(context["static_scores"][t + 1]).all()
    assert (context["setup_ranks"][t + 1] == 0).all()
    rows, columns = np.array([t, t, t + 1]), np.array([0, 2, 0])
    gathered = gather_rows(features, context, rows, columns)
    assert gathered.shape == (3, 37) and gathered.dtype == np.float32
    np.testing.assert_array_equal(gathered[:, :27], original[rows, columns])
    np.testing.assert_array_equal(gathered[:, 27:30], [[1, 0, 0], [0, 1, 1], [0, 0, 0]])
    np.testing.assert_array_equal(gathered[:, 30:33], [[0.75, 0, 0], [0, 1, 1], [0, 0, 0]])
    np.testing.assert_array_equal(gathered[:, 33:36], context["market_context"][rows])
    np.testing.assert_array_equal(
        gathered[:, 36], original[rows, columns, names["volatility_ratio_5_20"]]
    )
    empty = np.array([], dtype=int)
    assert gather_rows(features, context, empty, empty).shape == (0, 37)
    with pytest.raises(ValueError, match="aligned"):
        gather_rows(features, context, [t, t], [0])


def test_gates_and_optional_context_warmup_preserve_zero_vs_missing():
    market, options = inputs()
    features = build_features(market, **options)
    context = build_context(market, features)
    X, names = features["X"], {name: i for i, name in enumerate(features["feature_names"])}
    shared = features["eligible"] & features["benchmark_known"][:, None]
    reversal = np.isfinite(features["rule_scores"]["relative_reversal_5"]) & shared
    continuation = np.isfinite(features["rule_scores"]["relative_volume_continuation_5"]) & shared
    compression = (
        continuation
        & (X[:, :, names["volatility_ratio_5_20"]] < 1)
        & (X[:, :, names["relative_log_return_20"]] > 0)
    )
    assert reversal.any() and continuation.any() and compression.any()
    np.testing.assert_array_equal(context["setup_indicators"][:, :, 0], reversal)
    np.testing.assert_array_equal(context["setup_indicators"][:, :, 1], continuation)
    np.testing.assert_array_equal(context["setup_indicators"][:, :, 2], compression)
    assert not context["eligible"][:200].any()
    assert context["eligible"][200:272].any()  # Optional long context does not add a setup gate.
    assert np.isnan(context["market_context"][:272, 2]).all()
    assert np.isfinite(context["market_context"][272:, 2]).all()
    t = 300
    price = market["adjusted"][:, 3]
    daily = price[1:] / price[:-1] - 1
    rv20 = np.array(
        [np.std(daily[i - 20 : i], ddof=1) * np.sqrt(252) for i in range(t - 252, t + 1)]
    )
    expected = [
        price[t] / price[t - 199 : t + 1].mean() - 1,
        rv20[-1],
        rv20[-1] / np.median(rv20[:-1]),
    ]
    np.testing.assert_allclose(context["market_context"][t], expected, rtol=2e-6)
    np.testing.assert_array_equal(
        context["market_context"][:, 1], X[:, 0, names["benchmark_realized_volatility_20"]]
    )
    constant = deepcopy(market)
    constant["adjusted"][:, 3] = 100
    constant["close"][:, 3] = 100
    flat = build_context(constant, build_features(constant, **options))
    assert flat["market_context"][300, 0] == 0  # Exact MA distance is known, not missing.
    assert flat["market_context"][300, 1] == 0  # Observed zero volatility is known.
    assert np.isnan(flat["market_context"][300, 2])  # Ratio to zero median is unavailable.
    constant["benchmark"] = None
    unknown = build_context(constant, build_features(constant, **options))
    assert not unknown["eligible"].any()
    assert np.isnan(unknown["market_context"]).all()
    assert (unknown["setup_ranks"] == 0).all()


def test_future_prices_activity_and_labels_cannot_change_prior_conditional_inputs():
    market, options = inputs()
    features = build_features(market, **options)
    original = build_context(market, features)
    cutoff = 300
    future, changed_options = deepcopy(market), deepcopy(options)
    for name in ("adjusted", "close", "atr"):
        future[name][cutoff + 1 :] *= np.linspace(0.1, 4, len(future[name]) - cutoff - 1)[:, None]
    changed_options["dollar_volume"][cutoff + 1 :] *= 100
    changed_options["turnover"][cutoff + 1 :] *= 100
    changed_features = build_features(future, **changed_options)
    changed = build_context(future, changed_features)
    for name in ("eligible", "setup_indicators", "setup_ranks", "static_scores", "market_context"):
        np.testing.assert_array_equal(original[name][: cutoff + 1], changed[name][: cutoff + 1])
    rows, columns = np.array([200, 271, 299, 300]), np.array([0, 1, 2, 0])
    np.testing.assert_array_equal(
        gather_rows(features, original, rows, columns),
        gather_rows(changed_features, changed, rows, columns),
    )
    assert not np.allclose(
        features["labels"][cutoff], changed_features["labels"][cutoff], equal_nan=True
    )
    features["labels"][:] = 999999
    features["label_end"][:] = -999
    poisoned = build_context(market, features)
    for name in ("eligible", "setup_indicators", "setup_ranks", "static_scores", "market_context"):
        np.testing.assert_array_equal(original[name], poisoned[name])
    without_targets = {k: v for k, v in features.items() if k not in {"labels", "label_end"}}
    np.testing.assert_array_equal(
        gather_rows(without_targets, build_context(market, without_targets), rows, columns),
        gather_rows(features, original, rows, columns),
    )
