"""Independent calibration-only coefficient and transformed-forecast verification."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.with_name("conditional-selection20260928")
REPO = ROOT.parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def equal_bits(left, right, label):
    assert left.shape == right.shape and left.dtype == right.dtype, label
    assert np.array_equal(left.view(np.uint8), right.view(np.uint8)), label


def near(actual, expected, label):
    assert np.isclose(float(actual), float(expected), rtol=2e-10, atol=2e-12), label


def decimal_coefficients(raw, targets):
    """Full saved calibration rows, exact binary-float inputs, 50-digit arithmetic."""
    result = []
    with localcontext() as ctx:
        ctx.prec = 50
        for head in range(3):
            x = [Decimal.from_float(float(value)) for value in raw[:, head]]
            y = [Decimal.from_float(float(value)) for value in targets[:, head]]
            n = Decimal(len(x))
            mx, my = sum(x) / n, sum(y) / n
            var = sum((value - mx) ** 2 for value in x) / n
            cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / n
            constant = all(value == x[0] for value in x)
            if constant:
                var = Decimal(0)
                cov = Decimal(0)
            slope_raw = cov / var if var else Decimal(0)
            slope = max(Decimal(0), min(Decimal(1), slope_raw))
            result.append(dict(index=head, count=len(x), mean_raw=str(mx), mean_target=str(my),
                               variance_raw=str(var), covariance_raw_target=str(cov),
                               unconstrained_slope=str(slope_raw), slope=str(slope),
                               intercept=str(my - slope * mx), zero_variance=constant))
    return result


def audit_block(pointer, definition_sha, source_definition_sha, dense):
    manifest = read(pointer)
    assert manifest["definition_sha256"] == definition_sha
    number = manifest["block"]
    source_pointer = SOURCE / "blocks" / f"block-{number:03}.json"
    original = read(source_pointer)
    assert original["definition_sha256"] == source_definition_sha
    assert manifest["bounds"] == original["bounds"]
    assert manifest["source_block_sha256"] == sha(source_pointer)
    for name, expected in manifest["files"].items():
        assert sha(ROOT / name) == expected, name
    for name, expected in original["files"].items():
        if Path(name).name in ("forecasts.npz", "sample-arrays.npz", "calibration-predictions.npz"):
            assert sha(SOURCE / name) == expected, name
    model = SOURCE / original["model_directory"]
    parameters_path = ROOT / manifest["parameters_path"]
    parameters = read(parameters_path)
    with np.load(model / "calibration-predictions.npz") as calibration, np.load(model.parent / "sample-arrays.npz") as sample:
        for a, b in (("rows", "calibration_rows"), ("columns", "calibration_columns"), ("targets", "calibration_y")):
            equal_bits(calibration[a], sample[b], "exact source calibration pairing " + a)
        assert (sample["calibration_label_end"] < original["bounds"]["test_start"]).all()
        assert (calibration["rows"] >= original["bounds"]["calibration_start"]).all()
        assert (calibration["rows"] < original["bounds"]["test_start"]).all()
        assert np.isfinite(calibration["raw"]).all() and np.isfinite(calibration["targets"]).all()
        assert parameters["schema"] == "conditional-return-shrinkage-v1"
        for key in ("raw", "targets"):
            values = calibration[key]
            assert parameters["calibration_arrays"][key] == {"shape": list(values.shape), "dtype": str(values.dtype), "sha256": hashlib.sha256(values.tobytes(order="C")).hexdigest()}
        assert parameters["source_identity"] == {"block": number, "calibration_sha256": sha(model / "calibration-predictions.npz"), "sample_sha256": sha(model.parent / "sample-arrays.npz"), "bounds": original["bounds"]}
        coefficients = decimal_coefficients(calibration["raw"], calibration["targets"])
        assert parameters["calibration_rows"] == len(calibration["rows"])
        for expected, actual in zip(coefficients, parameters["returns"], strict=True):
            assert actual["index"] == expected["index"] and actual["count"] == expected["count"]
            assert actual["zero_variance"] == expected["zero_variance"]
            for key in ("mean_raw", "mean_target", "variance_raw", "covariance_raw_target", "unconstrained_slope", "slope", "intercept"):
                near(actual[key], expected[key], f"block {number} head {expected['index']} {key}")
        slope_one = calibration["raw"][:, :3] + np.mean(calibration["targets"][:, :3], axis=0) - np.mean(calibration["raw"][:, :3], axis=0)
        slope_one_error = float(np.max(np.abs(slope_one - calibration["corrected"][:, :3])))
        assert slope_one_error <= 2e-12
    with np.load(SOURCE / original["forecast_path"]) as old, np.load(ROOT / manifest["forecast_path"]) as new:
        for key in ("rows", "columns", "raw", "invalid_feature"):
            equal_bits(old[key], new[key], "unchanged " + key)
        equal_bits(old["corrected"][:, 3:].copy(), new["corrected"][:, 3:].copy(), "exact unchanged downside")
        assert np.array_equal(np.isfinite(old["corrected"]), np.isfinite(new["corrected"]))
        errors = []
        for head, coefficient in enumerate(coefficients):
            expected = float(coefficient["mean_target"]) + float(coefficient["slope"]) * (old["raw"][:, head] - float(coefficient["mean_raw"]))
            actual = new["corrected"][:, head]
            valid = np.isfinite(expected)
            assert np.allclose(actual[valid], expected[valid], rtol=2e-10, atol=2e-12)
            errors.append(float(np.max(np.abs(actual[valid] - expected[valid]))) if valid.any() else 0.0)
        equal_bits(new["corrected"], np.asarray(dense[new["rows"], new["columns"]]), "dense forecast exact assembly")
        return {"block": number, "status": "passed", "calibration_rows": parameters["calibration_rows"],
                "forecast_rows": len(new["rows"]), "source_block_sha256": sha(source_pointer),
                "new_block_manifest_sha256": sha(pointer), "parameters_sha256": sha(parameters_path),
                "decimal_coefficients": coefficients, "maximum_transformed_return_errors": errors,
                "original_slope_one_bias_reconstruction_error": slope_one_error}


def main():
    definition = read(ROOT / "definition.json")
    definition_sha = sha(ROOT / "definition.json")
    source_definition_sha = sha(SOURCE / "definition.json")
    assert definition["original_definition_sha256"] == source_definition_sha
    for collection in ("files", "inputs"):
        for name, expected in definition[collection].items():
            assert sha(REPO / name) == expected, name
    for name, expected in read(SOURCE / "definition.json")["files"].items():
        assert sha(REPO / name) == expected, name
    forecast_manifest = read(ROOT / "forecast-manifest.json")
    assert forecast_manifest["definition_sha256"] == definition_sha
    dense_path = ROOT / "corrected-forecasts.npy"
    assert sha(dense_path) == forecast_manifest["sha256"]
    dense = np.load(dense_path, mmap_mode="r")
    pointers = sorted((ROOT / "blocks").glob("block-*.json"))
    assert len(pointers) == 11
    records = []
    for pointer in pointers:
        print(json.dumps({"independent_block": pointer.name, "phase": "full_decimal_coefficients"}), flush=True)
        records.append(audit_block(pointer, definition_sha, source_definition_sha, dense))
    # No new dense-map memberships may appear outside the original shared candidate map.
    old_dense = np.load(SOURCE / "corrected-forecasts.npy", mmap_mode="r")
    assert dense.shape == old_dense.shape
    for start in range(0, len(dense), 32):
        new_chunk, old_chunk = np.asarray(dense[start:start+32]), np.asarray(old_dense[start:start+32])
        assert np.array_equal(np.isfinite(new_chunk), np.isfinite(old_chunk))
        equal_bits(new_chunk[:, :, 3:].copy(), old_chunk[:, :, 3:].copy(), "full dense downside")
    now = datetime.now(timezone.utc)
    result = {"reviewed_at": now.isoformat(), "definition_sha256": definition_sha,
              "original_definition_sha256": source_definition_sha, "forecast_identity": forecast_manifest["sha256"],
              "script_sha256": sha(Path(__file__)), "blocks": records,
              "qualification": "Full Decimal calibration arithmetic and exact preserved candidate/downside identity; not source completeness or profitability."}
    output = ROOT / ("independent-coefficient-audit-" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "blocks": len(records), "coefficients": 3*len(records),
                      "calibration_rows": sum(r["calibration_rows"] for r in records),
                      "forecast_rows": sum(r["forecast_rows"] for r in records), "status": "passed"}), flush=True)


if __name__ == "__main__":
    main()
