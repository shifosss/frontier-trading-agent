from copy import deepcopy

import numpy as np
import pytest

from frontier import conditional_models as models
from frontier.daily_policy import plan_entries


def test_sample_draw_precedes_missing_labels_and_purges_all_heads(monkeypatch):
    n, m = 12, 10
    market = {
        "sessions": [f"day-{i}" for i in range(n)],
        "symbols": [f"S{i}" for i in range(m)],
        "close": np.full((n, m), 20.0),
        "atr": np.full((n, m), 0.5),
    }
    features = {
        "labels": np.zeros((n, m, 6)),
        "label_end": np.arange(n)[:, None] + np.array([2, 4, 6]),
    }
    context = {"eligible": np.ones((n, m), dtype=bool), "feature_names": ["x"]}
    monkeypatch.setattr(
        models,
        "gather_rows",
        lambda features, context, rows, columns: columns[:, None].astype(np.float32),
    )
    original = models.sample_conditional_rows(market, features, context, 0, 10, 10, limit=4)
    first = original["audit"]["selected"][0]
    features["labels"][first[0], first[1], 0] = np.nan
    changed = models.sample_conditional_rows(market, features, context, 0, 10, 10, limit=4)
    assert [r[:3] for r in original["audit"]["selected"]] == [
        r[:3] for r in changed["audit"]["selected"]
    ]
    assert changed["audit"]["selected_count"] == 40
    assert len(changed["rows"]) == len(original["rows"]) - 1 == 15
    assert changed["audit"]["selected"][0][3] == ["nonfinite_label"]
    assert (changed["label_end"] < 10).all()
    assert set(changed["rows"]) == {0, 1, 2, 3}
    assert len(set(zip(changed["rows"], changed["columns"], strict=True))) == 15
    # A date has the same draw when reached through a different sample window.
    suffix = models.sample_conditional_rows(market, features, context, 2, 4, 10, limit=4)
    assert [r[:3] for r in suffix["audit"]["selected"]] == [
        r[:3] for r in original["audit"]["selected"] if 2 <= r[0] < 4
    ]


def test_reference_quantity_matches_independent_existing_planner():
    prices = np.array([2.0, 19.5, 120.0, 500.0])
    atrs = np.array([0.1, 0.8, 3.0, 5.0])
    notionals = models.reference_notionals(prices, atrs)
    for i in range(len(prices)):
        plan = plan_entries(
            symbols=["fixture"],
            ranking=[0],
            prices=prices[i : i + 1],
            atrs=atrs[i : i + 1],
            nav=2000,
            available_cash=2000,
            cost_bps=40,
        )
        quantity = plan["orders"][0]["quantity"] if plan["orders"] else 0
        assert notionals[i] == quantity * prices[i]
    assert notionals[-1] == 0


def test_utility_loss_weights_dates_not_row_counts_and_uses_all_horizons():
    target = np.zeros((4, 6))
    prediction = np.zeros((4, 6))
    prediction[0, :3] = [3, 6, 9]
    result = models.utility_loss(target, prediction, [2, 2, 2, 2], [10, 11, 11, 11])
    # Date10: mean([36,144,324])=168; date11:0. Row averaging would give42.
    assert result["value"] == 84
    assert result["by_horizon"] == [18, 72, 162]
    assert result["dates"][1]["rows"] == 3


def sample(rows):
    rows = np.asarray(rows, dtype=np.int64)
    X = np.column_stack((np.sin(rows / 31), rows / 1000, np.full(len(rows), np.nan)))
    y = np.column_stack(
        (
            0.02 * X[:, 0],
            -0.01 * X[:, 0],
            0.03 * X[:, 1],
            0.005 + 0.003 * (X[:, 0] + 1),
            0.01 + 0.006 * (X[:, 0] + 1),
            0.02 + 0.009 * (X[:, 0] + 1),
        )
    )
    return {
        "rows": rows,
        "columns": np.zeros(len(rows), dtype=np.int64),
        "X": X,
        "y": y,
        "reference_notional": np.full(len(rows), 100.0),
        "label_end": rows + 6,
        "audit": {
            "feature_names": ["cyclical", "trend", "missing"],
            "selected": [[int(i), 0, int(i + 6), []] for i in rows],
            "selected_count": len(rows),
            "retained_count": len(rows),
        },
    }


@pytest.fixture(scope="module")
def fitted(tmp_path_factory):
    fit, cal = sample(np.arange(498)), sample(np.arange(504, 750))
    path = tmp_path_factory.mktemp("conditional") / "block"
    events = []
    bundle = models.fit_conditional_block(
        fit,
        cal,
        0,
        504,
        756,
        path,
        metadata={"source": "synthetic_frozen_fixture"},
        progress=events.append,
    )
    assert [e["phase"] for e in events] == ["inner_fit"] * 6 + [
        "final_fit",
        "calibration",
        "saving_model",
    ]
    return fit, cal, path, bundle


def test_real_nested_fits_have_strict_train_validation_and_outer_purges(fitted):
    fit, cal, path, bundle = fitted
    assert bundle.available
    assert bundle.family in models.FAMILIES
    assert bundle.audit["status"] == "complete"
    for prefix, fold in zip(models.INNER_PREFIXES, bundle.audit["inner_folds"], strict=True):
        assert fold["fit_rows"] == prefix - 6
        assert fold["validation_rows"] == 78
        assert fold["fit_max_label_end"] < fold["validation_start"]
        assert fold["validation_max_label_end"] < fold["validation_end_exclusive"]
        for family in models.FAMILIES:
            record = fold["models"][family]
            assert record["status"] == "complete"
            assert record["fitted_rows"] == prefix - 6
            assert len(record["loss"]["dates"]) == 78
            expected = np.median(fit["X"][: prefix - 6, :2], axis=0)
            np.testing.assert_array_equal(record["preprocessing"]["feature_medians"][:2], expected)
    for family in models.FAMILIES:
        row = bundle.audit["family_selection"][family]
        assert row["eligible"]
        assert row["completed_folds"] == 3
        assert row["validation_dates"] == 234
        dates = [
            day
            for fold in bundle.audit["inner_folds"]
            for day in fold["models"][family]["loss"]["dates"]
        ]
        assert row["mean_loss"] == np.mean([d["loss_by_horizon"] for d in dates])
    assert bundle.audit["attempt"]["fallback_policy"] == "abstain"
    assert bundle.audit["attempt"]["arrays"]["fit"]["X"]["shape"] == [498, 3]
    assert bundle.audit["attempt"]["metadata"]["source"] == "synthetic_frozen_fixture"


def test_calibration_bias_and_artifact_predictions_are_exact(fitted):
    fit, cal, path, bundle = fitted
    forecast = models.predict_conditional(bundle, cal["X"])
    np.testing.assert_array_equal(bundle.bias, np.mean(cal["y"] - forecast["raw"], axis=0))
    expected = forecast["raw"] + bundle.bias
    expected[:, 3:] = np.maximum(0, expected[:, 3:])
    np.testing.assert_array_equal(forecast["corrected"], expected)
    saved = np.load(path / "calibration-predictions.npz")
    for key in ("raw", "corrected"):
        np.testing.assert_array_equal(saved[key], forecast[key])
    np.testing.assert_array_equal(saved["rows"], cal["rows"])
    np.testing.assert_array_equal(saved["targets"], cal["y"])
    loaded, manifest = models.load_conditional_block(path)
    assert manifest["reload_check"]["exact_equal"]
    assert manifest["reload_check"]["rows"] == 246
    for key, value in models.predict_conditional(loaded, cal["X"]).items():
        np.testing.assert_array_equal(value, forecast[key])


def test_calibration_changes_cannot_choose_family_or_fit_preprocessing(fitted, tmp_path):
    fit, cal, _, bundle = fitted
    changed_cal = deepcopy(cal)
    changed_cal["X"][:, :2] += 1_000_000
    changed_cal["y"][:, :3] += 0.3
    changed = models.fit_conditional_block(fit, changed_cal, 0, 504, 756, tmp_path / "changed")
    assert changed.family == bundle.family
    assert changed.audit["family_selection"] == bundle.audit["family_selection"]
    assert models._preprocessing(changed.model) == models._preprocessing(bundle.model)
    probe = fit["X"][:10]
    np.testing.assert_array_equal(
        models.predict_conditional(changed, probe)["raw"],
        models.predict_conditional(bundle, probe)["raw"],
    )
    assert not np.array_equal(changed.bias, bundle.bias)


def test_prediction_empty_and_future_rows_do_not_change_existing_forecasts(fitted):
    _, cal, _, bundle = fitted
    before = models.predict_conditional(bundle, cal["X"][:2])
    future = np.vstack((cal["X"][:2], [[1e6, -1e6, np.nan]]))
    after = models.predict_conditional(bundle, future)
    for name in ("raw", "corrected"):
        np.testing.assert_array_equal(before[name], after[name][:2])
        assert models.predict_conditional(bundle, future[:0])[name].shape == (0, 6)
    with pytest.raises(ValueError, match="feature order"):
        models.predict_conditional(bundle, np.zeros((2, 4)))


def test_exact_inner_tie_selects_ridge_and_final_failure_abstains(monkeypatch, tmp_path):
    original = models._fit_family
    final_attempts = []

    def fit_family(family, X, y, seed):
        if len(X) == 498:
            final_attempts.append(family)
            raise RuntimeError("declared final fit failure")
        return original(family, X, y, seed)

    monkeypatch.setattr(models, "_fit_family", fit_family)
    monkeypatch.setattr(models, "_family_prediction", lambda model, X: np.zeros((len(X), 6)))
    bundle = models.fit_conditional_block(
        sample(np.arange(498)),
        sample(np.arange(504, 750)),
        0,
        504,
        756,
        tmp_path / "failed-final",
    )
    assert bundle.audit["selected_family"] == "ridge"
    assert final_attempts == ["ridge"]
    assert not bundle.available
    assert bundle.audit["final_fits"][0]["error"] == "declared final fit failure"
    assert np.isnan(models.predict_conditional(bundle, np.zeros((2, 3)))["corrected"]).all()
    loaded, manifest = models.load_conditional_block(tmp_path / "failed-final")
    assert not loaded.available
    assert manifest["status"] == "unavailable"


def test_failed_inner_family_is_retained_and_cannot_be_selected(monkeypatch, tmp_path):
    original = models._fit_family

    def fit_family(family, X, y, seed):
        if family == "hist_gradient_boosting":
            raise RuntimeError("inner model failure")
        return original(family, X, y, seed)

    monkeypatch.setattr(models, "_fit_family", fit_family)
    bundle = models.fit_conditional_block(
        sample(np.arange(498)),
        sample(np.arange(504, 750)),
        0,
        504,
        756,
        tmp_path / "failed-inner",
    )
    assert bundle.family == "ridge"
    assert not bundle.audit["family_selection"]["hist_gradient_boosting"]["eligible"]
    for fold in bundle.audit["inner_folds"]:
        assert fold["models"]["hist_gradient_boosting"]["status"] == "failed"
        assert fold["models"]["hist_gradient_boosting"]["error"] == "inner model failure"


def test_window_boundary_violation_is_rejected(tmp_path):
    fit, cal = sample(np.arange(498)), sample(np.arange(504, 750))
    fit["label_end"][-1] = 504
    with pytest.raises(ValueError, match="purged window"):
        models.fit_conditional_block(fit, cal, 0, 504, 756, tmp_path / "leaked")
    with pytest.raises(ValueError, match="504"):
        models.fit_conditional_block(fit, cal, 0, 503, 756, tmp_path / "wrong-window")


def test_artifact_tampering_rejected_before_deserialization(fitted, tmp_path, monkeypatch):
    _, _, source, _ = fitted
    copied = tmp_path / "copied"
    copied.mkdir()
    for path in source.iterdir():
        (copied / path.name).write_bytes(path.read_bytes())
    (copied / "model.joblib").write_bytes(b"changed")
    monkeypatch.setattr(models.joblib, "load", lambda *_: pytest.fail("must not deserialize"))
    with pytest.raises(ValueError, match="integrity failed"):
        models.load_conditional_block(copied)


def test_existing_artifacts_are_never_overwritten(fitted):
    fit, cal, path, _ = fitted
    before = (path / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        models.fit_conditional_block(fit, cal, 0, 504, 756, path)
    assert (path / "manifest.json").read_bytes() == before
