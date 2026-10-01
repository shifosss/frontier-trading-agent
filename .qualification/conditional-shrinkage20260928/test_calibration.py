"""Focused checks for the declared calibration-only return attenuation."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location(
    "shrinkage_calibration", Path(__file__).with_name("calibration.py")
)
calibration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calibration)


def six_heads(returns):
    returns = np.asarray(returns, dtype=np.float64)
    if returns.ndim == 1:
        returns = np.repeat(returns[:, None], 3, axis=1)
    return np.column_stack((returns, np.full_like(returns, 0.03)))


@pytest.mark.parametrize(
    "raw_slope, expected", [(-2.0, 0.0), (0.0, 0.0), (0.4, 0.4), (1.0, 1.0), (3.0, 1.0)]
)
def test_negative_flat_attenuated_and_amplified_relationships(raw_slope, expected):
    raw = six_heads([-0.03, -0.01, 0.01, 0.03])
    targets = six_heads(0.007 + raw_slope * raw[:, :3])
    parameters = calibration.fit_return_shrinkage(raw, targets)
    for head in parameters["returns"]:
        assert head["unconstrained_slope"] == pytest.approx(raw_slope)
        assert head["slope"] == pytest.approx(expected)
        assert head["intercept"] == pytest.approx(0.007)
    result = calibration.apply_return_shrinkage(parameters, raw, raw.copy())
    np.testing.assert_allclose(result[:, :3], 0.007 + expected * raw[:, :3])


def test_zero_variance_uses_calibration_mean_without_epsilon_cutoff():
    raw = six_heads([0.02, 0.02, 0.02, 0.02])
    targets = six_heads([-0.03, 0.01, 0.03, 0.07])
    parameters = calibration.fit_return_shrinkage(raw, targets)
    assert all(head["zero_variance"] for head in parameters["returns"])
    result = calibration.apply_return_shrinkage(parameters, six_heads([0.9]), six_heads([0.8]))
    np.testing.assert_allclose(result[0, :3], 0.02)

    tiny = six_heads(np.array([-3, -1, 1, 3]) * 1e-12)
    fitted = calibration.fit_return_shrinkage(tiny, six_heads(tiny[:, :3] * 0.5))
    assert all(not head["zero_variance"] for head in fitted["returns"])
    assert all(head["slope"] == pytest.approx(0.5) for head in fitted["returns"])

    constant_decimal = six_heads(np.full(23616, 0.1))
    fitted = calibration.fit_return_shrinkage(constant_decimal, constant_decimal)
    assert all(head["zero_variance"] for head in fitted["returns"])
    assert all(head["variance_raw"] == 0.0 for head in fitted["returns"])


def test_intercept_matches_calibration_mean_and_heads_are_independent():
    x = np.array([[1, 5, 2], [2, 3, 4], [3, 1, 6]], dtype=np.float64) / 100
    y = x * np.array([0.2, -0.5, 2.0]) + np.array([0.003, 0.005, -0.01])
    raw, targets = six_heads(x), six_heads(y)
    parameters = calibration.fit_return_shrinkage(raw, targets)
    result = calibration.apply_return_shrinkage(parameters, raw, raw)
    np.testing.assert_allclose(result[:, :3].mean(axis=0), y.mean(axis=0))
    assert [head["slope"] for head in parameters["returns"]] == pytest.approx([0.2, 0.0, 1.0])


def test_slope_one_matches_original_mean_bias_with_rounding_tolerance():
    raw = six_heads([-0.07, -0.02, 0.01, 0.09])
    targets = six_heads(raw[:, :3] + 0.005)
    parameters = calibration.fit_return_shrinkage(raw, targets)
    original = raw + np.mean(targets - raw, axis=0)
    result = calibration.apply_return_shrinkage(parameters, raw, original)
    np.testing.assert_allclose(result[:, :3], original[:, :3], rtol=1e-14, atol=1e-16)


def test_downside_bytes_inputs_and_missing_forecast_rows_are_preserved():
    parameters = calibration.fit_return_shrinkage(six_heads([-0.1, 0.1]), six_heads([-0.03, 0.03]))
    raw = six_heads([0.2, np.nan, -0.1])
    original = six_heads([0.1, np.nan, -0.2])
    original[:, 3:] = np.array([[0.0, -0.0, 0.04], [np.nan, np.nan, np.nan], [0.02, 0.03, 0.01]])
    raw_before, original_before = raw.tobytes(), original.tobytes()
    result = calibration.apply_return_shrinkage(parameters, raw, original)
    assert result.dtype == np.float64
    assert result[:, 3:].tobytes() == original[:, 3:].tobytes()
    assert np.isnan(result[1, :3]).all()
    assert raw.tobytes() == raw_before
    assert original.tobytes() == original_before


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_invalid_calibration_fails_without_resampling(bad_value):
    raw, targets = six_heads([-0.1, 0.1]), six_heads([-0.02, 0.02])
    raw[0, 0] = bad_value
    with pytest.raises(ValueError, match="finite"):
        calibration.fit_return_shrinkage(raw, targets)
    raw = six_heads([-0.1, 0.1])
    targets[1, 4] = bad_value
    with pytest.raises(ValueError, match="finite"):
        calibration.fit_return_shrinkage(raw, targets)


def test_empty_mismatched_or_wrong_head_calibration_is_rejected():
    for raw, targets in [
        (np.empty((0, 6)), np.empty((0, 6))),
        (np.ones((2, 6)), np.ones((1, 6))),
        (np.ones((2, 3)), np.ones((2, 3))),
    ]:
        with pytest.raises(ValueError):
            calibration.fit_return_shrinkage(raw, targets)


def test_transform_has_no_future_target_input_and_does_not_refit_on_test_distribution():
    raw = six_heads([-0.04, -0.02, 0.02, 0.04])
    targets = six_heads(raw[:, :3] * 0.25 + 0.002)
    parameters = calibration.fit_return_shrinkage(raw, targets, source_identity={"block": 3})
    first = six_heads([0.05])
    expected = calibration.apply_return_shrinkage(parameters, first, first)
    changed_test = np.concatenate((first, six_heads([100, -100, 5])))
    result = calibration.apply_return_shrinkage(parameters, changed_test, changed_test)
    np.testing.assert_array_equal(result[:1], expected)
    assert parameters["source_identity"] == {"block": 3}
    assert parameters == calibration.fit_return_shrinkage(raw, targets, source_identity={"block": 3})
    changed_targets = targets.copy()
    changed_targets[:, 0] += 0.01
    changed = calibration.fit_return_shrinkage(raw, changed_targets)
    assert changed["returns"][0]["intercept"] != parameters["returns"][0]["intercept"]
    assert changed["calibration_arrays"]["targets"]["sha256"] != parameters["calibration_arrays"]["targets"]["sha256"]


def test_transform_rejects_infinite_predictions_and_changed_downside_dtype():
    raw = six_heads([-0.1, 0.1])
    parameters = calibration.fit_return_shrinkage(raw, raw)
    invalid = raw.copy()
    invalid[0, 0] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        calibration.apply_return_shrinkage(parameters, invalid, raw)
    with pytest.raises(ValueError, match="float64"):
        calibration.apply_return_shrinkage(parameters, raw, raw.astype(np.float32))
