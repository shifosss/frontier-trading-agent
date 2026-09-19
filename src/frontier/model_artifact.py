"""Integrity-checked joblib bundles for trusted local artifacts only.

Checksums detect damage, not malicious replacement. Never load uploaded or
untrusted files: joblib deserialization can execute code.
"""

import hashlib
import io
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import scipy
import sklearn

from frontier.ensemble_models import BASE_MODEL_NAMES, HEAD_NAMES, FittedHeads

SCHEMA_VERSION = "fitted-heads-v1"


def _runtime():
    return {
        "python": ".".join(platform.python_version_tuple()[:2]),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "sklearn": sklearn.__version__,
        "joblib": joblib.__version__,
    }


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _metadata(metadata, feature_count):
    if not isinstance(metadata, dict):
        raise ValueError("Artifact metadata must be a JSON object")
    names = metadata.get("feature_names")
    if (
        not isinstance(names, list)
        or len(names) != feature_count
        or not all(isinstance(name, str) and name for name in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("Artifact feature_names must uniquely identify every ordered feature")
    if metadata.get("head_names") != list(HEAD_NAMES):
        raise ValueError("Artifact head_names order is incompatible")
    return _json(metadata)


def _validate_bundle(bundle):
    if not isinstance(bundle, FittedHeads):
        raise ValueError("Artifact payload is not FittedHeads")
    if tuple(bundle.models) != BASE_MODEL_NAMES:
        raise ValueError("Artifact model order is incompatible")
    if bundle.imputer.n_features_in_ != bundle.feature_count:
        raise ValueError("Artifact feature count is incompatible")
    if (
        bundle.weights.shape != (len(BASE_MODEL_NAMES), 3)
        or not np.isfinite(bundle.weights).all()
        or (bundle.weights < 0).any()
        or not np.allclose(bundle.weights.sum(axis=0), 1.0)
    ):
        raise ValueError("Artifact calibration weights are invalid")
    if tuple(bundle.audit["config"]["head_names"]) != HEAD_NAMES:
        raise ValueError("Artifact payload head order is incompatible")


def save_heads(bundle, path, metadata):
    """Save a trusted bundle in a new directory; refuse existing destinations."""
    _validate_bundle(bundle)
    metadata_json = _metadata(metadata, bundle.feature_count)
    metadata = json.loads(metadata_json)
    payload = io.BytesIO()
    joblib.dump({"bundle": bundle, "metadata": metadata}, payload, compress=3)
    raw = payload.getvalue()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "payload_file": "heads.joblib",
        "payload_sha256": _digest(raw),
        "metadata_sha256": _digest(metadata_json.encode("utf-8")),
        "runtime": _runtime(),
        "feature_count": bundle.feature_count,
        "feature_names": metadata["feature_names"],
        "head_names": list(HEAD_NAMES),
        "model_names": list(BASE_MODEL_NAMES),
        "metadata": metadata,
    }
    destination = Path(path)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "heads.joblib").write_bytes(raw)
    (destination / "manifest.json").write_text(_json(manifest) + "\n", encoding="utf-8")
    return manifest


def load_heads(path):
    """Verify manifest and exact payload bytes BEFORE trusted-local deserialization."""
    source = Path(path)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Artifact schema version is incompatible")
    if manifest.get("runtime") != _runtime():
        raise ValueError("Artifact runtime is incompatible; refit in this runtime")
    if manifest.get("payload_file") != "heads.joblib":
        raise ValueError("Artifact payload file is invalid")
    count = manifest.get("feature_count")
    if type(count) is not int or count < 1:
        raise ValueError("Artifact feature count is invalid")
    metadata = manifest.get("metadata")
    metadata_json = _metadata(metadata, count)
    if manifest.get("metadata_sha256") != _digest(metadata_json.encode("utf-8")):
        raise ValueError("Artifact metadata integrity check failed")
    if manifest.get("feature_names") != metadata["feature_names"]:
        raise ValueError("Artifact feature order is incompatible")
    if manifest.get("head_names") != list(HEAD_NAMES):
        raise ValueError("Artifact head order is incompatible")
    if manifest.get("model_names") != list(BASE_MODEL_NAMES):
        raise ValueError("Artifact model order is incompatible")
    raw = (source / "heads.joblib").read_bytes()
    if manifest.get("payload_sha256") != _digest(raw):
        raise ValueError("Artifact payload integrity check failed")
    # Load the exact verified bytes, preventing a file-replacement race.
    payload = joblib.load(io.BytesIO(raw))
    if not isinstance(payload, dict) or _json(payload.get("metadata")) != metadata_json:
        raise ValueError("Artifact payload metadata is incompatible")
    bundle = payload.get("bundle")
    _validate_bundle(bundle)
    if bundle.feature_count != count:
        raise ValueError("Artifact payload feature count is incompatible")
    return bundle, manifest
