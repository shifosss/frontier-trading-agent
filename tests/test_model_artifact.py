import json

import numpy as np
import pytest

from frontier import model_artifact as artifacts
from frontier.ensemble_models import HEAD_NAMES, fit_heads, predict_heads


@pytest.fixture(scope="module")
def fitted_bundle():
    rng = np.random.default_rng(729)
    features = rng.normal(size=(120, 4))
    features[::5, 2] = np.nan
    targets = rng.normal(0, 0.01, size=(120, 6))
    targets[:, 3:] = np.abs(targets[:, 3:])
    bundle = fit_heads(features[:80], targets[:80], features[80:100], targets[80:100])
    return bundle, features[100:]


def metadata():
    return {
        "feature_names": ["price", "volume", "atr", "momentum"],
        "head_names": list(HEAD_NAMES),
        "capture": "frozen-capture-id",
        "sample_audit": {"rows": [2, 4, 9]},
    }


def test_roundtrip_preserves_predictions_audit_and_metadata(tmp_path, fitted_bundle):
    bundle, features = fitted_bundle
    path = tmp_path / "new-model"
    saved = artifacts.save_heads(bundle, path, metadata())
    restored, manifest = artifacts.load_heads(path)
    assert manifest == saved
    assert manifest["metadata"] == metadata()
    assert restored.audit == bundle.audit
    before = predict_heads(bundle, features)
    after = predict_heads(restored, features)
    for name in before:
        np.testing.assert_array_equal(before[name], after[name])
    assert all(x.shape == (0, 6) for x in predict_heads(restored, features[:0]).values())
    with pytest.raises(FileExistsError):
        artifacts.save_heads(bundle, path, metadata())


@pytest.mark.parametrize(
    "change,match",
    [
        ("payload", "payload integrity"),
        ("schema_version", "schema version"),
        ("runtime", "runtime"),
        ("feature_names", "feature order"),
        ("head_names", "head order"),
        ("model_names", "model order"),
        ("metadata", "metadata integrity"),
        ("payload_file", "payload file"),
    ],
)
def test_corruption_rejected_before_deserialization(
    tmp_path, fitted_bundle, monkeypatch, change, match
):
    bundle, _ = fitted_bundle
    path = tmp_path / "model"
    manifest = artifacts.save_heads(bundle, path, metadata())
    if change == "payload":
        with (path / "heads.joblib").open("ab") as stream:
            stream.write(b"tampered")
    else:
        if change in {"feature_names", "head_names", "model_names"}:
            manifest[change] = list(reversed(manifest[change]))
        elif change == "metadata":
            manifest["metadata"]["feature_names"].reverse()
        else:
            manifest[change] = "incompatible"
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def forbidden_load(*args, **kwargs):
        pytest.fail("Unverified artifact reached joblib.load")

    monkeypatch.setattr(artifacts.joblib, "load", forbidden_load)
    with pytest.raises(ValueError, match=match):
        artifacts.load_heads(path)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("feature_names", ["a"] * 4, "uniquely"),
        ("feature_names", ["a"], "uniquely"),
        ("head_names", list(reversed(HEAD_NAMES)), "head_names order"),
        ("extra", float("nan"), "JSON"),
    ],
)
def test_invalid_metadata_never_creates_destination(tmp_path, fitted_bundle, field, value, match):
    data = metadata()
    data[field] = value
    path = tmp_path / "model"
    with pytest.raises(ValueError, match=match):
        artifacts.save_heads(fitted_bundle[0], path, data)
    assert not path.exists()
