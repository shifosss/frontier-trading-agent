import json

import numpy as np
import pytest

from frontier import ensemble_models as models


@pytest.fixture(scope="module")
def sample():
    rng = np.random.default_rng(813)
    features = rng.normal(size=(656, 5))
    features[:, 3] = np.nan
    features[::7, 4] = np.nan
    targets = np.column_stack(
        (
            0.02 * features[:, 0],
            -0.03 * features[:, 1],
            0.01 * (features[:, 2] ** 2 - 1),
            0.005 + 0.01 * np.abs(features[:, 0]),
            0.01 + 0.02 * np.abs(features[:, 1]),
            0.015 + 0.03 * np.abs(features[:, 2]),
        )
    )
    return features[:512], targets[:512], features[512:640], targets[512:640], features[640:]


@pytest.fixture(scope="module")
def fitted(sample):
    return models.fit_predict_heads(*sample)


def test_real_shared_hidden_six_output_models_and_signed_returns(fitted):
    assert tuple(fitted["predictions"]) == models.MODEL_NAMES
    for prediction in fitted["predictions"].values():
        assert prediction.shape == (16, 6)
        assert np.isfinite(prediction).all()
        assert (prediction[:, 3:] >= 0).all()
    assert (fitted["predictions"]["ridge"][:, 0] < 0).any()
    assert (fitted["predictions"]["ridge"][:, 0] > 0).any()
    assert not np.allclose(
        fitted["predictions"]["ridge"][:, 0], fitted["predictions"]["ridge"][:, 1]
    )
    mlp = fitted["model_audit"]["multi_head_mlp"]
    assert mlp["weight_shapes"] == [[7, 32], [32, 16], [16, 6]]
    assert mlp["iterations"] <= 60
    assert mlp["outputs"] == 6
    boosted = fitted["model_audit"]["hist_gradient_boosting"]
    assert boosted["independent_target_estimators"] == 6
    assert boosted["iterations_per_target"] == [60] * 6
    assert fitted["config"]["models"]["hist_gradient_boosting"]["early_stopping"] is False
    assert fitted["config"]["boosting_wrapper"]["n_jobs"] == 1
    assert fitted["config"]["models"]["multi_head_mlp"]["early_stopping"] is False
    json.dumps(
        {key: value for key, value in fitted.items() if key != "predictions"}, allow_nan=False
    )


def test_calibration_weights_and_paired_downside_are_reproducible(fitted):
    predictions = fitted["predictions"]
    stacked = np.stack([predictions[name] for name in models.BASE_MODEL_NAMES])
    np.testing.assert_allclose(predictions["equal_ensemble"], stacked.mean(axis=0))
    calibration = fitted["calibration"]
    assert calibration["row_count"] == 128
    assert calibration["metric"] == "pooled_per_row_mse"
    assert any(not row["equal_weight_fallback"] for row in calibration["horizons"].values())
    for head, horizon in enumerate((1, 3, 5)):
        row = calibration["horizons"][str(horizon)]
        improvements = np.array(
            [
                max(calibration["baseline_mse"][head] - calibration["model_mse"][name][head], 0)
                for name in models.BASE_MODEL_NAMES
            ]
        )
        expected_weights = (
            improvements / improvements.sum()
            if improvements.sum()
            else np.full(len(models.BASE_MODEL_NAMES), 1 / len(models.BASE_MODEL_NAMES))
        )
        np.testing.assert_allclose(list(row["weights"].values()), expected_weights)
        for target_head in (head, head + 3):
            np.testing.assert_allclose(
                predictions["calibrated_ensemble"][:, target_head],
                np.einsum("m,mn->n", expected_weights, stacked[:, :, target_head]),
            )


def test_imputation_and_both_scalers_use_training_only(sample, fitted):
    train, targets, _, _, _ = sample
    audit = fitted["preprocessing"]
    assert audit["fitted_rows"] == len(train)
    assert audit["missing_indicator_features"] == [3, 4]
    medians = np.array([np.nanmedian(train[:, j]) if j != 3 else 0 for j in range(5)])
    imputed = np.where(np.isnan(train), medians, train)
    imputed = np.column_stack((imputed, np.isnan(train[:, [3, 4]]).astype(float)))
    np.testing.assert_allclose(audit["feature_medians"], medians)
    np.testing.assert_allclose(audit["feature_mean"], imputed.mean(axis=0))
    scales = imputed.std(axis=0)
    scales[scales == 0] = 1
    np.testing.assert_allclose(audit["feature_scale"], scales)
    np.testing.assert_allclose(audit["target_mean"], targets.mean(axis=0))
    np.testing.assert_allclose(audit["target_scale"], targets.std(axis=0))


def assert_calibration_close(left, right):
    for key in ("row_count", "metric", "interpretation"):
        assert left[key] == right[key]
    for key in ("training_target_mean", "baseline_mse"):
        np.testing.assert_allclose(left[key], right[key], rtol=1e-12, atol=1e-15)
    for name in models.BASE_MODEL_NAMES:
        np.testing.assert_allclose(
            left["model_mse"][name], right["model_mse"][name], rtol=1e-12, atol=1e-15
        )
    for horizon in ("1", "3", "5"):
        a, b = left["horizons"][horizon], right["horizons"][horizon]
        assert a["equal_weight_fallback"] == b["equal_weight_fallback"]
        for key in ("weights", "positive_mse_improvement"):
            np.testing.assert_allclose(
                list(a[key].values()), list(b[key].values()), rtol=1e-12, atol=1e-15
            )


def test_future_features_cannot_change_fit_calibration_or_existing_prediction(sample, fitted):
    train, targets, cal, cal_targets, test = sample
    changed_test = np.vstack((test, np.full((1, test.shape[1]), 1_000_000.0)))
    changed = models.fit_predict_heads(train, targets, cal, cal_targets, changed_test)
    assert changed["preprocessing"] == fitted["preprocessing"]
    assert_calibration_close(changed["calibration"], fitted["calibration"])
    for name in models.MODEL_NAMES:
        np.testing.assert_allclose(
            changed["predictions"][name][:-1], fitted["predictions"][name], rtol=1e-12, atol=1e-12
        )


def test_calibration_labels_only_change_weights_and_equal_fallback_is_declared(sample, fitted):
    train, targets, cal, _, test = sample
    baseline_targets = np.tile(targets.mean(axis=0), (len(cal), 1))
    changed = models.fit_predict_heads(train, targets, cal, baseline_targets, test)
    assert changed["preprocessing"] == fitted["preprocessing"]
    for name in models.BASE_MODEL_NAMES:
        np.testing.assert_allclose(changed["predictions"][name], fitted["predictions"][name])
    for row in changed["calibration"]["horizons"].values():
        assert row["equal_weight_fallback"] is True
        np.testing.assert_allclose(
            list(row["weights"].values()),
            np.full(len(models.BASE_MODEL_NAMES), 1 / len(models.BASE_MODEL_NAMES)),
        )
    np.testing.assert_allclose(
        changed["predictions"]["calibrated_ensemble"], changed["predictions"]["equal_ensemble"]
    )
    assert "not significance or qualification" in changed["calibration"]["interpretation"]


def test_batched_float32_predictions_match_and_empty_test_is_allowed(sample, monkeypatch):
    train, targets, cal, cal_targets, test = sample
    arrays = (train.astype(np.float32), targets, cal.astype(np.float32), cal_targets)
    regular = models.fit_predict_heads(*arrays, test.astype(np.float32))
    monkeypatch.setattr(models, "PREDICTION_BATCH_SIZE", 3)
    batched = models.fit_predict_heads(*arrays, test.astype(np.float32))
    for name in models.MODEL_NAMES:
        np.testing.assert_allclose(
            regular["predictions"][name], batched["predictions"][name], rtol=1e-6, atol=1e-8
        )
    empty = models.fit_predict_heads(*arrays, np.empty((0, train.shape[1])))
    assert all(value.shape == (0, 6) for value in empty["predictions"].values())
    assert_calibration_close(empty["calibration"], regular["calibration"])


@pytest.mark.parametrize(
    "which,replacement,match",
    [
        (0, np.ones(5), "two-dimensional"),
        (0, np.empty((0, 5)), "must contain rows"),
        (2, np.empty((0, 5)), "must contain rows"),
        (4, np.ones((2, 4)), "same column count"),
        (4, np.full((2, 5), np.inf), "infinite"),
        (1, np.zeros((512, 5)), "six target heads"),
        (3, np.full((128, 6), np.nan), "finite"),
        (3, np.full((128, 6), -1.0), "nonnegative"),
    ],
)
def test_invalid_inputs_fail_explicitly(sample, which, replacement, match):
    args = list(sample)
    args[which] = replacement
    with pytest.raises(ValueError, match=match):
        models.fit_predict_heads(*args)


def test_individual_model_failure_is_not_silently_removed(sample, monkeypatch):
    def failed_fit(self, X, y):
        raise RuntimeError("deliberate tree failure")

    monkeypatch.setattr(models.ExtraTreesRegressor, "fit", failed_fit)
    with pytest.raises(RuntimeError, match="deliberate tree failure"):
        models.fit_predict_heads(*sample)


def test_convergence_warning_is_preserved_with_model_and_category(sample, monkeypatch):
    monkeypatch.setitem(models.MODEL_CONFIG["multi_head_mlp"], "max_iter", 1)
    result = models.fit_predict_heads(*sample)
    assert result["model_audit"]["multi_head_mlp"]["convergence_warning"] is True
    assert any(
        item["model"] == "multi_head_mlp" and item["category"] == "ConvergenceWarning"
        for item in result["warnings"]
    )
    assert result["config"]["models"]["multi_head_mlp"]["max_iter"] == 1


def test_only_negative_downside_predictions_are_clipped():
    class Predictions:
        def predict(self, features):
            return np.tile([-2.0, -0.01, 3.0, -0.5, 0.1, 2.0], (len(features), 1))

    prediction = models._prediction(Predictions(), np.ones((1, 2)))
    np.testing.assert_array_equal(prediction, [[-2.0, -0.01, 3.0, 0.0, 0.1, 2.0]])


def test_separate_fit_predict_preserves_legacy_results_and_empty_rows(sample, fitted):
    bundle = models.fit_heads(*sample[:4])
    predictions = models.predict_heads(bundle, sample[4])
    assert bundle.audit.keys() == fitted.keys() - {"predictions"}
    assert_calibration_close(bundle.audit["calibration"], fitted["calibration"])
    for name in models.MODEL_NAMES:
        np.testing.assert_allclose(predictions[name], fitted["predictions"][name], atol=1e-15)
    assert all(x.shape == (0, 6) for x in models.predict_heads(bundle, sample[4][:0]).values())
    with pytest.raises(ValueError, match="same column count"):
        models.predict_heads(bundle, np.zeros((2, 4)))


def test_repeated_fits_calibration_and_predictions_are_exact(sample):
    first = models.fit_heads(*sample[:4])
    second = models.fit_heads(*sample[:4])
    assert first.audit == second.audit
    np.testing.assert_array_equal(first.weights, second.weights)
    assert first.models["extra_trees"].n_jobs == 1
    assert first.audit["model_audit"]["extra_trees"]["fit_n_jobs"] == 2
    assert first.audit["model_audit"]["extra_trees"]["predict_n_jobs"] == 1
    assert first.audit["config"]["extra_trees_prediction_n_jobs"] == 1
    expected = models.predict_heads(first, sample[4])
    for bundle in (first, first, second):
        actual = models.predict_heads(bundle, sample[4])
        for name in models.MODEL_NAMES:
            np.testing.assert_array_equal(expected[name], actual[name])
