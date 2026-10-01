"""Synthetic-only checks; no original filings, prices, network or accounts."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import earnings_models as models

FOLD = {"fit_decision_years": [2017, 2018, 2019], "calibration_decision_year": 2020,
        "test_decision_year": 2021}
CALENDAR = ["2017-01-03", "2018-01-02", "2019-01-02", "2019-01-09", "2019-12-31",
            "2020-01-02", "2020-01-09", "2020-12-31", "2021-01-04", "2021-01-11"]


def fixture(fit_count=256, cal_count=64, fit_issuers=25, cal_issuers=16):
    rng = np.random.default_rng(971)
    rows, labels = [], {}
    for name, count, issuers, day, end, shift in (
        ("fit", fit_count, fit_issuers, "2019-01-02", "2019-01-09", 0),
        ("cal", cal_count, cal_issuers, "2020-01-02", "2020-01-09", 4),
        ("test", 3, 3, "2021-01-04", "2021-01-11", 20),
    ):
        for i in range(count):
            event_id = f"{name}-{i:04d}"
            X = rng.normal(size=5) + shift
            rows.append({"event_id": event_id, "accession": event_id,
                         "cik": str(i % issuers + 1).zfill(10),
                         "decision_timestamp": day + "T09:00:00-05:00",
                         "planned_label_end_session": end,
                         "model_input_status": "qualified", "model_inputs": X.tolist(),
                         "original_source": {"path": f"synthetic/{event_id}", "sha256": "a" * 64}})
            labels[event_id] = {"status": "qualified",
                                "targets": [0.01 + 0.002 * X[0], 0.01 + 0.0005 * abs(X[1])]}
    return rows, labels


class ConstantModel:
    def __init__(self, raw=(0.03, -0.04)):
        self.raw = raw

    def predict(self, X):
        return np.tile(self.raw, (len(X), 1))


class ForbiddenFutureLabels(dict):
    def get(self, key, default=None):
        if key.startswith("test") or key.startswith("purged"):
            raise AssertionError(f"Future/purged label was accessed: {key}")
        return super().get(key, default)


class TwoOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.labels = fixture()
        cls.bundles = models.fit_fold(cls.rows, cls.labels, FOLD, CALENDAR)

    def test_actual_families_have_two_heads_and_exact_presets(self):
        self.assertEqual(set(self.bundles), set(models.FAMILIES))
        for family, bundle in self.bundles.items():
            self.assertTrue(bundle.available, bundle.audit)
            raw = bundle.model.predict(np.asarray([self.rows[0]["model_inputs"]]))
            self.assertEqual(raw.shape, (1, 2))
            self.assertEqual(bundle.audit["samples"]["fit"]["rows"], 256)
            self.assertEqual(bundle.audit["samples"]["fit"]["distinct_ciks"], 25)
            self.assertEqual(bundle.audit["samples"]["calibration"]["rows"], 64)
            self.assertEqual(bundle.audit["samples"]["calibration"]["distinct_ciks"], 16)
            parameters = bundle.model.steps[-1][1].get_params()
            if family == "ridge":
                self.assertEqual(parameters["alpha"], 100)
            else:
                self.assertEqual(parameters["n_jobs"], 1)
                self.assertEqual(parameters["estimator__max_iter"], 60)
                self.assertEqual(parameters["estimator__random_state"], 1729)
                self.assertFalse(parameters["estimator__early_stopping"])

    def test_scaler_and_baseline_use_fitting_rows_only(self):
        bundle = self.bundles["ridge"]
        X = np.asarray([row["model_inputs"] for row in self.rows[:256]])
        targets = np.asarray([self.labels[row["event_id"]]["targets"] for row in self.rows[:256]])
        np.testing.assert_allclose(bundle.audit["preprocessing"]["feature_mean"], X.mean(axis=0))
        np.testing.assert_allclose(bundle.training_mean, targets.mean(axis=0))
        self.assertGreater(abs(np.asarray(self.rows[256]["model_inputs"]).mean() - X.mean()), 1)

    def test_manual_calibration_and_calibration_only_edges(self):
        for bundle in self.bundles.values():
            cal = bundle.audit["calibration"]
            targets = np.asarray(bundle.audit["samples"]["calibration"]["targets"])
            raw = np.asarray(cal["raw"])
            uncal = np.column_stack((raw[:, 0], np.maximum(0, raw[:, 1])))
            bias = (targets - uncal).mean(axis=0)
            corrected = uncal + bias
            corrected[:, 1] = np.maximum(0, corrected[:, 1])
            np.testing.assert_array_equal(cal["uncalibrated"], uncal)
            np.testing.assert_array_equal(bundle.bias, bias)
            np.testing.assert_array_equal(cal["corrected"], corrected)
            for layer, values in (("raw", raw), ("corrected", corrected)):
                for head in range(2):
                    cuts = np.quantile(values[:, head], [.2, .4, .6, .8])
                    expected = sorted(set(float(c) for c in cuts
                                          if values[:, head].min() < c < values[:, head].max()))
                    self.assertEqual(bundle.quantile_edges[layer][head], expected)

    def test_negative_raw_downside_survives_and_is_clipped_before_bias(self):
        with patch.object(models.shared, "_fit_family", return_value=ConstantModel()), \
             patch.object(models.shared, "_preprocessing", return_value={}):
            bundle = models.fit_family_fold("ridge", self.rows, self.labels, FOLD, CALENDAR)
        self.assertTrue(bundle.available)
        raw = np.asarray(bundle.audit["calibration"]["raw"])
        np.testing.assert_array_equal(raw[:, 1], -.04)
        np.testing.assert_array_equal(np.asarray(bundle.audit["calibration"]["uncalibrated"])[:, 1], 0)
        target_mean = np.asarray(bundle.audit["samples"]["calibration"]["targets"]).mean(axis=0)
        self.assertAlmostEqual(bundle.bias[1], target_mean[1])
        self.assertEqual(bundle.quantile_edges, {"raw": [[], []], "corrected": [[], []]})

    def test_future_labels_never_accessed_and_missing_test_labels_do_not_filter(self):
        guarded = ForbiddenFutureLabels(self.labels)
        bundle = models.fit_family_fold("ridge", self.rows, guarded, FOLD, CALENDAR)
        test_rows = [r for r in self.rows if r["event_id"].startswith("test")]
        before = models.predict_events(bundle, test_rows)
        for row in test_rows:
            guarded[row["event_id"]] = {"status": "unavailable", "reasons": ["No future price"]}
        second = models.fit_family_fold("ridge", self.rows, guarded, FOLD, CALENDAR)
        after = models.predict_events(second, test_rows)
        self.assertEqual(before["forecasts"], after["forecasts"])
        self.assertEqual(len(before["forecasts"]), 3)
        self.assertTrue(all(r["status"] == "predicted" for r in before["forecasts"]))
        self.assertEqual(bundle.audit["samples"]["test"]["event_ids"],
                         [r["event_id"] for r in test_rows])

    def test_purge_uses_actual_first_sessions_and_decision_year(self):
        rows, labels = fixture()
        for name, decision, end in (("purged-fit", "2019-12-31", "2020-01-02"),
                                    ("purged-cal", "2020-12-31", "2021-01-04")):
            row = deepcopy(rows[0])
            row.update(event_id=name, accession=name, decision_timestamp=decision + "T09:00:00-05:00",
                       planned_label_end_session=end)
            rows.append(row)
        # Earlier filing date must not move a 2020 decision into fitting.
        rows[256]["filingDate"] = "2019-12-31"
        bundle = models.fit_family_fold("ridge", rows, ForbiddenFutureLabels(labels), FOLD, CALENDAR)
        dispositions = {r["event_id"]: r for r in bundle.audit["row_dispositions"]}
        self.assertEqual(dispositions["purged-fit"]["status"], "purged")
        self.assertEqual(dispositions["purged-cal"]["status"], "purged")
        self.assertEqual(dispositions["cal-0000"]["partition"], "calibration")
        self.assertEqual(bundle.audit["boundaries"],
                         {"fit": "2020-01-02", "calibration": "2021-01-04"})
        self.assertTrue(bundle.available)

    def test_each_fixed_row_and_issuer_gate_abstains_without_fit(self):
        for kwargs in ({"fit_count": 255}, {"cal_count": 63},
                       {"fit_issuers": 24}, {"cal_issuers": 15}):
            rows, labels = fixture(**kwargs)
            with patch.object(models.shared, "_fit_family") as fitter:
                bundle = models.fit_family_fold("ridge", rows, labels, FOLD, CALENDAR)
            fitter.assert_not_called()
            self.assertEqual(bundle.audit["status"], "insufficient_sample")
            self.assertFalse(bundle.available)
            output = models.predict_events(bundle, rows[-3:])
            self.assertTrue(all(r["status"] == "unavailable" for r in output["forecasts"]))

    def test_invalid_input_or_training_label_retained_and_affects_gate(self):
        for which in ("input", "label"):
            rows, labels = fixture()
            if which == "input":
                rows[0]["model_input_status"] = "unavailable"
                rows[0]["model_input_reasons"] = ["Missing original CFO"]
            else:
                labels[rows[0]["event_id"]] = {"status": "unavailable", "reasons": ["Missing exit close"]}
            bundle = models.fit_family_fold("ridge", rows, labels, FOLD, CALENDAR)
            self.assertEqual(bundle.audit["status"], "insufficient_sample")
            self.assertEqual(len(bundle.audit["row_dispositions"]), len(rows))
            record = next(r for r in bundle.audit["row_dispositions"] if r["event_id"] == rows[0]["event_id"])
            self.assertEqual(record["status"], "unavailable")
            self.assertEqual(bundle.audit["samples"]["fit"]["rows"], 255)

    def test_wrong_clock_and_duplicate_event_cannot_enter(self):
        rows, labels = fixture()
        rows[0]["decision_timestamp"] = "2019-01-02T08:59:00-05:00"
        bundle = models.fit_family_fold("ridge", rows, labels, FOLD, CALENDAR)
        self.assertEqual(bundle.audit["status"], "insufficient_sample")
        with self.assertRaisesRegex(ValueError, "unique"):
            models.fit_family_fold("ridge", self.rows + [self.rows[0]], labels, FOLD, CALENDAR)

    def test_fit_failure_preserves_warning_and_no_family_fallback(self):
        def fail(*args):
            warnings.warn("synthetic fitting warning", RuntimeWarning)
            raise RuntimeError("synthetic fit failure")
        with patch.object(models.shared, "_fit_family", side_effect=fail) as fitter:
            bundle = models.fit_family_fold("ridge", self.rows, self.labels, FOLD, CALENDAR)
        self.assertEqual(fitter.call_count, 1)
        self.assertEqual(bundle.family, "ridge")
        self.assertEqual(bundle.audit["status"], "failed")
        self.assertEqual(bundle.audit["failed_stage"], "fit")
        self.assertEqual(bundle.audit["warnings"][0]["message"], "synthetic fitting warning")

    def test_six_head_calibration_is_explicit_failure(self):
        with patch.object(models.shared, "_fit_family", return_value=ConstantModel((0,) * 6)), \
             patch.object(models.shared, "_preprocessing", return_value={}):
            bundle = models.fit_family_fold("ridge", self.rows, self.labels, FOLD, CALENDAR)
        self.assertFalse(bundle.available)
        self.assertEqual(bundle.audit["failed_stage"], "calibration")
        self.assertIn("n-by-2", bundle.audit["error"])

    def test_invalid_return_and_nonfinite_row_abstain_without_hiding_output(self):
        bundle = deepcopy(self.bundles["ridge"])
        bundle.model = ConstantModel((-1.5, -.02))
        bundle.bias = np.zeros(2)
        output = models.predict_events(bundle, self.rows[-3:])
        self.assertEqual(output["forecasts"][0]["status"], "unavailable")
        self.assertEqual(output["forecasts"][0]["raw"], [-1.5, -.02])
        self.assertEqual(output["forecasts"][0]["corrected"], [-1.5, 0])
        bundle.model = ConstantModel((float("nan"), .02))
        output = models.predict_events(bundle, self.rows[-3:])
        self.assertEqual(output["forecasts"][0]["raw"][0], "nan")
        self.assertEqual(output["forecasts"][0]["status"], "unavailable")

    def test_prediction_shape_failure_retains_all_requested_events(self):
        bundle = deepcopy(self.bundles["ridge"])
        bundle.model = ConstantModel((0,) * 6)
        output = models.predict_events(bundle, self.rows[-3:])
        self.assertEqual(len(output["forecasts"]), 3)
        self.assertIn("n-by-2", output["error"])
        self.assertTrue(all(r["status"] == "unavailable" for r in output["forecasts"]))

    def test_source_rows_saved_models_and_forecasts_reload_exactly(self):
        for family, bundle in self.bundles.items():
            with tempfile.TemporaryDirectory(prefix="synthetic-model-", dir=HERE) as temp:
                path = Path(temp) / family
                manifest = models.save_bundle(bundle, path)
                self.assertTrue(manifest["reload_check"]["exact_equal"])
                self.assertEqual(manifest["reload_check"]["rows"], 64)
                reloaded = models.load_bundle(path)
                self.assertEqual(reloaded.rows, self.rows)
                self.assertEqual(models.predict_events(bundle, self.rows[-3:]),
                                 models.predict_events(reloaded, self.rows[-3:]))
                with self.assertRaises(FileExistsError):
                    models.save_bundle(bundle, path)
                with (path / "model.joblib").open("ab") as handle:
                    handle.write(b"corrupt")
                with self.assertRaisesRegex(ValueError, "integrity"):
                    models.load_bundle(path)


    def test_failed_calibration_retains_fitted_model_and_raw_nonfinite_outputs(self):
        with patch.object(models.shared, "_fit_family", return_value=ConstantModel((float("nan"), -.02))), \
             patch.object(models.shared, "_preprocessing", return_value={}):
            bundle = models.fit_family_fold("ridge", self.rows, self.labels, FOLD, CALENDAR)
        self.assertFalse(bundle.available)
        self.assertIsNotNone(bundle.model)
        self.assertEqual(bundle.audit["failed_stage"], "calibration")
        self.assertEqual(bundle.audit["calibration"]["raw"][0], ["nan", -.02])
        np.testing.assert_array_equal(bundle.training_mean,
            np.asarray(bundle.audit["samples"]["fit"]["targets"]).mean(axis=0))
        with tempfile.TemporaryDirectory(prefix="synthetic-failed-", dir=HERE) as temp:
            path = Path(temp) / "failed"
            models.save_bundle(bundle, path)
            loaded = models.load_bundle(path)
            self.assertFalse(loaded.available)
            self.assertIsNotNone(loaded.model)
            self.assertEqual(loaded.audit, bundle.audit)

    def test_insufficient_sample_artifact_retains_absence_and_all_rows(self):
        rows, labels = fixture(fit_count=255)
        bundle = models.fit_family_fold("ridge", rows, labels, FOLD, CALENDAR)
        with tempfile.TemporaryDirectory(prefix="synthetic-insufficient-", dir=HERE) as temp:
            path = Path(temp) / "insufficient"
            models.save_bundle(bundle, path)
            loaded = models.load_bundle(path)
            self.assertFalse(loaded.available)
            self.assertIsNone(loaded.model)
            self.assertEqual(loaded.rows, rows)
            self.assertEqual(loaded.audit, bundle.audit)

    def test_specification_and_fold_are_fixed(self):
        with self.assertRaisesRegex(ValueError, "predeclared"):
            models.fit_family_fold("ridge", self.rows, self.labels, {**FOLD, "test_decision_year": 2022}, CALENDAR)
        with patch.dict(models.shared.MODEL_CONFIG, {"ridge": {"alpha": 1}}):
            with self.assertRaisesRegex(ValueError, "preset"):
                models.specification()


if __name__ == "__main__":
    unittest.main(verbosity=2)
