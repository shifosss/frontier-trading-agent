"""Train-only multi-output models and chronological calibration for research.

The caller owns chronological splits, outcome purging and row sampling. This module
never fits preprocessing or models to calibration/test observations. Calibration
weights are pooled predictive-error diagnostics, not evidence of a tradable edge.
"""

import warnings
from copy import deepcopy
from dataclasses import dataclass

import numpy as np
import sklearn
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

BASE_MODEL_NAMES = ("ridge", "extra_trees", "hist_gradient_boosting", "multi_head_mlp")
MODEL_NAMES = BASE_MODEL_NAMES + ("equal_ensemble", "calibrated_ensemble")
PREDICTION_BATCH_SIZE = 65_536
HEAD_NAMES = ("return_1", "return_3", "return_5", "downside_1", "downside_3", "downside_5")
MODEL_CONFIG = {
    "ridge": {"alpha": 100.0},
    "extra_trees": {
        "n_estimators": 48,
        "max_depth": 8,
        "min_samples_leaf": 64,
        "max_features": 0.8,
        "n_jobs": 2,
    },
    "hist_gradient_boosting": {
        "max_iter": 60,
        "max_leaf_nodes": 15,
        "learning_rate": 0.05,
        "l2_regularization": 10.0,
        "min_samples_leaf": 64,
        "early_stopping": False,
    },
    "multi_head_mlp": {
        "hidden_layer_sizes": (32, 16),
        "activation": "relu",
        "solver": "adam",
        "alpha": 0.0001,
        "batch_size": "auto",
        "learning_rate_init": 0.001,
        "max_iter": 60,
        "shuffle": True,
        "early_stopping": False,
        "tol": 0.0001,
        "n_iter_no_change": 10,
    },
}
CONFIG = {
    "version": "multi-output-ensemble-v1",
    "head_names": HEAD_NAMES,
    "models": MODEL_CONFIG,
    "extra_trees_prediction_n_jobs": 1,
    "boosting_wrapper": {"class": "MultiOutputRegressor", "n_jobs": 1},
    "feature_imputation": "training median, missing indicators, retain empty features",
    "feature_scaling": "training StandardScaler for ridge and multi_head_mlp",
    "target_scaling": "training StandardScaler for multi_head_mlp only",
    "calibration": "positive return-MSE improvement over training-mean baseline",
    "risk_weights": "same horizon weights as return head",
    "no_improvement": "equal weights; not a qualification decision",
    "prediction_clipping": "downside heads at zero only; return heads unbounded",
    "thread_limit": 2,
    "prediction_batch_size": PREDICTION_BATCH_SIZE,
}


def _features(value, name):
    values = np.asarray(value)
    if not np.issubdtype(values.dtype, np.floating):
        values = values.astype(float)
    if values.ndim != 2 or values.shape[1] == 0:
        raise ValueError(f"{name} must be a two-dimensional matrix with features")
    for start in range(0, len(values), PREDICTION_BATCH_SIZE):
        if np.isinf(values[start : start + PREDICTION_BATCH_SIZE]).any():
            raise ValueError(f"{name} contains infinite features")
    return values


def _targets(value, row_count, name):
    values = np.asarray(value, dtype=float)
    if values.shape != (row_count, len(HEAD_NAMES)) or not np.isfinite(values).all():
        raise ValueError(f"{name} must contain {row_count} finite rows and six target heads")
    if (values[:, 3:] < 0).any():
        raise ValueError(f"{name} downside target magnitudes must be nonnegative")
    return values


def _prediction(model, features, target_scaler=None):
    if len(features) == 0:
        return np.empty((0, len(HEAD_NAMES)), dtype=float)
    values = model.predict(features)
    if target_scaler is not None:
        values = target_scaler.inverse_transform(values)
    values = np.asarray(values, dtype=float)
    if values.shape != (len(features), len(HEAD_NAMES)) or not np.isfinite(values).all():
        raise ValueError("Model returned invalid six-head predictions")
    values[:, 3:] = np.maximum(values[:, 3:], 0.0)
    return values


def _calibration(y_train, y_cal, predictions):
    baseline = y_train.mean(axis=0)
    baseline_mse = np.mean(np.square(y_cal - baseline), axis=0)
    model_mse = np.array(
        [np.mean(np.square(y_cal - predictions[name]), axis=0) for name in BASE_MODEL_NAMES]
    )
    improvements = np.maximum(baseline_mse[:3] - model_mse[:, :3], 0.0)
    weights = np.full((len(BASE_MODEL_NAMES), 3), 1.0 / len(BASE_MODEL_NAMES))
    totals = improvements.sum(axis=0)
    improved = totals > 0
    weights[:, improved] = improvements[:, improved] / totals[improved]
    audit = {
        "row_count": len(y_cal),
        "metric": "pooled_per_row_mse",
        "interpretation": "Rows are not independent; this is not significance or qualification.",
        "training_target_mean": baseline.tolist(),
        "baseline_mse": baseline_mse.tolist(),
        "model_mse": {
            name: model_mse[index].tolist() for index, name in enumerate(BASE_MODEL_NAMES)
        },
        "horizons": {
            str(horizon): {
                "weights": dict(zip(BASE_MODEL_NAMES, weights[:, head].tolist(), strict=True)),
                "positive_mse_improvement": dict(
                    zip(BASE_MODEL_NAMES, improvements[:, head].tolist(), strict=True)
                ),
                "equal_weight_fallback": bool(not improved[head]),
            }
            for head, horizon in enumerate((1, 3, 5))
        },
    }
    return weights, audit


@dataclass
class FittedHeads:
    """Fitted train-only preprocessing, models and chronological ensemble weights."""

    imputer: SimpleImputer
    feature_scaler: StandardScaler
    target_scaler: StandardScaler
    models: dict
    weights: np.ndarray
    feature_count: int
    audit: dict


def fit_heads(X_train, y_train, X_cal, y_cal, *, seed=1729):
    """Fit four six-output models and calibrate using the separate calibration rows."""
    X_train = _features(X_train, "X_train")
    X_cal = _features(X_cal, "X_cal")
    if not len(X_train) or not len(X_cal):
        raise ValueError("Training and calibration matrices must contain rows")
    if X_cal.shape[1] != X_train.shape[1]:
        raise ValueError("All feature matrices must have the same column count")
    y_train = _targets(y_train, len(X_train), "y_train")
    y_cal = _targets(y_cal, len(X_cal), "y_cal")

    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    train_imputed = imputer.fit_transform(X_train)
    cal_imputed = imputer.transform(X_cal)
    feature_scaler = StandardScaler().fit(train_imputed)
    target_scaler = StandardScaler().fit(y_train)
    train_scaled = feature_scaler.transform(train_imputed)
    cal_scaled = feature_scaler.transform(cal_imputed)
    models = {
        "ridge": Ridge(**MODEL_CONFIG["ridge"]),
        "extra_trees": ExtraTreesRegressor(**MODEL_CONFIG["extra_trees"], random_state=seed),
        "hist_gradient_boosting": MultiOutputRegressor(
            HistGradientBoostingRegressor(
                **MODEL_CONFIG["hist_gradient_boosting"], random_state=seed
            ),
            n_jobs=1,
        ),
        "multi_head_mlp": MLPRegressor(**MODEL_CONFIG["multi_head_mlp"], random_state=seed),
    }
    cal_predictions, model_audit, warning_records = {}, {}, []
    with threadpool_limits(limits=CONFIG["thread_limit"]):
        for name, model in models.items():
            tree_model = name in {"extra_trees", "hist_gradient_boosting"}
            train, cal = (train_imputed, cal_imputed) if tree_model else (train_scaled, cal_scaled)
            scaler = target_scaler if name == "multi_head_mlp" else None
            targets = scaler.transform(y_train) if scaler is not None else y_train
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model.fit(train, targets)
                if name == "extra_trees":
                    # Fixed estimator reduction order for calibration and saved inference.
                    model.set_params(n_jobs=CONFIG["extra_trees_prediction_n_jobs"])
                cal_predictions[name] = _prediction(model, cal, scaler)
            warning_records.extend(
                {
                    "model": name,
                    "category": item.category.__name__,
                    "message": str(item.message),
                }
                for item in caught
            )
            model_audit[name] = {
                "training_rows": len(train),
                "outputs": len(HEAD_NAMES),
                "convergence_warning": any(
                    issubclass(item.category, ConvergenceWarning) for item in caught
                ),
            }
            if name == "extra_trees":
                model_audit[name].update(
                    {
                        "fit_n_jobs": MODEL_CONFIG["extra_trees"]["n_jobs"],
                        "predict_n_jobs": model.n_jobs,
                    }
                )
            if name == "hist_gradient_boosting":
                model_audit[name].update(
                    {
                        "independent_target_estimators": len(model.estimators_),
                        "iterations_per_target": [
                            int(estimator.n_iter_) for estimator in model.estimators_
                        ],
                    }
                )
            if name == "multi_head_mlp":
                model_audit[name].update(
                    {
                        "iterations": int(model.n_iter_),
                        "scaled_training_loss": float(model.loss_),
                        "weight_shapes": [list(layer.shape) for layer in model.coefs_],
                    }
                )

    weights, calibration = _calibration(y_train, y_cal, cal_predictions)
    config = deepcopy(CONFIG)
    config.update({"seed": seed, "sklearn_version": sklearn.__version__})
    audit = {
        "calibration": calibration,
        "warnings": warning_records,
        "config": config,
        "model_audit": model_audit,
        "preprocessing": {
            "fitted_rows": len(X_train),
            "feature_medians": imputer.statistics_.tolist(),
            "missing_indicator_features": imputer.indicator_.features_.tolist(),
            "feature_mean": feature_scaler.mean_.tolist(),
            "feature_scale": feature_scaler.scale_.tolist(),
            "target_mean": target_scaler.mean_.tolist(),
            "target_scale": target_scaler.scale_.tolist(),
        },
    }

    return FittedHeads(
        imputer, feature_scaler, target_scaler, models, weights, X_train.shape[1], audit
    )


def predict_heads(bundle, X):
    """Predict all six declared outputs without fitting any state; empty rows are valid."""
    X = _features(X, "X")
    if X.shape[1] != bundle.feature_count:
        raise ValueError("All feature matrices must have the same column count")
    predictions = {}
    with threadpool_limits(limits=CONFIG["thread_limit"]):
        for name in BASE_MODEL_NAMES:
            tree_model = name in {"extra_trees", "hist_gradient_boosting"}
            scaler = bundle.target_scaler if name == "multi_head_mlp" else None
            predicted = np.empty((len(X), len(HEAD_NAMES)), dtype=float)
            for start in range(0, len(X), PREDICTION_BATCH_SIZE):
                stop = start + PREDICTION_BATCH_SIZE
                features = bundle.imputer.transform(X[start:stop])
                if not tree_model:
                    features = bundle.feature_scaler.transform(features)
                predicted[start:stop] = _prediction(bundle.models[name], features, scaler)
            predictions[name] = predicted
    stacked = np.stack([predictions[name] for name in BASE_MODEL_NAMES], axis=0)
    predictions["equal_ensemble"] = stacked.mean(axis=0)
    paired_weights = np.concatenate((bundle.weights, bundle.weights), axis=1)
    predictions["calibrated_ensemble"] = (stacked * paired_weights[:, None, :]).sum(axis=0)
    return predictions


def fit_predict_heads(X_train, y_train, X_cal, y_cal, X_test, *, seed=1729):
    """Legacy fit/predict interface with unchanged prediction and audit structure."""
    X_test = _features(X_test, "X_test")
    X_train = _features(X_train, "X_train")
    if X_test.shape[1] != X_train.shape[1]:
        raise ValueError("All feature matrices must have the same column count")
    bundle = fit_heads(X_train, y_train, X_cal, y_cal, seed=seed)
    return {"predictions": predict_heads(bundle, X_test), **bundle.audit}
