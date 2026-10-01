"""Fixed two-output earnings models; labels never enter the forecast interface."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import io
import json
import uuid
import warnings

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from frontier import conditional_models as shared
from frontier import ensemble_models

SPEC_PATH = Path(__file__).resolve().parents[1] / "cohort/model-specification.json"
SPEC_SHA256 = "7e837043e034305fe3aa15aefd3d28d8389f63e923fc7ef0739d1883e8a30ffb"
SCHEMA = "earnings-two-output-v1"
FAMILIES = ("ridge", "hist_gradient_boosting")
FEATURE_NAMES = (
    "S", "Q", "prior_relative_return_5",
    "prior_dollar_activity_ratio_20", "prior_spy_sma200_distance",
)
HEAD_NAMES = ("return_5", "downside_5")
EASTERN = ZoneInfo("America/New_York")


def _identity(value):
    return shared._digest(shared._json(value).encode("utf-8"))


def _code_identity():
    return {
        "adapter": shared._digest(Path(__file__).read_bytes()),
        "shared_fit_module": shared._digest(Path(shared.__file__).read_bytes()),
        "preset_module": shared._digest(Path(ensemble_models.__file__).read_bytes()),
    }


def specification():
    raw = SPEC_PATH.read_bytes()
    if shared._digest(raw) != SPEC_SHA256:
        raise ValueError("The predeclared model specification changed")
    spec = json.loads(raw)
    for family in FAMILIES:
        expected = dict(spec["models"][family])
        expected.pop("random_state", None)
        if expected != shared.MODEL_CONFIG[family]:
            raise ValueError(f"Shared {family} preset differs from the frozen specification")
    return spec


def _decision(row):
    try:
        value = datetime.fromisoformat(row["decision_timestamp"])
        if value.utcoffset() is None:
            raise ValueError("Decision timestamp lacks a UTC offset")
        value = value.astimezone(EASTERN)
        if (value.hour, value.minute, value.second, value.microsecond) != (9, 0, 0, 0):
            raise ValueError("Decision timestamp is not 09:00 Eastern")
        return value
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid decision clock: {error}") from error


def _inputs(row):
    values = np.asarray(row.get("model_inputs"), dtype=float)
    if values.shape != (5,) or not np.isfinite(values).all():
        raise ValueError("All five causal inputs must be finite")
    return values


def _target(label):
    if label is None or label.get("status") != "qualified":
        raise ValueError("Unavailable joint label")
    values = np.asarray(label.get("targets"), dtype=float)
    if values.shape != (2,) or not np.isfinite(values).all():
        raise ValueError("Both target heads must be finite")
    if values[0] <= -1 or not 0 <= values[1] < 1:
        raise ValueError("Targets cannot arise from finite positive entry and follow-up closes")
    return values


def _partition(rows, labels, fold, sessions):
    if not sessions or sessions != sorted(set(sessions)):
        raise ValueError("Calendar sessions must be ordered and unique")
    for day in sessions:
        if datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
            raise ValueError("Calendar sessions must be ISO dates")
    session_set = set(sessions)
    boundaries = {
        "fit": next((s for s in sessions if int(s[:4]) == fold["calibration_decision_year"]), None),
        "calibration": next((s for s in sessions if int(s[:4]) == fold["test_decision_year"]), None),
    }
    if None in boundaries.values():
        raise ValueError("Calendar does not supply both purging boundaries")
    groups = {"fit": [], "calibration": [], "test": []}
    records = []
    ids = set()
    for row in rows:
        event_id = row["event_id"]
        cik = row["cik"]
        if not isinstance(event_id, str) or not event_id or event_id in ids:
            raise ValueError("Every original event needs a unique nonempty event_id")
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isascii() or not cik.isdigit():
            raise ValueError("CIK must be a zero-padded ten-digit string")
        ids.add(event_id)
        record = {
            "event_id": event_id, "cik": cik, "row_sha256": _identity(row),
            "partition": "unassigned", "status": "unavailable", "reasons": [],
        }
        records.append(record)
        try:
            decision = _decision(row)
        except ValueError as error:
            record["reasons"].append(str(error))
            continue
        year = decision.year
        part = ("fit" if year in fold["fit_decision_years"] else
                "calibration" if year == fold["calibration_decision_year"] else
                "test" if year == fold["test_decision_year"] else "outside")
        record.update(partition=part, decision_timestamp=row["decision_timestamp"])
        if part == "outside":
            record.update(status="outside", reasons=["Decision year is outside this fold"])
            continue
        if row.get("model_input_status") != "qualified":
            record["reasons"] = ["Causal input population unavailable", *row.get("model_input_reasons", [])]
            continue
        try:
            X = _inputs(row)
            if decision.date().isoformat() not in session_set:
                raise ValueError("Decision date is not in the supplied exchange calendar")
            end = row.get("planned_label_end_session")
            if end not in session_set or end <= decision.date().isoformat():
                raise ValueError("Planned label end must be a later exchange session")
        except (TypeError, ValueError) as error:
            record["reasons"].append(str(error))
            continue
        record["planned_label_end_session"] = end
        if part != "test" and end >= boundaries[part]:
            record.update(status="purged", reasons=["Label end reaches the next partition"])
            continue
        if part == "test":
            record["status"] = "eligible"
            groups[part].append((row, X, None))
            continue
        # Outcome lookup occurs only after causal qualification and purging.
        label = labels.get(event_id)
        record["label_sha256"] = _identity(label)
        try:
            y = _target(label)
        except (TypeError, ValueError) as error:
            record["reasons"] = [str(error), *(label or {}).get("reasons", [])]
            continue
        record["status"] = "retained"
        groups[part].append((row, X, y))
    for group in groups.values():
        group.sort(key=lambda item: (_decision(item[0]), item[0]["cik"],
                                     item[0].get("accession", item[0]["event_id"])))
    return groups, records, boundaries


def _raw_predict(model, X):
    with threadpool_limits(limits=2):
        raw = np.asarray(model.predict(X), dtype=float)
    if raw.shape != (len(X), 2):
        raise ValueError(f"Expected n-by-2 model output, received {raw.shape}")
    return raw


def _layers(raw, bias):
    uncalibrated = raw.copy()
    uncalibrated[:, 1] = np.maximum(0, uncalibrated[:, 1])
    corrected = uncalibrated + bias
    corrected[:, 1] = np.maximum(0, corrected[:, 1])
    return uncalibrated, corrected


def _quantile_edges(values):
    # Interior cutpoints only; constant predictions have one bin.
    return [
        sorted(set(float(v) for v in np.quantile(head, [0.2, 0.4, 0.6, 0.8])
                   if head.min() < v < head.max()))
        for head in values.T
    ]


@dataclass
class FittedEarnings:
    model: object
    family: str
    bias: np.ndarray
    training_mean: np.ndarray | None
    quantile_edges: dict
    audit: dict
    rows: list

    @property
    def available(self):
        return self.model is not None and self.audit["status"] == "complete"


def fit_family_fold(family, rows, labels, fold, calendar_sessions):
    """Fit one declared family/year once, using only purged fit/calibration labels."""
    spec = specification()
    if family not in FAMILIES or fold not in spec["chronology"]["folds"]:
        raise ValueError("Family and fold must be exactly predeclared")
    rows = deepcopy(list(rows))
    groups, records, boundaries = _partition(rows, labels, fold, calendar_sessions)
    samples = {}
    for name, group in groups.items():
        samples[name] = {
            "event_ids": [item[0]["event_id"] for item in group],
            "rows": len(group), "distinct_ciks": len({item[0]["cik"] for item in group}),
        }
        if name != "test":
            samples[name].update(
                X=[item[1].tolist() for item in group],
                targets=[item[2].tolist() for item in group],
            )
    audit = {
        "schema": SCHEMA, "attempt_id": uuid.uuid4().hex, "family": family,
        "status": "unavailable", "fold": deepcopy(fold), "boundaries": boundaries,
        "specification_sha256": SPEC_SHA256, "rows_sha256": _identity(rows),
        "calendar_sha256": _identity(calendar_sessions), "feature_names": list(FEATURE_NAMES),
        "head_names": list(HEAD_NAMES), "samples": samples, "row_dispositions": records,
        "warnings": [], "reasons": [], "calibration": None, "preprocessing": None,
        "code_sha256": _code_identity(),
        "runtime": shared._runtime(),
    }
    bundle = FittedEarnings(None, family, np.zeros(2), None, {}, audit, rows)
    for name, minimum in (("fit", spec["chronology"]["minimum_fit"]),
                          ("calibration", spec["chronology"]["minimum_calibration"])):
        sample = samples[name]
        if (sample["rows"] < minimum["rows_after_purge_and_joint_label_validation"]
                or sample["distinct_ciks"] < minimum["distinct_CIKs"]):
            audit["reasons"].append(f"{name} sample below fixed row/issuer minimum")
    if audit["reasons"]:
        audit["status"] = "insufficient_sample"
        return bundle
    X = np.asarray(samples["fit"]["X"], dtype=float)
    y = np.asarray(samples["fit"]["targets"], dtype=float)
    X_cal = np.asarray(samples["calibration"]["X"], dtype=float)
    y_cal = np.asarray(samples["calibration"]["targets"], dtype=float)
    bundle.training_mean = y.mean(axis=0)
    audit["training_mean"] = bundle.training_mean.tolist()
    caught = []
    stage = "fit"
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = shared._fit_family(family, X, y, spec["models"]["seed"])
            bundle.model = model  # Keep a fitted model even if its calibration later fails.
            audit["preprocessing"] = shared._preprocessing(model)
            stage = "calibration"
            raw = _raw_predict(model, X_cal)
            audit["calibration"] = {"raw": [_visible(row) for row in raw]}
            if not np.isfinite(raw).all():
                raise ValueError("Calibration model predictions are not all finite")
            uncalibrated, _ = _layers(raw, np.zeros(2))
            bias = np.mean(y_cal - uncalibrated, axis=0)
            uncalibrated, corrected = _layers(raw, bias)
            if not np.isfinite(bias).all() or not np.isfinite(corrected).all():
                raise ValueError("Calibration correction is not finite")
        bundle.bias = bias
        bundle.quantile_edges = {"raw": _quantile_edges(raw), "corrected": _quantile_edges(corrected)}
        audit.update(status="complete", training_mean=bundle.training_mean.tolist())
        audit["calibration"] = {
            "bias": bias.tolist(), "raw": raw.tolist(), "uncalibrated": uncalibrated.tolist(),
            "corrected": corrected.tolist(), "quantile_edges": bundle.quantile_edges,
            "bin_assignment": "searchsorted(interior_edges, value, side=right); bins are zero-based",
            "interpretation": "Calibration error is fitted, not held-out performance",
        }
    except Exception as error:
        audit.update(status="failed", failed_stage=stage,
                     error_type=type(error).__name__, error=str(error))
    finally:
        audit["warnings"] = [{"category": item.category.__name__, "message": str(item.message)}
                             for item in caught]
    return bundle


def fit_fold(rows, labels, fold, calendar_sessions):
    """Both frozen families; no family selection, capital input or fee input."""
    return {family: fit_family_fold(family, rows, labels, fold, calendar_sessions)
            for family in FAMILIES}


def _visible(values):
    return [float(v) if np.isfinite(v) else str(float(v)) for v in values]


def predict_events(bundle, rows):
    """Forecast the fold's causal test events. This interface accepts no outcomes."""
    dispositions = {row["event_id"]: row for row in bundle.audit["row_dispositions"]}
    prepared = [(row, _identity(row)) for row in rows]
    if len({row["event_id"] for row, _ in prepared}) != len(prepared):
        raise ValueError("Prediction rows contain duplicate event identities")
    if any(dispositions.get(row["event_id"], {}).get("row_sha256") != digest for row, digest in prepared):
        raise ValueError("Prediction row differs from the saved historical source row")
    result = {"family": bundle.family, "test_decision_year": bundle.audit["fold"]["test_decision_year"],
              "model_attempt_id": bundle.audit["attempt_id"], "forecasts": [], "warnings": []}
    eligible, indices = [], []
    for row, digest in prepared:
        record = {"event_id": row["event_id"], "cik": row["cik"], "prepared_row_sha256": digest,
                  "status": "unavailable",
                  "reasons": [], "raw": None, "uncalibrated": None, "corrected": None}
        result["forecasts"].append(record)
        source = dispositions[row["event_id"]]
        if source["partition"] != "test" or source["status"] != "eligible":
            record["reasons"] = deepcopy(source["reasons"]) or ["Event is outside the model's eligible test population"]
            continue
        if not bundle.available:
            record["reasons"] = [f"Fold model unavailable: {bundle.audit['status']}"]
            continue
        eligible.append(_inputs(row))
        indices.append(len(result["forecasts"]) - 1)
    if not eligible:
        return result
    caught = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            raw = _raw_predict(bundle.model, np.asarray(eligible))
            uncalibrated, corrected = _layers(raw, bundle.bias)
        for j, index in enumerate(indices):
            record = result["forecasts"][index]
            record.update(raw=_visible(raw[j]), uncalibrated=_visible(uncalibrated[j]),
                          corrected=_visible(corrected[j]))
            if not np.isfinite(raw[j]).all() or not np.isfinite(corrected[j]).all():
                record["reasons"] = ["Nonfinite model forecast"]
            elif corrected[j, 0] <= -1:
                record["reasons"] = ["Corrected return is invalid for cash utility planning"]
            else:
                record.update(status="predicted", quantile_bins={
                    layer: [int(np.searchsorted(bundle.quantile_edges[layer][head], values[j, head], side="right"))
                            for head in range(2)]
                    for layer, values in (("raw", raw), ("corrected", corrected))
                })
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error))
        for index in indices:
            result["forecasts"][index]["reasons"] = [f"Prediction failed: {type(error).__name__}: {error}"]
    finally:
        result["warnings"] = [{"category": item.category.__name__, "message": str(item.message)}
                              for item in caught]
    return result


def save_bundle(bundle, directory):
    """Create a new immutable local model artifact; verify exact calibration reload."""
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=False)
    metadata = {"family": bundle.family, "bias": bundle.bias.tolist(),
                "training_mean": None if bundle.training_mean is None else bundle.training_mean.tolist(),
                "quantile_edges": bundle.quantile_edges, "audit": bundle.audit}
    payload = io.BytesIO()
    joblib.dump(bundle.model, payload, compress=3)
    files = {"model.joblib": payload.getvalue(),
             "metadata.json": (shared._json(metadata) + "\n").encode("utf-8"),
             "source-rows.json": (shared._json(bundle.rows) + "\n").encode("utf-8")}
    for name, raw in files.items():
        (destination / name).write_bytes(raw)
    manifest = {"schema": SCHEMA, "runtime": shared._runtime(),
                "files": {name: shared._digest(raw) for name, raw in files.items()},
                "specification_sha256": SPEC_SHA256,
                "code_sha256": bundle.audit["code_sha256"]}
    (destination / "manifest.json").write_text(shared._json(manifest) + "\n", encoding="utf-8")
    loaded = load_bundle(destination)
    if bundle.available:
        X_cal = np.asarray(bundle.audit["samples"]["calibration"]["X"])
        expected = np.asarray(bundle.audit["calibration"]["raw"])
        actual = _raw_predict(loaded.model, X_cal)
        if not np.array_equal(expected, actual):
            raise ValueError("Reloaded two-output calibration forecasts differ")
    manifest["reload_check"] = {"exact_equal": True, "rows": bundle.audit["samples"]["calibration"]["rows"]
                                if bundle.available else 0, "available": bundle.available}
    (destination / "manifest.json").write_text(shared._json(manifest) + "\n", encoding="utf-8")
    return manifest


def load_bundle(directory):
    """Verify trusted local artifact bytes before deserializing its sklearn model."""
    specification()
    source = Path(directory)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["schema"] != SCHEMA or manifest["runtime"] != shared._runtime()
            or manifest["specification_sha256"] != SPEC_SHA256
            or manifest["code_sha256"] != _code_identity()):
        raise ValueError("Model artifact schema, runtime, code or specification is incompatible")
    if set(manifest["files"]) != {"model.joblib", "metadata.json", "source-rows.json"}:
        raise ValueError("Model artifact file set is incompatible")
    raw = {name: (source / name).read_bytes() for name in manifest["files"]}
    if any(shared._digest(value) != manifest["files"][name] for name, value in raw.items()):
        raise ValueError("Model artifact integrity failed")
    metadata, rows = json.loads(raw["metadata.json"]), json.loads(raw["source-rows.json"])
    if (_identity(rows) != metadata["audit"]["rows_sha256"]
            or metadata["audit"]["code_sha256"] != manifest["code_sha256"]):
        raise ValueError("Saved row or implementation identity differs")
    return FittedEarnings(joblib.load(io.BytesIO(raw["model.joblib"])), metadata["family"],
                          np.asarray(metadata["bias"], dtype=float),
                          None if metadata["training_mean"] is None else np.asarray(metadata["training_mean"]),
                          metadata["quantile_edges"], metadata["audit"], rows)
