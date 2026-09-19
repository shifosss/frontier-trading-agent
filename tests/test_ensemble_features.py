from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from frontier.ensemble_features import FEATURE_NAMES, HORIZONS, RULE_NAMES, build_features


def inputs(n=310):
    t = np.arange(n)
    benchmark = 0.001 + 0.002 * np.sin(t / 8)
    residuals = np.column_stack(
        [0.002 * np.sin(t / 3), 0.003 * np.cos(t / 6), 0.004 * np.sin(t / 5), np.zeros(n)]
    )
    adjusted = np.exp(np.cumsum(benchmark[:, None] + residuals, axis=0)) * [30, 50, 70, 100]
    market = {
        "symbols": ["AAA", "BBB", "CCC", "SPY"],
        "sessions": pd.bdate_range("2020-01-02", periods=n).strftime("%Y-%m-%d").tolist(),
        "adjusted": adjusted,
        "close": adjusted.copy(),
        "atr": adjusted * 0.02,
        "benchmark": 3,
        "market_trend": np.ones(n, dtype=bool),
        "market_trend_known": np.ones(n, dtype=bool),
    }
    dollars = np.full((n, 4), 10_000_000.0)
    options = {
        "stock_mask": np.array([True, True, True, False]),
        "liquidity_floor": 5_000_000,
        "turnover": pd.DataFrame(dollars).rolling(20).mean().to_numpy(copy=True),
        "dollar_volume": dollars,
    }
    return market, options


def feature(result, name):
    return result["X"][:, :, result["feature_names"].index(name)]


def test_contract_maturity_and_separate_long_feature_warmup():
    market, options = inputs()
    result = build_features(market, **options)
    assert result["X"].shape == (310, 4, 27)
    assert result["X"].dtype == result["labels"].dtype == np.float32
    assert result["eligible"].dtype == result["benchmark_known"].dtype == bool
    assert result["labels"].shape == (310, 4, 6)
    assert list(result["rule_scores"]) == list(RULE_NAMES)
    assert result["feature_names"] == list(FEATURE_NAMES)
    assert not result["eligible"][:200].any()
    assert result["eligible"][200:, :3].all()
    assert not result["eligible"][:, 3].any()
    assert np.isnan(feature(result, "momentum_12_1")[200:252]).all()
    assert np.isfinite(feature(result, "momentum_12_1")[252:]).all()
    assert result["label_end"][-1].tolist() == [311, 313, 315]
    assert np.isnan(result["labels"][-2:, :, 0]).all()
    assert np.isnan(result["labels"][-6:, :, 2]).all()


def test_labels_exact_next_close_timing_and_close_path_downside():
    market, options = inputs()
    t = 260
    # Signal-to-entry's enormous return is deliberately outside the outcome.
    market["adjusted"][t : t + 7, 0] = [1, 100, 110, 90, 120, 80, 130]
    market["adjusted"][t : t + 7, 3] = [100, 100, 50, 40, 30, 20, 10]
    result = build_features(market, **options)
    np.testing.assert_allclose(result["labels"][t, 0], [0.1, 0.2, 0.3, 0, 0.1, 0.2])
    np.testing.assert_array_equal(result["label_end"][t], t + 1 + np.array(HORIZONS))
    # Positive returns are raw stock returns, despite the falling benchmark.
    assert result["labels"][t, 0, 0] == pytest.approx(0.1)


@pytest.mark.parametrize("missing", [np.nan, 0.0, -1.0])
def test_missing_intermediate_future_marks_invalidate_both_labels_only(missing):
    market, options = inputs()
    original = build_features(market, **options)
    t = 260
    market["adjusted"][t + 3, 0] = missing
    changed = build_features(market, **options)
    np.testing.assert_array_equal(changed["eligible"][: t + 1], original["eligible"][: t + 1])
    np.testing.assert_allclose(changed["X"][: t + 1], original["X"][: t + 1], equal_nan=True)
    assert np.isfinite(changed["labels"][t, 0, [0, 3]]).all()
    assert np.isnan(changed["labels"][t, 0, [1, 2, 4, 5]]).all()
    for name in RULE_NAMES:
        np.testing.assert_allclose(
            changed["rule_scores"][name][: t + 1],
            original["rule_scores"][name][: t + 1],
            equal_nan=True,
        )


def test_future_mutation_cannot_change_features_ranks_or_eligibility():
    market, options = inputs()
    original = build_features(market, **options)
    t = 260
    for name in ("adjusted", "close", "atr"):
        market[name][t + 1 :] *= np.linspace(0.1, 4, len(market[name]) - t - 1)[:, None]
    options["dollar_volume"][t + 1 :] *= 100
    options["turnover"][t + 1 :] *= 100
    changed = build_features(market, **options)
    np.testing.assert_allclose(changed["X"][: t + 1], original["X"][: t + 1], equal_nan=True)
    np.testing.assert_array_equal(changed["eligible"][: t + 1], original["eligible"][: t + 1])
    np.testing.assert_array_equal(
        changed["benchmark_known"][: t + 1], original["benchmark_known"][: t + 1]
    )
    for name in RULE_NAMES:
        np.testing.assert_allclose(
            changed["rule_scores"][name][: t + 1],
            original["rule_scores"][name][: t + 1],
            equal_nan=True,
        )
    assert not np.allclose(changed["labels"][t], original["labels"][t], equal_nan=True)


def test_exact_relative_rules_lagged_sigma_and_nonoverlapping_activity():
    market, options = inputs()
    t = 260
    # A rising stock can be a relative reversal: +1% versus benchmark +2%.
    market["adjusted"][t, 0] = market["adjusted"][t - 1, 0] * 1.01
    market["adjusted"][t - 1, 0] = market["adjusted"][t - 2, 0] * 1.01
    market["adjusted"][t, 0] = market["adjusted"][t - 1, 0] * 1.01
    market["adjusted"][t - 1, 3] = market["adjusted"][t - 2, 3] * 1.02
    market["adjusted"][t, 3] = market["adjusted"][t - 1, 3] * 1.02
    options["dollar_volume"][t - 24 : t - 4, 0] = 10_000_000
    options["dollar_volume"][t - 4 : t + 1, 0] = 30_000_000
    result = build_features(market, **options)
    stock_log = np.diff(np.log(market["adjusted"][:, 0]), prepend=np.nan)
    benchmark_log = np.diff(np.log(market["adjusted"][:, 3]), prepend=np.nan)
    residual = stock_log - benchmark_log
    sigma = np.std(residual[t - 20 : t], ddof=1)
    score = -sum(residual[t - 1 : t + 1]) / (sigma * np.sqrt(2))
    assert result["rule_scores"]["relative_reversal_2"][t, 0] == pytest.approx(score)
    assert feature(result, "relative_daily_volatility_20_lagged")[t, 0] == pytest.approx(sigma)
    assert feature(result, "dollar_activity_5_prior_20")[t, 0] == pytest.approx(3)
    assert feature(result, "return_2")[t, 0] > 0
    assert feature(result, "relative_log_return_2")[t, 0] < 0
    changed = deepcopy(market)
    changed["adjusted"][t, 0] *= 2
    second = build_features(changed, **options)
    assert (
        feature(second, "relative_daily_volatility_20_lagged")[t, 0]
        == feature(result, "relative_daily_volatility_20_lagged")[t, 0]
    )


def test_relative_volume_continuation_can_be_negative_absolute_return():
    market, options = inputs()
    t = 260
    for offset in range(1, 6):
        market["adjusted"][t - 5 + offset, 0] = market["adjusted"][t - 5, 0] * 0.99**offset
        market["adjusted"][t - 5 + offset, 3] = market["adjusted"][t - 5, 3] * 0.98**offset
    options["dollar_volume"][t - 4 : t + 1, 0] *= 1.5
    result = build_features(market, **options)
    assert feature(result, "return_5")[t, 0] < 0
    assert result["rule_scores"]["relative_volume_continuation_5"][t, 0] > 0
    assert np.isnan(result["rule_scores"]["relative_reversal_5"][t, 0])
    options["dollar_volume"][t - 4 : t + 1, 0] *= 1.499 / 1.5
    below = build_features(market, **options)
    assert np.isnan(below["rule_scores"]["relative_volume_continuation_5"][t, 0])


def test_split_and_dollar_volume_scale_preserve_return_and_activity_features():
    market, options = inputs()
    original = build_features(market, **options)
    nominal_shares = options["dollar_volume"] / market["close"]
    factors = np.where(np.arange(310)[:, None] < 260, 7.0, 1.0)
    market["close"] *= factors
    market["atr"] *= factors
    nominal_shares /= factors
    options["dollar_volume"] = market["close"] * nominal_shares
    options["turnover"] = (
        pd.DataFrame(options["dollar_volume"]).rolling(20).mean().to_numpy(copy=True)
    )
    reconstructed = build_features(market, **options)
    np.testing.assert_allclose(reconstructed["X"], original["X"], equal_nan=True, atol=1e-7)
    np.testing.assert_allclose(reconstructed["labels"], original["labels"], equal_nan=True)
    np.testing.assert_array_equal(reconstructed["eligible"], original["eligible"])
    for name in RULE_NAMES:
        np.testing.assert_allclose(
            reconstructed["rule_scores"][name], original["rule_scores"][name], equal_nan=True
        )
    options["dollar_volume"] *= 5
    options["turnover"] *= 5
    scaled = build_features(market, **options)
    np.testing.assert_allclose(
        feature(scaled, "dollar_activity_5_prior_20"),
        feature(original, "dollar_activity_5_prior_20"),
        equal_nan=True,
    )
    np.testing.assert_allclose(
        feature(scaled, "log_dollar_turnover_20")[200:],
        feature(original, "log_dollar_turnover_20")[200:] + np.log(5),
        rtol=1e-6,
    )


def test_benchmark_gap_is_distinct_from_no_candidates_and_recovers_after_22_closes():
    market, options = inputs(n=500)
    baseline = build_features(market, **options)
    market["adjusted"][250, 3] = np.nan
    result = build_features(market, **options)
    np.testing.assert_array_equal(result["eligible"][:, :3], baseline["eligible"][:, :3])
    assert result["benchmark_known"][249]
    assert not result["benchmark_known"][250:272].any()
    assert result["benchmark_known"][272]
    for scores in result["rule_scores"].values():
        assert np.isnan(scores[250:272]).all()
    assert np.isnan(feature(result, "benchmark_above_ma_200")[272]).all()
    # Recovery of the rules does not wait for the optional 200-session feature.
    assert any(np.isfinite(scores[272:300, :3]).any() for scores in result["rule_scores"].values())
    market["benchmark"] = None
    missing = build_features(market, **options)
    assert not missing["benchmark_known"].any()
    assert all(np.isnan(scores).all() for scores in missing["rule_scores"].values())


def test_stock_gap_liquidity_and_zero_rule_denominators_are_not_silently_imputed():
    market, options = inputs(n=500)
    market["adjusted"][250, 0] = np.nan
    options["turnover"][260, 1] = 4_999_999
    market["atr"][261, 1] = 0
    # Identical stock and benchmark returns give exactly zero residual sigma.
    market["adjusted"][:, 2] = market["adjusted"][:, 3]
    options["dollar_volume"][236:256, 1] = 0
    result = build_features(market, **options)
    assert not result["eligible"][250:451, 0].any()
    assert result["eligible"][451, 0]
    assert not result["eligible"][260, 1]
    assert not result["eligible"][261, 1]
    assert result["eligible"][262, 1]
    assert all(np.isnan(scores[260, 1]) for scores in result["rule_scores"].values())
    assert all(np.isnan(scores[:, 2]).all() for scores in result["rule_scores"].values())


def test_cross_section_rank_uses_only_same_day_eligible_stocks_and_average_ties():
    market, options = inputs()
    market["adjusted"][:, 1] = market["adjusted"][:, 0]
    options["turnover"][260, 2] = 0
    result = build_features(market, **options)
    ranks = feature(result, "cross_section_relative_rank_5")
    np.testing.assert_allclose(ranks[260, :2], [0.75, 0.75])
    assert np.isnan(ranks[260, 2:]).all()


def test_zero_prior_activity_denominator_rejects_rules_without_changing_shared_eligibility():
    market, options = inputs()
    t = 260
    options["dollar_volume"][t - 24 : t - 4, 0] = 0
    options["dollar_volume"][t - 4 : t + 1, 0] = 30_000_000
    options["turnover"] = pd.DataFrame(options["dollar_volume"]).rolling(20).mean().to_numpy()
    result = build_features(market, **options)
    assert options["turnover"][t, 0] == 7_500_000
    assert result["eligible"][t, 0]
    assert np.isnan(feature(result, "dollar_activity_5_prior_20")[t, 0])
    assert all(np.isnan(scores[t, 0]) for scores in result["rule_scores"].values())


def test_chunking_does_not_change_any_value(monkeypatch):
    market, options = inputs()
    expected = build_features(market, **options)
    monkeypatch.setattr("frontier.ensemble_features.CHUNK_SIZE", 1)
    actual = build_features(market, **options)
    for key in ("X", "eligible", "benchmark_known", "labels", "label_end"):
        np.testing.assert_allclose(actual[key], expected[key], equal_nan=True)
    for name in RULE_NAMES:
        np.testing.assert_allclose(
            actual["rule_scores"][name], expected["rule_scores"][name], equal_nan=True
        )
