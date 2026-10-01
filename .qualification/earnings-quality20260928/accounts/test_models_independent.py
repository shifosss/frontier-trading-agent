"""Independent synthetic review of source binding, causal gates and calibration."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models"))
import earnings_models as models
from test_earnings_models import CALENDAR, FOLD, ConstantModel, fixture
from account_adapter import _identity as account_identity


def fit_synthetic(rows, labels):
    with patch.object(models.shared, "_fit_family", return_value=ConstantModel((.03, -.04))), \
         patch.object(models.shared, "_preprocessing", return_value={}):
        return models.fit_family_fold("ridge", rows, labels, FOLD, CALENDAR)


def test_prediction_binds_original_source_payload_and_matches_account_digest():
    rows, labels = fixture()
    rows[-1]["original_source"]["issuer_name"] = "Synthétique"
    bundle = fit_synthetic(rows, labels)
    output = models.predict_events(bundle, [rows[-1]])["forecasts"][0]
    assert output["prepared_row_sha256"] == account_identity(rows[-1])["prepared_event_sha256"]
    changed = deepcopy(rows[-1]); changed["original_source"]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="saved historical source"):
        models.predict_events(bundle, [changed])
    changed = deepcopy(rows[-1]); changed["model_inputs"][2] += .01
    with pytest.raises(ValueError, match="saved historical source"):
        models.predict_events(bundle, [changed])


def test_prediction_cannot_readmit_saved_causally_unavailable_test_row():
    rows, labels = fixture()
    rows[-1]["planned_label_end_session"] = "2021-01-05"  # Absent exchange session.
    bundle = fit_synthetic(rows, labels)
    disposition = next(x for x in bundle.audit["row_dispositions"] if x["event_id"] == rows[-1]["event_id"])
    output = models.predict_events(bundle, [rows[-1]])["forecasts"][0]
    assert disposition["status"] == "unavailable"
    assert output["status"] == "unavailable"
    assert set(disposition["reasons"]).issubset(output["reasons"])


def test_constant_raw_downside_calibration_matches_decimal_formula():
    rows, labels = fixture()
    bundle = fit_synthetic(rows, labels)
    cal_ids = bundle.audit["samples"]["calibration"]["event_ids"]
    n = Decimal(len(cal_ids))
    expected_return_bias = sum(Decimal(str(labels[key]["targets"][0])) - Decimal(".03") for key in cal_ids) / n
    expected_downside_bias = sum(Decimal(str(labels[key]["targets"][1])) for key in cal_ids) / n
    np.testing.assert_allclose(bundle.bias, [float(expected_return_bias), float(expected_downside_bias)], rtol=0, atol=1e-14)
    forecast = models.predict_events(bundle, [rows[-1]])["forecasts"][0]
    assert forecast["raw"] == [.03, -.04]
    assert forecast["uncalibrated"] == [.03, 0.]
    np.testing.assert_allclose(forecast["corrected"], [
        float(Decimal(".03") + expected_return_bias), float(expected_downside_bias)], rtol=0, atol=1e-14)
    assert bundle.quantile_edges == {"raw": [[], []], "corrected": [[], []]}


def test_purge_precedes_label_access_and_reduces_fitting_sample_gate():
    rows, labels = fixture()
    rows[0]["decision_timestamp"] = "2019-12-31T09:00:00-05:00"
    rows[0]["planned_label_end_session"] = "2020-01-02"
    class GuardedLabels(dict):
        def get(self, key, default=None):
            assert key != rows[0]["event_id"] and not key.startswith("test")
            return super().get(key, default)
    with patch.object(models.shared, "_fit_family") as fitter:
        bundle = models.fit_family_fold("ridge", rows, GuardedLabels(labels), FOLD, CALENDAR)
    fitter.assert_not_called()
    assert bundle.audit["status"] == "insufficient_sample"
    assert bundle.audit["samples"]["fit"]["rows"] == 255
    assert bundle.audit["row_dispositions"][0]["status"] == "purged"


def test_saved_model_rejects_changed_running_code_identity(tmp_path):
    rows, labels = fixture();bundle = fit_synthetic(rows, labels)
    artifact = tmp_path / "model"
    models.save_bundle(bundle, artifact)
    changed = {**models._code_identity(), "adapter": "0" * 64}
    with patch.object(models, "_code_identity", return_value=changed):
        with pytest.raises(ValueError, match="code"):
            models.load_bundle(artifact)
