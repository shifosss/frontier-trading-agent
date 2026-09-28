"""Purged conditional research fits; no account, broker or future-test selection.

Only the two existing learner presets are compared. Samples, failed fits and raw
calibration forecasts remain available even when the whole block must abstain.
"""

import hashlib
import io
import json
import warnings
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from frontier.conditional_features import gather_rows
from frontier.ensemble_models import (
    HEAD_NAMES,
    MODEL_CONFIG,
    PREDICTION_BATCH_SIZE,
    _features,
    _prediction,
    _targets,
)
from frontier.model_artifact import _runtime

FAMILIES = ("ridge", "hist_gradient_boosting")
SCHEMA = "conditional-model-v1"
FIT_SESSIONS = 504
CALIBRATION_SESSIONS = 252
INNER_PREFIXES = (252, 336, 420)
INNER_VALIDATION = 84


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _array_identity(value):
    array = np.ascontiguousarray(value)
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "sha256": _digest(array.tobytes()),
    }


def reference_notionals(prices, atrs):
    """Independent USD2,000/40bps reference quantities, with no coupled slot fill."""
    prices, atrs = np.asarray(prices, dtype=float), np.asarray(atrs, dtype=float)
    valid = np.isfinite(prices) & np.isfinite(atrs) & (prices > 0) & (atrs > 0)
    result = np.full(prices.shape, np.nan)
    quantity = np.minimum(
        np.floor(400.0 / (prices[valid] * 1.002)),
        np.floor(10.0 / (2.0 * atrs[valid])),
    )
    result[valid] = quantity * prices[valid]
    return result


def sample_conditional_rows(
    market, features, context, start, end, boundary, *, seed=1729, limit=96
):
    """Sample unique eligible stocks before any target inspection; [start,end)."""
    if not 0 <= start <= end <= len(market["sessions"]) or boundary < start:
        raise ValueError("Sampling bounds must follow the market calendar")
    if not isinstance(limit, int) or not 1 <= limit <= 96:
        raise ValueError("Sample limit must be an integer in [1,96]")
    rows, columns = [], []
    for row in range(start, end):
        eligible = np.flatnonzero(context["eligible"][row])
        rng = np.random.default_rng(np.random.SeedSequence([seed, row]))
        selected = np.sort(rng.choice(eligible, size=min(limit, len(eligible)), replace=False))
        rows.extend([row] * len(selected))
        columns.extend(selected.tolist())
    rows, columns = np.asarray(rows, dtype=np.int64), np.asarray(columns, dtype=np.int64)
    # Gathering follows the draw, so a missing target cannot produce a replacement.
    X = gather_rows(features, context, rows, columns)
    y = np.asarray(features["labels"][rows, columns], dtype=float)
    label_end = np.asarray(features["label_end"])[rows].max(axis=1)
    notionals = reference_notionals(market["close"][rows, columns], market["atr"][rows, columns])
    reasons = []
    for index in range(len(rows)):
        reason = []
        if label_end[index] >= boundary:
            reason.append("label_reaches_boundary")
        if not np.isfinite(y[index]).all():
            reason.append("nonfinite_label")
        if np.any(y[index, 3:] < 0):
            reason.append("negative_downside_label")
        if np.isinf(X[index]).any():
            reason.append("infinite_feature")
        if not np.isfinite(notionals[index]) or notionals[index] < 0:
            reason.append("invalid_reference_quote")
        reasons.append(reason)
    retained = np.array([not reason for reason in reasons], dtype=bool)
    selected = [
        [int(row), int(column), int(label_end[k]), reasons[k]]
        for k, (row, column) in enumerate(zip(rows, columns, strict=True))
    ]
    audit = {
        "start": start,
        "end_exclusive": end,
        "label_boundary": boundary,
        "seed": seed,
        "limit_per_date": limit,
        "sampling": "SeedSequence(seed,absolute_session_index), unique draw before label filtering",
        "selected_count": len(rows),
        "retained_count": int(retained.sum()),
        "selected": selected,
        "selected_columns": "session_index,symbol_index,max_label_end,exclusion_reasons",
        "symbol_order": list(market["symbols"]),
        "sessions": {str(i): str(market["sessions"][i]) for i in range(start, end)},
        "feature_names": list(context["feature_names"]),
        "selected_sha256": _digest(_json(selected).encode()),
    }
    return {
        "rows": rows[retained],
        "columns": columns[retained],
        "X": X[retained],
        "y": y[retained],
        "reference_notional": notionals[retained],
        "label_end": label_end[retained],
        "audit": audit,
    }


def utility_loss(targets, predictions, reference_notional, rows):
    """Equal stocks within date, then equal dates/horizons; no broker-cost input."""
    targets = _targets(targets, len(rows), "utility targets")
    predictions = _targets(predictions, len(rows), "utility predictions")
    notionals = np.asarray(reference_notional, dtype=float)
    rows = np.asarray(rows)
    if not len(rows) or notionals.shape != (len(rows),):
        raise ValueError("Utility loss requires matching nonempty rows and notionals")
    if not np.isfinite(notionals).all() or (notionals < 0).any():
        raise ValueError("Reference notionals must be finite and nonnegative")
    error = notionals[:, None] * (
        predictions[:, :3] - 0.5 * predictions[:, 3:] - targets[:, :3] + 0.5 * targets[:, 3:]
    )
    squared = np.square(error)
    dates = [
        {
            "session_index": int(day),
            "rows": int((rows == day).sum()),
            "loss_by_horizon": squared[rows == day].mean(axis=0).tolist(),
        }
        for day in np.unique(rows)
    ]
    per_horizon = np.mean([record["loss_by_horizon"] for record in dates], axis=0)
    return {
        "value": float(per_horizon.mean()),
        "by_horizon": per_horizon.tolist(),
        "dates": dates,
        "weighting": "equal stocks within date; equal dates and horizons",
    }


def _fit_family(family, X, y, seed):
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    if family == "ridge":
        model = make_pipeline(imputer, StandardScaler(), Ridge(**MODEL_CONFIG["ridge"]))
    else:
        estimator = HistGradientBoostingRegressor(
            **MODEL_CONFIG["hist_gradient_boosting"], random_state=seed
        )
        model = make_pipeline(imputer, MultiOutputRegressor(estimator, n_jobs=1))
    with threadpool_limits(limits=2):
        model.fit(X, y)
    return model


def _family_prediction(model, X):
    with threadpool_limits(limits=2):
        return _prediction(model, X)


def _preprocessing(model):
    imputer = model.steps[0][1]
    result = {
        "feature_medians": imputer.statistics_.tolist(),
        "missing_indicator_features": imputer.indicator_.features_.tolist(),
    }
    if "standardscaler" in model.named_steps:
        scaler = model.named_steps["standardscaler"]
        result.update(feature_mean=scaler.mean_.tolist(), feature_scale=scaler.scale_.tolist())
    return result


def _attempt_fit(family, sample, indices, seed, record):
    """Failures are evidence; a failed candidate never silently leaves the denominator."""
    caught = []
    try:
        if not len(indices):
            raise ValueError("No retained fitting rows")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = _fit_family(family, sample["X"][indices], sample["y"][indices], seed)
        record.update(
            status="fit",
            fitted_rows=len(indices),
            preprocessing=_preprocessing(model),
        )
        return model
    except Exception as error:
        record.update(status="failed", error_type=type(error).__name__, error=str(error))
        return None
    finally:
        record["warnings"] = [
            {"category": item.category.__name__, "message": str(item.message)} for item in caught
        ]


def _indices(sample, start, end, boundary):
    return np.flatnonzero(
        (sample["rows"] >= start) & (sample["rows"] < end) & (sample["label_end"] < boundary)
    )


def _validate_sample(sample, start, end, boundary):
    X = _features(sample["X"], "sample X")
    y = _targets(sample["y"], len(X), "sample y")
    for key in ("rows", "columns", "reference_notional", "label_end"):
        if np.asarray(sample[key]).shape != (len(X),):
            raise ValueError(f"Sample {key} must match X")
    if len(_indices(sample, start, end, boundary)) != len(X):
        raise ValueError("Sample contains rows or labels outside its purged window")
    if len(set(zip(sample["rows"], sample["columns"], strict=True))) != len(X):
        raise ValueError("Sample contains duplicate stock/date rows")
    if (
        not np.isfinite(sample["reference_notional"]).all()
        or (sample["reference_notional"] < 0).any()
    ):
        raise ValueError("Sample reference notionals are invalid")
    return X, y


@dataclass
class FittedConditional:
    model: object
    family: str | None
    bias: np.ndarray
    feature_count: int
    audit: dict

    @property
    def available(self):
        return self.model is not None


def predict_conditional(bundle, X):
    """Forecast every supplied feature row without consulting future outcomes."""
    X = _features(X, "prediction X")
    if X.shape[1] != bundle.feature_count:
        raise ValueError("Prediction features must follow the fitted feature order")
    raw = np.full((len(X), len(HEAD_NAMES)), np.nan)
    if bundle.available:
        for start in range(0, len(X), PREDICTION_BATCH_SIZE):
            raw[start : start + PREDICTION_BATCH_SIZE] = _family_prediction(
                bundle.model, X[start : start + PREDICTION_BATCH_SIZE]
            )
    corrected = raw + bundle.bias
    corrected[:, 3:] = np.maximum(0, corrected[:, 3:])
    return {"raw": raw, "corrected": corrected}


def fit_conditional_block(
    fit_sample,
    cal_sample,
    fit_start,
    calibration_start,
    test_start,
    save_directory,
    *,
    seed=1729,
    fallback_policy="abstain",
    metadata=None,
    progress=None,
):
    """Select inside fitting only, calibrate later, and save one immutable block."""
    if calibration_start - fit_start != FIT_SESSIONS:
        raise ValueError("Fitting window must contain 504 calendar sessions")
    if test_start - calibration_start != CALIBRATION_SESSIONS:
        raise ValueError("Calibration window must contain 252 calendar sessions")
    if fallback_policy != "abstain":
        raise ValueError("Declared final-fit failure policy is abstain")
    X, y = _validate_sample(fit_sample, fit_start, calibration_start, calibration_start)
    X_cal, y_cal = _validate_sample(cal_sample, calibration_start, test_start, test_start)
    names = fit_sample["audit"]["feature_names"]
    if X.shape[1] != X_cal.shape[1] or names != cal_sample["audit"]["feature_names"]:
        raise ValueError("Fitting and calibration features must have the same order")
    if len(names) != X.shape[1] or len(set(names)) != len(names):
        raise ValueError("Ordered feature names must be unique and complete")
    destination = Path(save_directory)
    destination.mkdir(parents=True, exist_ok=False)
    attempt = {
        "schema_version": SCHEMA,
        "fit_start": fit_start,
        "calibration_start": calibration_start,
        "test_start": test_start,
        "seed": seed,
        "fallback_policy": fallback_policy,
        "families": list(FAMILIES),
        "presets": {name: deepcopy(MODEL_CONFIG[name]) for name in FAMILIES},
        "feature_names": names,
        "head_names": list(HEAD_NAMES),
        "reference": {"nav": 2000, "round_trip_bps": 40, "coupled_slots": False},
        "loss": "equal-date/equal-horizon squared Nref*((rhat-.5*dhat)-(r-.5*d))",
        "metadata": metadata or {},
        "arrays": {
            label: {
                key: _array_identity(sample[key])
                for key in ("rows", "columns", "X", "y", "reference_notional", "label_end")
            }
            for label, sample in (("fit", fit_sample), ("calibration", cal_sample))
        },
    }
    (destination / "attempt.json").write_text(_json(attempt) + "\n", encoding="utf-8")
    (destination / "samples.json").write_text(
        _json({"fit": fit_sample["audit"], "calibration": cal_sample["audit"]}) + "\n",
        encoding="utf-8",
    )
    audit = {
        "status": "unavailable",
        "inner_folds": [],
        "family_selection": {},
        "final_fits": [],
        "calibration": None,
        "attempt": attempt,
    }
    losses = {family: [] for family in FAMILIES}
    for prefix in INNER_PREFIXES:
        validation_start = fit_start + prefix
        validation_end = validation_start + INNER_VALIDATION
        train_indices = _indices(fit_sample, fit_start, validation_start, validation_start)
        valid_indices = _indices(fit_sample, validation_start, validation_end, validation_end)
        fold = {
            "fit_start": fit_start,
            "validation_start": validation_start,
            "validation_end_exclusive": validation_end,
            "fit_rows": len(train_indices),
            "validation_rows": len(valid_indices),
            "fit_max_label_end": int(fit_sample["label_end"][train_indices].max())
            if len(train_indices)
            else None,
            "validation_max_label_end": int(fit_sample["label_end"][valid_indices].max())
            if len(valid_indices)
            else None,
            "models": {},
        }
        for family in FAMILIES:
            if progress:
                progress(
                    {
                        "phase": "inner_fit",
                        "family": family,
                        "validation_start": validation_start,
                        "validation_end_exclusive": validation_end,
                    }
                )
            record = {"family": family}
            fold["models"][family] = record
            model = _attempt_fit(family, fit_sample, train_indices, seed, record)
            if model is None:
                continue
            try:
                prediction = _family_prediction(model, X[valid_indices])
                record["loss"] = utility_loss(
                    y[valid_indices],
                    prediction,
                    fit_sample["reference_notional"][valid_indices],
                    fit_sample["rows"][valid_indices],
                )
                baseline = np.tile(y[train_indices].mean(axis=0), (len(valid_indices), 1))
                record["training_mean_baseline_loss"] = utility_loss(
                    y[valid_indices],
                    baseline,
                    fit_sample["reference_notional"][valid_indices],
                    fit_sample["rows"][valid_indices],
                )
                record["return_mse"] = np.mean(
                    np.square(y[valid_indices, :3] - prediction[:, :3]), axis=0
                ).tolist()
                record["downside_mse"] = np.mean(
                    np.square(y[valid_indices, 3:] - prediction[:, 3:]), axis=0
                ).tolist()
                record["status"] = "complete"
                losses[family].append(record["loss"]["dates"])
            except Exception as error:
                record.update(status="failed", error_type=type(error).__name__, error=str(error))
        audit["inner_folds"].append(fold)
    for family in FAMILIES:
        eligible = len(losses[family]) == len(INNER_PREFIXES)
        dates = [day for fold_dates in losses[family] for day in fold_dates]
        audit["family_selection"][family] = {
            "eligible": eligible,
            "completed_folds": len(losses[family]),
            "mean_loss": float(np.mean([day["loss_by_horizon"] for day in dates]))
            if eligible
            else None,
            "validation_dates": len(dates),
        }
    ranked = sorted(
        [name for name in FAMILIES if audit["family_selection"][name]["eligible"]],
        key=lambda name: (audit["family_selection"][name]["mean_loss"], FAMILIES.index(name)),
    )
    audit["selected_family"] = ranked[0] if ranked else None
    allowed = ranked[:1]
    bundle = FittedConditional(None, None, np.zeros(6), X.shape[1], audit)
    calibration_predictions = {
        "raw": np.full(y_cal.shape, np.nan),
        "corrected": np.full(y_cal.shape, np.nan),
    }
    for family in allowed:
        if progress:
            progress({"phase": "final_fit", "family": family, "rows": len(X)})
        record = {"family": family, "fallback": family != audit["selected_family"]}
        audit["final_fits"].append(record)
        model = _attempt_fit(family, fit_sample, np.arange(len(X)), seed, record)
        if model is None:
            continue
        if progress:
            progress({"phase": "calibration", "family": family, "rows": len(X_cal)})
        try:
            if not len(X_cal):
                raise ValueError("No retained calibration rows")
            raw = _family_prediction(model, X_cal)
            bias = np.mean(y_cal - raw, axis=0)
            candidate = FittedConditional(model, family, bias, X.shape[1], audit)
            calibration_predictions = predict_conditional(candidate, X_cal)
            audit["calibration"] = {
                "rows": len(y_cal),
                "method": "pooled per-row mean(target - uncalibrated forecast), six outputs",
                "downside": "nonnegative before bias and after bias; returns unbounded",
                "bias": bias.tolist(),
                "raw_utility_loss": utility_loss(
                    y_cal, raw, cal_sample["reference_notional"], cal_sample["rows"]
                ),
                "corrected_utility_loss": utility_loss(
                    y_cal,
                    calibration_predictions["corrected"],
                    cal_sample["reference_notional"],
                    cal_sample["rows"],
                ),
                "interpretation": (
                    "Correction fits this calibration set; corrected error is not held out."
                ),
            }
            record["status"] = "complete"
            audit["status"] = "complete"
            audit["used_family"] = family
            bundle = candidate
            break
        except Exception as error:
            record.update(status="failed", error_type=type(error).__name__, error=str(error))
    np.savez_compressed(
        destination / "calibration-predictions.npz",
        rows=cal_sample["rows"],
        columns=cal_sample["columns"],
        targets=y_cal,
        reference_notional=cal_sample["reference_notional"],
        **calibration_predictions,
    )
    (destination / "diagnostics.json").write_text(_json(audit) + "\n", encoding="utf-8")
    if progress:
        progress(
            {"phase": "saving_model", "family": bundle.family, "status": bundle.audit["status"]}
        )
    _save_block(bundle, destination, X_cal)
    return bundle


def _save_block(bundle, destination, reload_features):
    payload = io.BytesIO()
    joblib.dump(bundle, payload, compress=3)
    (destination / "model.joblib").write_bytes(payload.getvalue())
    files = (
        "attempt.json",
        "samples.json",
        "diagnostics.json",
        "calibration-predictions.npz",
        "model.joblib",
    )
    manifest = {
        "schema_version": SCHEMA,
        "runtime": _runtime(),
        "files": {name: _digest((destination / name).read_bytes()) for name in files},
        "code_sha256": _digest(Path(__file__).read_bytes()),
        "status": bundle.audit["status"],
        "family": bundle.family,
        "feature_count": bundle.feature_count,
        "feature_names": bundle.audit["attempt"]["feature_names"],
        "head_names": list(HEAD_NAMES),
    }
    path = destination / "manifest.json"
    path.write_text(_json(manifest) + "\n", encoding="utf-8")
    loaded, _ = load_conditional_block(destination)
    expected, actual = (
        predict_conditional(bundle, reload_features),
        predict_conditional(loaded, reload_features),
    )
    if not all(np.array_equal(expected[key], actual[key], equal_nan=True) for key in expected):
        raise ValueError("Saved conditional forecasts differ on reload")
    manifest["reload_check"] = {
        "exact_equal": True,
        "rows": len(reload_features),
        "availability": bundle.available,
        "arrays": ["raw", "corrected"],
    }
    path.write_text(_json(manifest) + "\n", encoding="utf-8")


def load_conditional_block(directory):
    """Verify trusted local block bytes before joblib deserialization."""
    source = Path(directory)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA or manifest.get("runtime") != _runtime():
        raise ValueError("Conditional artifact schema/runtime is incompatible")
    files = (
        "attempt.json",
        "samples.json",
        "diagnostics.json",
        "calibration-predictions.npz",
        "model.joblib",
    )
    if set(manifest.get("files", {})) != set(files):
        raise ValueError("Conditional artifact file set is incompatible")
    raw = {}
    for name in files:
        raw[name] = (source / name).read_bytes()
        if _digest(raw[name]) != manifest["files"][name]:
            raise ValueError(f"Conditional artifact integrity failed: {name}")
    bundle = joblib.load(io.BytesIO(raw["model.joblib"]))
    if not isinstance(bundle, FittedConditional):
        raise ValueError("Conditional artifact payload type is incompatible")
    if (
        manifest.get("head_names") != list(HEAD_NAMES)
        or manifest.get("feature_count") != bundle.feature_count
        or manifest.get("feature_names") != bundle.audit["attempt"]["feature_names"]
        or manifest.get("family") != bundle.family
        or manifest.get("status") != bundle.audit["status"]
        or bundle.bias.shape != (6,)
        or not np.isfinite(bundle.bias).all()
    ):
        raise ValueError("Conditional artifact payload metadata is incompatible")
    if _json(bundle.audit) != _json(json.loads(raw["diagnostics.json"])):
        raise ValueError("Conditional artifact diagnostics do not match payload")
    return bundle, manifest
