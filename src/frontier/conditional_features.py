"""Causal setup context for conditional selection; gather only the rows a model needs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from frontier.ensemble_features import CHUNK_SIZE
from frontier.ensemble_features import FEATURE_NAMES as BASE_FEATURE_NAMES

SETUP_NAMES = (
    "relative_reversal_5",
    "relative_volume_continuation_5",
    "compression_continuation_5",
)
FEATURE_NAMES = (
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


def build_context(market, features):
    """Add three setup memberships/ranks and three dated benchmark inputs.

    Unavailable setups have indicator/rank zero, while an unavailable market
    observation remains NaN. Optional long-context warmup never gates a setup.
    Compression is a continuation subset; its extra static rank is deliberate.
    No target, future action, or account outcome is read.
    """
    if tuple(features["feature_names"]) != BASE_FEATURE_NAMES:
        raise ValueError("Conditional selection requires the declared base feature order")
    X = features["X"]
    n, m = X.shape[:2]
    names = {name: i for i, name in enumerate(BASE_FEATURE_NAMES)}
    shared = features["eligible"] & features["benchmark_known"][:, None]
    indicators = np.zeros((n, m, 3), dtype=bool)
    ranks = np.zeros((n, m, 3), dtype=np.float32)
    compression = (X[:, :, names["volatility_ratio_5_20"]] < 1) & (
        X[:, :, names["relative_log_return_20"]] > 0
    )
    for k, setup in enumerate(SETUP_NAMES):
        source = features["rule_scores"][SETUP_NAMES[1] if k == 2 else setup]
        known = shared & np.isfinite(source)
        if k == 2:
            known &= compression
        indicators[:, :, k] = known
        for start in range(0, n, CHUNK_SIZE):
            rows = slice(start, min(start + CHUNK_SIZE, n))
            ranks[rows, :, k] = (
                pd.DataFrame(source[rows])
                .where(known[rows])
                .rank(axis=1, method="average", pct=True)
                .fillna(0)
                .to_numpy(dtype=np.float32)
            )
    eligible = indicators.any(axis=2)
    static_scores = np.where(eligible, ranks.mean(axis=2), np.nan).astype(np.float32)
    j = market["benchmark"]
    values = np.asarray(market["adjusted"][:, j]) if j is not None else np.full(n, np.nan)
    price = pd.Series(np.where(np.isfinite(values) & (values > 0), values, np.nan))
    volatility = price.pct_change(fill_method=None).rolling(20).std(ddof=1) * np.sqrt(252)
    prior_median = volatility.shift(1).rolling(252, min_periods=252).median()
    market_context = np.column_stack(
        (
            price / price.rolling(200, min_periods=200).mean() - 1,
            volatility,
            volatility / prior_median.where(prior_median > 0),
        )
    ).astype(np.float32)
    return {
        "eligible": eligible,
        "setup_indicators": indicators,
        "setup_ranks": ranks,
        "static_scores": static_scores,
        "market_context": market_context,
        "feature_names": list(FEATURE_NAMES),
    }


def gather_rows(features, context, rows, columns):
    """Gather aligned date/symbol rows without duplicating the full 37-input tensor.

    The declared 37-input schema intentionally repeats benchmark RV20 and stock
    RV5/RV20 from the base schema; these aliases are not additional information.
    """
    rows, columns = np.asarray(rows), np.asarray(columns)
    if rows.ndim != 1 or columns.shape != rows.shape:
        raise ValueError("Date and symbol indices must be aligned one-dimensional arrays")
    base = features["X"][rows, columns]
    return np.column_stack(
        (
            base,
            context["setup_indicators"][rows, columns],
            context["setup_ranks"][rows, columns],
            context["market_context"][rows],
            base[:, BASE_FEATURE_NAMES.index("volatility_ratio_5_20")],
        )
    ).astype(np.float32, copy=False)
