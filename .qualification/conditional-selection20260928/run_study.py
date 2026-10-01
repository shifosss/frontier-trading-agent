"""Frozen conditional strategy comparison; offline research, never a broker transport."""
import gc
import hashlib
import json
import math
import os
import sqlite3
import traceback
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np

from frontier.conditional_features import FEATURE_NAMES, SETUP_NAMES, build_context, gather_rows
from frontier.conditional_models import (
    CALIBRATION_SESSIONS,
    FAMILIES,
    FIT_SESSIONS,
    INNER_PREFIXES,
    INNER_VALIDATION,
    fit_conditional_block,
    load_conditional_block,
    predict_conditional,
    sample_conditional_rows,
)
from frontier.conditional_policy import ConditionalPolicy
from frontier.ensemble_models import HEAD_NAMES, MODEL_CONFIG
from frontier.execution_costs import get_cost_profile
from frontier.historical_study import _metrics
from frontier.short_horizon_study import _simulate_daily, _summarize

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PREP = ROOT / "preparation"
POLICIES = ("static_setup_rank", "conditional_net_fraction", "conditional_net_dollars")
BATCH = 32768


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_result(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Completed result differs; preserve the previous artifact: {path}")
    else:
        save(path, value)


def status(phase, **details):
    item = dict(phase=phase, pid=os.getpid(), updated_at=datetime.now(timezone.utc).isoformat(), **details)
    save(ROOT / "status.json", item)
    print(json.dumps(item), flush=True)


def verify_files(root, files):
    for name, expected in files.items():
        if sha(root / name) != expected:
            raise ValueError(f"Frozen artifact changed: {name}")


def validate_definition(check_cache=True):
    request, definition = read(ROOT / "request.json"), read(ROOT / "definition.json")
    verify_files(REPO, definition["files"])
    for name, expected in definition["dependencies"].items():
        if version(name) != expected:
            raise ValueError(f"Frozen dependency changed: {name}")
    identities = {
        "request_sha256": ROOT / "request.json",
        "preparation_definition_sha256": PREP / "definition.json",
        "coverage_preflight_sha256": PREP / "coverage-preflight.json",
    }
    if check_cache:
        identities["preparation_cache_sha256"] = PREP / "market-features.joblib"
    for key, path in identities.items():
        if definition[key] != sha(path):
            raise ValueError(f"Frozen input changed: {key}")
    manifest, preparation = read(PREP / "cache-manifest.json"), read(PREP / "definition.json")
    if manifest["sha256"] != definition["preparation_cache_sha256"]:
        raise ValueError("Preparation cache manifest does not match the experiment")
    if manifest["definition_sha256"] != definition["preparation_definition_sha256"]:
        raise ValueError("Preparation definition does not match the cache")
    if read(PREP / "status.json")["phase"] != "complete":
        raise ValueError("Data preparation is not complete")
    if not read(PREP / "coverage-preflight.json")["passed"]:
        raise ValueError("Historical coverage preflight failed")
    for key in ("source_run_id", "history_start", "first_signal", "last_session"):
        if request[key] != preparation[key]:
            raise ValueError(f"Experiment/preparation mismatch: {key}")
    if (request["policies"] != list(POLICIES) or request["holding_sessions"] != [1, 3, 5]
            or request["cost_profiles"] != ["proportional", "moomoo_ca_us"]
            or request["capital_usd"] != 2000 or request["round_trip_bps"] != 40
            or request["planned_accounts"] != 18 or request["fallback_policy"] != "abstain"
            or request["feature_names"] != list(FEATURE_NAMES)
            or request["head_names"] != list(HEAD_NAMES)
            or request["setup_names"] != list(SETUP_NAMES)):
        raise ValueError("Request differs from the implemented conditional comparison")
    learning = request["learning"]
    if (learning["families"] != {name: MODEL_CONFIG[name] for name in FAMILIES}
            or learning["fitting_sessions"] != FIT_SESSIONS
            or learning["calibration_sessions"] != CALIBRATION_SESSIONS
            or learning["test_sessions"] != 252
            or learning["inner_prefixes"] != list(INNER_PREFIXES)
            or learning["inner_validation_sessions"] != INNER_VALIDATION
            or learning["sample_limit_per_date"] != 96):
        raise ValueError("Declared learner or window parameters differ from the implementation")
    return request, definition


def forecast_candidates(bundle, features, context, start, end, progress=None):
    """Retain every eligible stock/date, including unknown future outcomes."""
    rows, columns = np.nonzero(context["eligible"][start:end + 1])
    rows = rows + start
    result = {"rows": rows, "columns": columns, "raw": np.full((len(rows), 6), np.nan),
              "corrected": np.full((len(rows), 6), np.nan), "invalid_feature": np.zeros(len(rows), dtype=bool)}
    for first in range(0, len(rows), BATCH):
        last = min(first + BATCH, len(rows))
        X = gather_rows(features, context, rows[first:last], columns[first:last])
        valid = ~np.isinf(X).any(axis=1)
        result["invalid_feature"][first:last] = ~valid
        if valid.any():
            predictions = predict_conditional(bundle, X[valid])
            selected = np.flatnonzero(valid) + first
            for key in ("raw", "corrected"):
                result[key][selected] = predictions[key]
        if progress:
            progress(completed=last, total=len(rows))
    return result


def setup_means(sample):
    memberships = sample["X"][:, 27:30] > 0
    pooled = sample["y"].mean(axis=0) if len(sample["y"]) else np.full(6, np.nan)
    counts = memberships.sum(axis=0).tolist()
    means = np.array([sample["y"][memberships[:, i]].mean(axis=0) if counts[i] else pooled for i in range(3)])
    return means, counts


def setup_baseline(memberships, means):
    counts = memberships.sum(axis=1)
    result = np.full((len(memberships), 6), np.nan)
    for index in range(3):
        selected = memberships[:, index]
        # Avoid 0*NaN contaminating a row belonging only to another available setup.
        for head in range(6):
            if np.isfinite(means[index, head]):
                unset = selected & np.isnan(result[:, head])
                result[unset, head] = 0.0
                result[selected, head] += means[index, head]
    return result / counts[:, None]


def forecast_diagnostics(predictions, targets, baseline, calibration):
    """Per-head row-weighted diagnostics, with fixed calibration-defined bins."""
    output = {"weighting": "one candidate row per head; descriptive overlapping observations, not account returns"}
    for key in ("raw", "corrected"):
        output[key] = []
        for head in range(6):
            pred, target = predictions[key][:, head], targets[:, head]
            cal = calibration[key][:, head]
            cal = cal[np.isfinite(cal)]
            edges = np.unique(np.quantile(cal, [.2, .4, .6, .8])) if len(cal) else np.array([])
            finite_prediction, finite_target = np.isfinite(pred), np.isfinite(target)
            paired = finite_prediction & finite_target
            assignments = np.searchsorted(edges, pred, side="right")
            bins = []
            for index in range(len(edges) + 1):
                members = finite_prediction & (assignments == index)
                known = members & finite_target
                bins.append({"bin": index, "predictions": int(members.sum()), "paired_count": int(known.sum()),
                             "missing_target": int((members & ~finite_target).sum()),
                             "mean_forecast": float(pred[known].mean()) if known.any() else None,
                             "mean_target": float(target[known].mean()) if known.any() else None})
            compare = paired & np.isfinite(baseline[:, head])
            output[key].append({"head": HEAD_NAMES[head], "candidates": len(pred),
                                "finite_predictions": int(finite_prediction.sum()), "missing_target": int((~finite_target).sum()),
                                "paired_count": int(paired.sum()), "calibration_edges": edges.tolist(),
                                "calibration_predictions": len(cal), "bins": bins,
                                "paired_baseline_count": int(compare.sum()),
                                "forecast_mse": float(np.square(pred[compare] - target[compare]).mean()) if compare.any() else None,
                                "setup_baseline_mse": float(np.square(baseline[compare, head] - target[compare]).mean()) if compare.any() else None})
    return output


def run_block(number, bounds, market, features, context, request, definition_sha):
    pointer = ROOT / "blocks" / f"block-{number:03}.json"
    if pointer.exists():
        manifest = read(pointer)
        if manifest["definition_sha256"] != definition_sha or manifest["bounds"] != bounds:
            raise ValueError("Saved block identity changed")
        verify_files(ROOT, manifest["files"])
        load_conditional_block(ROOT / manifest["model_directory"])
        return manifest
    directory = ROOT / "blocks" / f"block-{number:03}" / ("attempt-" + uuid4().hex)
    directory.mkdir(parents=True)
    save(directory / "attempt.json", {"definition_sha256": definition_sha, "bounds": bounds,
                                      "at": datetime.now(timezone.utc).isoformat(), "status": "started"})
    try:
        status("sampling_block", block=number, bounds=bounds)
        fit = sample_conditional_rows(market, features, context, bounds["fit_start"], bounds["calibration_start"], bounds["calibration_start"], seed=request["seed"])
        cal = sample_conditional_rows(market, features, context, bounds["calibration_start"], bounds["test_start"], bounds["test_start"], seed=request["seed"])
        sample_arrays = {f"{label}_{key}": sample[key] for label, sample in (("fit", fit), ("calibration", cal))
                         for key in ("rows", "columns", "X", "y", "reference_notional", "label_end")}
        np.savez_compressed(directory / "sample-arrays.npz", **sample_arrays)
        bundle = fit_conditional_block(fit, cal, bounds["fit_start"], bounds["calibration_start"], bounds["test_start"], directory / "model",
                                       seed=request["seed"], fallback_policy="abstain",
                                       metadata={"definition_sha256": definition_sha, "block": number, "bounds": bounds},
                                       progress=lambda event: status("fitting_block", block=number, model_progress=event))
        result = forecast_candidates(bundle, features, context, bounds["test_start"], bounds["test_end"],
                                     progress=lambda **event: status("predicting_block", block=number, **event))
        np.savez_compressed(directory / "forecasts.npz", **result)
        means, counts = setup_means(fit)
        memberships = context["setup_indicators"][result["rows"], result["columns"]]
        baseline = setup_baseline(memberships, means)
        targets = features["labels"][result["rows"], result["columns"]]
        with np.load(directory / "model" / "calibration-predictions.npz") as calibration:
            diagnostics = forecast_diagnostics(result, targets, baseline, calibration)
        diagnostics["setup_prior"] = {"names": list(SETUP_NAMES), "counts": counts,
                                      "means": [[float(x) if np.isfinite(x) else None for x in row] for row in means],
                                      "fallback": "pooled fitting mean if setup has no fitting members; diagnostics only"}
        save(directory / "test-diagnostics.json", diagnostics)
        manifest = {"definition_sha256": definition_sha, "block": number, "bounds": bounds,
                    "model_directory": (directory / "model").relative_to(ROOT).as_posix(),
                    "forecast_path": (directory / "forecasts.npz").relative_to(ROOT).as_posix(),
                    "family": bundle.family, "available": bundle.available,
                    "candidates": len(result["rows"]), "invalid_feature_rows": int(result["invalid_feature"].sum()),
                    "finite_corrected_rows": int(np.isfinite(result["corrected"]).all(axis=1).sum()),
                    "fit_rows": len(fit["rows"]), "calibration_rows": len(cal["rows"]),
                    "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(directory.rglob("*")) if p.is_file()}}
        save(pointer, manifest)
        return manifest
    except BaseException as error:
        save(directory / "failure.json", {"error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        raise


def assemble_forecasts(root, blocks, shape, definition_sha):
    pointer = root / "forecast-manifest.json"
    path = root / "corrected-forecasts.npy"
    inputs = {block["forecast_path"]: block["files"][block["forecast_path"]] for block in blocks}
    if pointer.exists():
        manifest = read(pointer)
        if (manifest["definition_sha256"] != definition_sha or manifest["inputs"] != inputs
                or manifest["shape"] != list(shape) or sha(path) != manifest["sha256"]):
            raise ValueError("Saved full-period forecast identity changed")
        return path, manifest["sha256"]
    # Every interrupted temporary file remains evidence; no partial output is reused.
    temporary = root / ("corrected-forecasts-" + uuid4().hex + ".tmp.npy")
    output = np.lib.format.open_memmap(temporary, mode="w+", dtype=np.float64, shape=shape)
    output[:] = np.nan
    for block in blocks:
        with np.load(root / block["forecast_path"]) as saved:
            output[saved["rows"], saved["columns"]] = saved["corrected"]
    output.flush()
    del output
    if path.exists():
        path.rename(root / ("unmanifested-forecasts-" + uuid4().hex + ".npy"))
    temporary.replace(path)
    identity = sha(path)
    save(pointer, {"definition_sha256": definition_sha, "inputs": inputs, "shape": list(shape),
                   "dtype": "float64", "sha256": identity})
    return path, identity


def benchmark(market, budget, costs, start, end):
    """Same whole-share SPY benchmark convention as the completed rule study."""
    column = market["benchmark"]
    values = market["adjusted"][start + 1:end + 1, column]
    price = float(market["close"][start + 1, column])
    if not np.isfinite(values).all() or (values <= 0).any() or not np.isfinite(price) or price <= 0:
        return {"status": "incomplete", "missing": ["SPY reference prices"]}
    quantity = costs.maximum_quantity(math.floor(budget / price), price, budget)
    equity = np.full(end - start + 1, budget, dtype=float)
    cash, fees = equity.copy(), 0.0
    if quantity:
        notional = quantity * price
        entry_fee = costs.fee(quantity, notional, "buy")
        free = budget - notional - entry_fee
        marks = notional * values / values[0]
        equity[1:], cash[1:] = free + marks, free
        exit_fee = costs.fee(quantity, float(marks[-1]), "sell")
        equity[-1] -= exit_fee
        cash[-1] = equity[-1]
        fees = entry_fee + exit_fee
    return _metrics(dict(status="complete", missing=[], equity=equity, cash=cash, fees=fees, trades=int(quantity > 0)), market["sessions"][start:end + 1], budget)


def evaluate_account(market, ranking, counts, forecast, forecast_identity, request, definition_sha, first, last, policy, horizon, profile):
    name = f"{policy}-{horizon}-{profile}"
    path = ROOT / "accounts" / (name + ".json")
    pointer = ROOT / "account-manifests" / (name + ".json")
    if pointer.exists():
        manifest = read(pointer)
        if manifest["definition_sha256"] != definition_sha or manifest["forecast_identity"] != forecast_identity or sha(path) != manifest["sha256"]:
            raise ValueError(f"Saved account identity changed: {name}")
        return read(path)
    if path.exists():
        path.rename(path.with_name(name + ".unmanifested-" + uuid4().hex + ".json"))
    try:
        head = request["holding_sessions"].index(horizon)
        entry_policy = None if policy == "static_setup_rank" else ConditionalPolicy(
            lambda row, column: (float(forecast[row, column, head]), float(forecast[row, column, head + 3])),
            ranking_mode="fraction" if policy == "conditional_net_fraction" else "dollars",
            forecast_identity=forecast_identity,
        )
        # One invocation for the complete date range: model switches never reset cash or holdings.
        simulation = _simulate_daily(market, policy, horizon, request["capital_usd"], request["round_trip_bps"], first, last,
                                     audit=True, signal_ranking=ranking, signal_counts=counts,
                                     cost_model=get_cost_profile(profile, request["round_trip_bps"]), entry_policy=entry_policy)
        report = _summarize(simulation, market["sessions"][first:last + 1], request["capital_usd"])
    except Exception as error:
        report = {"status": "failed", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc(),
                  "total_return": None, "max_drawdown": None}
    convention = ("original unconditional next-close fill sizing" if policy == "static_setup_rank" else
                  "simulated contingent-fill utility guard; no claim that closing price was known before submission")
    report.update(policy=policy, horizon=horizon, cost_profile=profile, definition_sha256=definition_sha,
                  forecast_identity=forecast_identity, qualification="exploratory_current_member_adjusted_vintage",
                  fill_convention=convention)
    save(path, report)
    save(pointer, {"definition_sha256": definition_sha, "forecast_identity": forecast_identity, "sha256": sha(path), "status": report["status"]})
    return report


def paired_results(results):
    lookup = {(r["policy"], r["horizon"], r["cost_profile"]): r for r in results}
    output = []
    for horizon in (1, 3, 5):
        for profile in ("proportional", "moomoo_ca_us"):
            for candidate, baseline in ((POLICIES[1], POLICIES[0]), (POLICIES[2], POLICIES[0]), (POLICIES[2], POLICIES[1])):
                left, right = lookup[candidate, horizon, profile], lookup[baseline, horizon, profile]
                complete = left["status"] == right["status"] == "complete"
                output.append({"candidate": candidate, "baseline": baseline, "horizon": horizon, "cost_profile": profile,
                               "status": "complete" if complete else "unavailable",
                               "total_return_difference": left["total_return"] - right["total_return"] if complete else None,
                               "max_drawdown_difference": left["max_drawdown"] - right["max_drawdown"] if complete else None})
    return output


def main():
    status("validating_frozen_inputs")
    request, definition = validate_definition()
    definition_sha = sha(ROOT / "definition.json")
    lock = sqlite3.connect((REPO / "data/historical/worker.lock.sqlite").as_uri() + "?mode=rw", uri=True, timeout=0)
    lock.execute("BEGIN EXCLUSIVE")
    attempt_path = ROOT / "attempts" / (uuid4().hex + ".json")
    attempt = {"definition_sha256": definition_sha, "started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}
    save(attempt_path, {**attempt, "status": "running"})
    try:
        status("loading_verified_preparation")
        market, features = joblib.load(PREP / "market-features.joblib", mmap_mode="r")
        preflight = read(PREP / "coverage-preflight.json")
        first, last = market["sessions"].index(request["first_signal"]), market["sessions"].index(request["last_session"])
        expected_bounds = [{"fit_start": start - 756, "calibration_start": start - 252, "test_start": start, "test_end": min(start + 251, last)} for start in range(first, last + 1, 252)]
        if expected_bounds != [{key: b[key] for key in expected_bounds[0]} for b in preflight["blocks"]]:
            raise ValueError("Saved outer boundaries differ from the declaration")
        status("building_conditional_context")
        context = build_context(market, features)
        daily_counts = context["eligible"][first:last + 1].sum(axis=1)
        coverage = {"definition_sha256": definition_sha, "prepared_symbols": len(market["symbols"]),
                    "distinct_eligible_symbols": int(context["eligible"][first:last + 1].any(axis=0).sum()),
                    "candidate_rows": int(daily_counts.sum()), "minimum_per_session": int(daily_counts.min()),
                    "median_per_session": float(np.median(daily_counts)), "maximum_per_session": int(daily_counts.max()),
                    "sessions": [{"session": market["sessions"][i], "eligible": int(daily_counts[i - first])} for i in range(first, last + 1)]}
        save_result(ROOT / "candidate-coverage.json", coverage)
        blocks = [run_block(number, bounds, market, features, context, request, definition_sha) for number, bounds in enumerate(expected_bounds)]
        status("assembling_shared_forecasts", blocks=len(blocks))
        path, forecast_identity = assemble_forecasts(ROOT, blocks, (*market["close"].shape, 6), definition_sha)
        forecast = np.load(path, mmap_mode="r")
        values = context["static_scores"]
        counts = np.isfinite(values).sum(axis=1).astype(np.int32)
        ranking = np.argsort(-np.where(np.isfinite(values), values, -np.inf), axis=1, kind="stable").astype(np.int32)
        del features, context, values
        gc.collect()
        results = []
        for policy in request["policies"]:
            for horizon in request["holding_sessions"]:
                for profile in request["cost_profiles"]:
                    status("evaluating_accounts", completed=len(results), total=18, current=f"{policy}-{horizon}-{profile}")
                    report = evaluate_account(market, ranking, counts, forecast, forecast_identity, request, definition_sha, first, last, policy, horizon, profile)
                    results.append({k: v for k, v in report.items() if k not in {"equity_curve", "trade_records", "period_returns", "policy_audit"}})
        references = {name: benchmark(market, request["capital_usd"], get_cost_profile(name, request["round_trip_bps"]), first, last) for name in request["cost_profiles"]}
        summary = {"request": request, "definition_sha256": definition_sha, "forecast_identity": forecast_identity,
                   "results": results, "references": references, "cash_reference_return": 0, "paired_results": paired_results(results),
                   "blocks": [{k: v for k, v in block.items() if k != "files"} for block in blocks],
                   "candidate_coverage": {k: v for k, v in coverage.items() if k != "sessions"},
                   "source_evidence": "preparation/source-evidence.json"}
        validate_definition(check_cache=False)
        if sha(ROOT / "definition.json") != definition_sha:
            raise ValueError("Experiment definition changed during execution")
        save_result(ROOT / "summary.json", summary)
        save_result(ROOT / "result-hashes.json", {p.name: sha(p) for p in sorted((ROOT / "accounts").glob("*.json")) if ".unmanifested-" not in p.name})
        save(attempt_path, {**attempt, "status": "complete", "completed_at": datetime.now(timezone.utc).isoformat(), "summary_sha256": sha(ROOT / "summary.json")})
        status("complete", completed=len(results), incomplete=sum(r["status"] != "complete" for r in results), blocks=len(blocks), summary=str(ROOT / "summary.json"))
    except BaseException as error:
        save(attempt_path, {**attempt, "status": "failed", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        raise
    finally:
        lock.rollback()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        status("failed", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        raise
