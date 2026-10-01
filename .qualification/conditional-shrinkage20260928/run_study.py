"""Six frozen calibration comparisons over existing models; no broker access."""
import gc
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from uuid import uuid4

import joblib
import numpy as np

from frontier.historical_lab import _save
from calibration import fit_return_shrinkage, apply_return_shrinkage

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SOURCE = ROOT.parent / "conditional-selection20260928"
POLICY = "conditional_shrinkage_dollars"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load_module("original_conditional_runner", SOURCE / "run_study.py")
read, sha = source.read, source.sha


def save_result(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Retained result differs: {path}")
    else:
        _save(path, value)


def status(phase, **details):
    value = dict(phase=phase, pid=os.getpid(), updated_at=datetime.now(timezone.utc).isoformat(), **details)
    _save(ROOT / "status.json", value)
    print(json.dumps(value), flush=True)


def validate(check_cache=True):
    request, definition = read(ROOT / "request.json"), read(ROOT / "definition.json")
    source.validate_definition(check_cache=check_cache)
    source.verify_files(REPO, definition["files"])
    source.verify_files(REPO, definition["inputs"])
    assert sha(ROOT / "request.json") == definition["request_sha256"]
    assert sha(SOURCE / "definition.json") == definition["original_definition_sha256"]
    assert request["policies"] == [POLICY] and request["planned_accounts"] == 6
    original = read(SOURCE / "request.json")
    for key in ("capital_usd", "holding_sessions", "cost_profiles", "round_trip_bps", "first_signal", "last_session", "execution", "cost_specifications"):
        assert request[key] == original[key], key
    return request, definition


def transform_block(number, original, definition_sha):
    pointer = ROOT / "blocks" / f"block-{number:03}.json"
    if pointer.exists():
        result = read(pointer)
        assert result["definition_sha256"] == definition_sha
        source.verify_files(ROOT, result["files"])
        return result
    directory = ROOT / "blocks" / f"block-{number:03}" / ("attempt-" + uuid4().hex)
    directory.mkdir(parents=True)
    source.verify_files(SOURCE, original["files"])
    model_path = SOURCE / original["model_directory"]
    bounds = original["bounds"]
    try:
        with np.load(model_path.parent / "sample-arrays.npz") as sample, np.load(model_path / "calibration-predictions.npz") as cal:
            assert np.array_equal(sample["calibration_rows"], cal["rows"])
            assert np.array_equal(sample["calibration_columns"], cal["columns"])
            assert np.array_equal(sample["calibration_y"], cal["targets"])
            assert np.all(sample["calibration_label_end"] < bounds["test_start"])
            assert np.all(sample["calibration_rows"] >= bounds["calibration_start"])
            assert np.all(sample["calibration_rows"] < bounds["test_start"])
            parameters = fit_return_shrinkage(cal["raw"], cal["targets"], source_identity={
                "block": number, "calibration_sha256": sha(model_path / "calibration-predictions.npz"),
                "sample_sha256": sha(model_path.parent / "sample-arrays.npz"), "bounds": bounds,
            })
        _save(directory / "parameters.json", parameters)
        with np.load(SOURCE / original["forecast_path"]) as saved:
            result = {key: saved[key] for key in saved.files}
            result["corrected"] = apply_return_shrinkage(parameters, saved["raw"], saved["corrected"])
            assert np.array_equal(result["corrected"][:, 3:], saved["corrected"][:, 3:])
            assert np.isfinite(result["corrected"]).all()
            np.savez_compressed(directory / "forecasts.npz", **result)
        manifest = {"definition_sha256": definition_sha, "block": number, "bounds": bounds,
                    "source_block_sha256": sha(SOURCE / "blocks" / f"block-{number:03}.json"),
                    "original_model_directory": str(model_path.relative_to(REPO)),
                    "parameters_path": (directory / "parameters.json").relative_to(ROOT).as_posix(),
                    "forecast_path": (directory / "forecasts.npz").relative_to(ROOT).as_posix(),
                    "candidates": len(result["rows"]),
                    "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(directory.iterdir()) if p.is_file()}}
        _save(pointer, manifest)
        return manifest
    except BaseException as error:
        _save(directory / "failure.json", {"error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        raise


def evaluate_account(*args):
    """Reuse the exact frozen cash runner with explicit output/persistence bindings."""
    original_root, original_save = source.ROOT, source.save
    try:
        source.ROOT, source.save = ROOT, _save
        return source.evaluate_account(*args)
    finally:
        source.ROOT, source.save = original_root, original_save


def main():
    request, definition = validate()
    definition_sha = sha(ROOT / "definition.json")
    lock = sqlite3.connect((REPO / "data/historical/worker.lock.sqlite").as_uri() + "?mode=rw", uri=True, timeout=0)
    lock.execute("BEGIN EXCLUSIVE")
    attempt_path = ROOT / "attempts" / (uuid4().hex + ".json")
    attempt = {"definition_sha256": definition_sha, "started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "status": "running"}
    _save(attempt_path, attempt)
    try:
        status("transforming_saved_forecasts")
        originals = [read(SOURCE / "blocks" / f"block-{number:03}.json") for number in range(11)]
        blocks = [transform_block(number, block, definition_sha) for number, block in enumerate(originals)]
        status("loading_verified_market")
        market, features = joblib.load(SOURCE / "preparation/market-features.joblib", mmap_mode="r")
        first, last = (market["sessions"].index(request[key]) for key in ("first_signal", "last_session"))
        path, forecast_identity = source.assemble_forecasts(ROOT, blocks, (*market["close"].shape, 6), definition_sha)
        forecasts = np.load(path, mmap_mode="r")
        status("reconstructing_identical_candidate_population")
        context = source.build_context(market, features)
        values = context["static_scores"]
        counts = np.isfinite(values).sum(axis=1).astype(np.int32)
        ranking = np.argsort(-np.where(np.isfinite(values), values, -np.inf), axis=1, kind="stable").astype(np.int32)
        coverage = read(SOURCE / "candidate-coverage.json")
        assert int(counts[first:last+1].sum()) == coverage["candidate_rows"]
        assert counts[first:last+1].tolist() == [row["eligible"] for row in coverage["sessions"]]
        # Labels are consulted only after parameters/predictions are saved, for reporting.
        diagnostics = []
        for block in blocks:
            with np.load(ROOT / block["forecast_path"]) as saved:
                target = features["labels"][saved["rows"], saved["columns"], :3]
                old = np.load(SOURCE / originals[block["block"]]["forecast_path"])
                heads = []
                for head in range(3):
                    valid = np.isfinite(target[:, head])
                    heads.append({"head": head, "paired": int(valid.sum()), "missing_target": int((~valid).sum()),
                                  "new_mse": float(np.square(saved["corrected"][valid, head] - target[valid, head]).mean()),
                                  "original_mse": float(np.square(old["corrected"][valid, head] - target[valid, head]).mean())})
                old.close()
                diagnostics.append({"block": block["block"], "heads": heads})
        save_result(ROOT / "test-diagnostics.json", diagnostics)
        del features, context, values
        gc.collect()
        results = []
        for horizon in request["holding_sessions"]:
            for profile in request["cost_profiles"]:
                status("evaluating_accounts", completed=len(results), total=6, current=f"{POLICY}-{horizon}-{profile}")
                report = evaluate_account(market, ranking, counts, forecasts, forecast_identity, request, definition_sha,
                                          first, last, POLICY, horizon, profile)
                results.append({k: v for k, v in report.items() if k not in {"equity_curve", "trade_records", "period_returns", "policy_audit"}})
        original_summary = read(SOURCE / "summary.json")
        summary = {"request": request, "definition_sha256": definition_sha, "forecast_identity": forecast_identity,
                   "results": results, "references": original_summary["references"], "cash_reference_return": 0,
                   "source_summary_sha256": sha(SOURCE / "summary.json"), "blocks": blocks}
        validate(check_cache=False)
        assert sha(ROOT / "definition.json") == definition_sha
        save_result(ROOT / "summary.json", summary)
        save_result(ROOT / "result-hashes.json", {p.name: sha(p) for p in sorted((ROOT / "accounts").glob("*.json")) if ".unmanifested-" not in p.name})
        _save(attempt_path, {**attempt, "status": "complete", "completed_at": datetime.now(timezone.utc).isoformat(), "summary_sha256": sha(ROOT / "summary.json")})
        status("complete", completed=len(results), incomplete=sum(r["status"] != "complete" for r in results))
    except BaseException as error:
        _save(attempt_path, {**attempt, "status": "failed", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        lock.rollback()
        lock.close()


if __name__ == "__main__":
    main()
    raise SystemExit(subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "economic_analysis.py")], cwd=REPO, check=False).returncode)
