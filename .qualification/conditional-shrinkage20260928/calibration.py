"""One declared calibration-only attenuation; no selection or model fitting."""

import hashlib
import json

import numpy as np


SCHEMA = "conditional-return-shrinkage-v1"
HEAD_NAMES = (
    "return_1", "return_3", "return_5", "downside_1", "downside_3", "downside_5"
)


def _six_heads(values):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != len(HEAD_NAMES):
        raise ValueError("Expected a two-dimensional six-head array")
    return values


def _array_identity(values):
    return {
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "sha256": hashlib.sha256(values.tobytes(order="C")).hexdigest(),
    }


def fit_return_shrinkage(raw_calibration, targets, *, source_identity=None):
    """Fit three affine slopes from the supplied saved calibration rows only.

    Every supplied row must be finite. The caller verifies original manifests,
    exact sample pairing and purged boundaries before supplying these arrays.
    No row filtering, weighting, resampling or test data enters this fit.
    """
    raw = _six_heads(raw_calibration)
    targets = _six_heads(targets)
    if raw.shape != targets.shape or not len(raw):
        raise ValueError("Calibration arrays must have matching nonempty shapes")
    if not np.isfinite(raw).all() or not np.isfinite(targets).all():
        raise ValueError("Saved calibration arrays must be entirely finite")

    coefficients = []
    for index, name in enumerate(HEAD_NAMES[:3]):
        x, y = raw[:, index], targets[:, index]
        constant = bool(np.all(x == x[0]))
        # Exact equality handles constant nonbinary floats without an epsilon.
        mean_x = float(x[0]) if constant else float(np.mean(x))
        mean_y = float(np.mean(y))
        variance = 0.0 if constant else float(np.mean((x - mean_x) ** 2))
        covariance = 0.0 if constant else float(np.mean((x - mean_x) * (y - mean_y)))
        if not np.isfinite([mean_x, mean_y, variance, covariance]).all():
            raise ValueError("Calibration moments must be finite")
        if not constant and variance == 0.0:
            raise ValueError("Nonconstant calibration variance underflowed to zero")
        unconstrained = 0.0 if constant else covariance / variance
        if not np.isfinite(unconstrained):
            raise ValueError("Calibration slope must be finite")
        slope = float(np.clip(unconstrained, 0.0, 1.0))
        intercept = mean_y - slope * mean_x
        if not np.isfinite(intercept):
            raise ValueError("Calibration intercept must be finite")
        coefficients.append({
            "head": name,
            "index": index,
            "count": len(raw),
            "mean_raw": mean_x,
            "mean_target": mean_y,
            "variance_raw": variance,
            "covariance_raw_target": covariance,
            "unconstrained_slope": unconstrained,
            "slope": slope,
            "intercept": intercept,
            "zero_variance": constant,
        })

    return {
        "schema": SCHEMA,
        "head_names": list(HEAD_NAMES),
        "calibration_rows": len(raw),
        "calibration_arrays": {
            "raw": _array_identity(raw),
            "targets": _array_identity(targets),
        },
        "source_identity": json.loads(json.dumps(source_identity or {}, allow_nan=False)),
        "returns": coefficients,
    }


def apply_return_shrinkage(parameters, raw_test, original_corrected):
    """Transform returns while copying original float64 downside bytes.

    NaN predictions remain unavailable; infinite predictions fail explicitly.
    Test targets and test-wide statistics are deliberately absent from this API.
    """
    if parameters.get("schema") != SCHEMA or parameters.get("head_names") != list(HEAD_NAMES):
        raise ValueError("Unexpected shrinkage schema or head order")
    raw = _six_heads(raw_test)
    original = np.asarray(original_corrected)
    if original.dtype != np.float64:
        raise ValueError("Original corrected forecasts must be float64 for exact downside preservation")
    if raw.shape != original.shape:
        raise ValueError("Raw and original corrected forecasts must have matching shapes")
    if np.isinf(raw).any() or np.isinf(original).any():
        raise ValueError("Saved test forecasts cannot contain infinite values")
    coefficients = parameters["returns"]
    if len(coefficients) != 3:
        raise ValueError("Expected exactly three return coefficients")
    result = original.copy(order="C")
    for index, head in enumerate(coefficients):
        if head["index"] != index or head["head"] != HEAD_NAMES[index]:
            raise ValueError("Unexpected coefficient head order")
        slope, intercept = head["slope"], head["intercept"]
        if not np.isfinite([slope, intercept]).all() or not 0 <= slope <= 1:
            raise ValueError("Invalid saved calibration coefficients")
        result[:, index] = intercept + slope * raw[:, index]
    if np.isinf(result[:, :3]).any():
        raise ValueError("Transformed return overflowed")
    return result
