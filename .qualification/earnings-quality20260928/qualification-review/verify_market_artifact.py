"""Independent read-only check of the one completed source-only market extraction."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.metadata
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np

REPO = Path(__file__).resolve().parents[3]
REVIEW = Path(__file__).resolve().parent
BASE = REVIEW.parent
ATTEMPT = BASE / "model-inputs/market-attempts/fd5e59aac98c4fc298f0c7ce9a860c18"
DEFINITION = BASE / "model-inputs/market-definition.json"
# Exact declared identity, kept separate from the artifact's own statement.
EXPECTED_DEFINITION = "2ce0cac8cded227b612ff63c9181f64e1e84a0d6fd98e1ffb52c56a75ef75544"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify():
    assert sha(DEFINITION) == EXPECTED_DEFINITION
    definition = read(DEFINITION)
    attempt = read(ATTEMPT / "attempt.json")
    completed = read(ATTEMPT / "completion.json")
    market = read(ATTEMPT / "market-inputs.json")
    assert attempt["definition"] == definition
    assert attempt["definition_sha256"] == completed["definition_sha256"] == EXPECTED_DEFINITION
    assert completed["status"] == "complete" and not (ATTEMPT / "failure.json").exists()
    for name, digest in completed["outputs"].items():
        assert sha(ATTEMPT / name) == digest, name
    assert market["arrays_sha256"] == completed["outputs"]["market-arrays.npz"]
    assert market["features_or_returns_computed"] is False
    for name, digest in definition["inputs"].items():
        assert market["source_inputs"][name] == digest, name
    for name, digest in market["source_inputs"].items():
        assert sha(REPO / name) == digest, name
    for name, version in definition["dependencies"].items():
        assert importlib.metadata.version(name) == version
    paths = definition["paths"]
    cohort = read(REPO / paths["cohort"])
    selected = [{"symbol": row["symbol"], "cik": row["cik"]} for row in cohort["selected"]]
    assert len(selected) == len({row["symbol"] for row in selected}) == len({row["cik"] for row in selected}) == 100
    assert market["cohort_order"] == selected
    symbols = sorted([row["symbol"] for row in selected] + ["SPY"])
    assert market["symbols"] == symbols and len(symbols) == 101
    assert symbols[market["benchmark"]] == market["benchmark_symbol"] == "SPY"
    assert [row["symbol"] for row in market["source_by_symbol"]] == symbols
    calendar = read(REPO / paths["calendar"])
    sessions = [row["session"] for row in calendar["sessions"]]
    assert sessions == sorted(set(sessions)) == market["sessions"]
    session_indices = {day: index for index, day in enumerate(sessions)}
    manifest = read(REPO / paths["cache_manifest"])
    cache_path = REPO / paths["cache"]
    assert manifest["sha256"] == market["source_inputs"][paths["cache"]]
    assert cache_path.stat().st_size == manifest["bytes"]
    cached, _ = joblib.load(cache_path, mmap_mode="r")
    assert cached["sessions"] == sessions
    evidence = read(REPO / paths["cache_source_evidence"])
    assert evidence["capture_index_sha256"] == market["source_inputs"][paths["capture_index"]]
    by_cache_source = {row["symbol"]: row["sha256"] for row in evidence["source_hashes"]}
    assert len(by_cache_source) == len(evidence["source_hashes"])
    capture_records = read(REPO / paths["capture_index"])
    by_capture = {row["symbol"]: row for row in capture_records}
    assert len(by_capture) == len(capture_records)
    assert len(set(cached["symbols"])) == len(cached["symbols"])
    cached_indices = {symbol: i for i, symbol in enumerate(cached["symbols"])}
    arrays = np.load(ATTEMPT / "market-arrays.npz")
    expected_keys = {"close", "adjusted", "atr", "vendor_quote_close", "vendor_quote_volume", "settlement_index"}
    assert set(arrays.files) == expected_keys
    values = {key: arrays[key] for key in arrays.files}
    arrays.close()
    for key in expected_keys - {"settlement_index"}:
        assert values[key].shape == (len(sessions), len(symbols)), key
    assert np.array_equal(values["settlement_index"], cached["settlement_index"])
    assert values["settlement_index"].dtype == cached["settlement_index"].dtype
    per_symbol, product_count, different_nominal = [], 0, 0
    ny = ZoneInfo("America/New_York")
    for j, symbol in enumerate(symbols):
        cached_j = cached_indices[symbol]
        for key in ("close", "adjusted", "atr"):
            assert np.array_equal(values[key][:, j], cached[key][:, cached_j], equal_nan=True), (symbol, key)
        status = market["source_by_symbol"][j]
        assert status["cache_status"] == "copied_exactly" and status["vendor_quote_status"] == "mapped"
        record = by_capture[symbol]
        raw_path = (REPO / paths["capture_workspace"] / record["path"]).resolve()
        assert raw_path == (REPO / status["raw_path"]).resolve()
        raw = raw_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["sha256"] == by_cache_source[symbol] == status["source_sha256"]
        assert market["source_inputs"][status["raw_path"]] == record["sha256"]
        assert status["captured_at"] == record["captured_at"] and status["url"] == record["url"]
        result = json.loads(raw)["chart"]["result"][0]
        assert result["meta"]["symbol"] == symbol and result["meta"]["currency"] == "USD"
        quote = result["indicators"]["quote"][0]
        assert len(result["timestamp"]) == len(quote["close"]) == len(quote["volume"])
        original_close, original_volume = np.full(len(sessions), np.nan), np.full(len(sessions), np.nan)
        observed, invalid, outside = set(), [], []
        symbol_products = 0
        for timestamp, close, volume in zip(result["timestamp"], quote["close"], quote["volume"], strict=True):
            day = datetime.fromtimestamp(timestamp, ny).date().isoformat()
            if day not in session_indices:
                if sessions[0] <= day <= sessions[-1]:
                    outside.append(day)
                continue
            assert day not in observed, (symbol, day)
            observed.add(day)
            i = session_indices[day]
            valid_close = type(close) in (int, float) and np.isfinite(close) and close > 0
            valid_volume = type(volume) in (int, float) and np.isfinite(volume) and volume >= 0
            if valid_close:
                original_close[i] = close
            if valid_volume:
                original_volume[i] = volume
            if not (valid_close and valid_volume):
                invalid.append(day)
            else:
                actual_close, actual_volume = values["vendor_quote_close"][i, j], values["vendor_quote_volume"][i, j]
                original_product = Decimal(str(close)) * Decimal(str(volume))
                extracted_product = Decimal(str(float(actual_close))) * Decimal(str(float(actual_volume)))
                assert original_product == extracted_product, (symbol, day, "vendor dollar product")
                symbol_products += 1
                if np.isfinite(values["close"][i, j]) and values["close"][i, j] != actual_close:
                    different_nominal += 1
        assert np.array_equal(original_close, values["vendor_quote_close"][:, j], equal_nan=True), (symbol, "original close")
        assert np.array_equal(original_volume, values["vendor_quote_volume"][:, j], equal_nan=True), (symbol, "original volume")
        missing = sorted(set(sessions) - observed)
        assert status["observed_session_count"] == len(observed)
        assert status["missing_sessions"] == missing and status["invalid_sessions"] == invalid
        assert status["noncalendar_sessions_inside_window"] == outside
        good_adjusted = np.isfinite(values["adjusted"][:, j]) & (values["adjusted"][:, j] > 0)
        good_product = np.isfinite(original_close) & (original_close > 0) & np.isfinite(original_volume) & (original_volume >= 0)
        study = np.array(["2017-01-01" <= day <= "2025-12-31" for day in sessions])
        missing_inside_observed_span = [day for day in missing if min(observed) <= day <= max(observed)] if observed else []
        per_symbol.append({"symbol": symbol, "calendar_rows": len(sessions), "observed_raw_rows": len(observed), "missing_raw_rows": len(missing), "missing_inside_observed_span": len(missing_inside_observed_span), "invalid_raw_rows": len(invalid), "valid_adjusted_close_rows": int(good_adjusted.sum()), "valid_original_quote_product_rows": int(good_product.sum()), "original_product_decimal_checks": symbol_products, "study_2017_2025_calendar_rows": int(study.sum()), "study_2017_2025_valid_adjusted_rows": int((study & good_adjusted).sum()), "study_2017_2025_valid_original_product_rows": int((study & good_product).sum()), "first_observed": min(observed) if observed else None, "last_observed": max(observed) if observed else None})
        product_count += symbol_products
    assert completed["symbols"] == completed["copied_histories"] == completed["mapped_quotes"] == 101
    # Recheck all identities after the comparison, including the memory-mapped cache.
    for name, digest in market["source_inputs"].items():
        assert sha(REPO / name) == digest, name
    assert sha(DEFINITION) == EXPECTED_DEFINITION
    for name, digest in completed["outputs"].items():
        assert sha(ATTEMPT / name) == digest, name
    return {
        "status": "verified", "at": datetime.now(timezone.utc).isoformat(), "attempt": str(ATTEMPT.relative_to(REPO)), "definition_sha256": EXPECTED_DEFINITION,
        "checker_sha256": sha(Path(__file__)), "fixed_issuer_count": 100, "benchmark_count": 1, "symbols": 101, "calendar_sessions": len(sessions), "calendar_first": sessions[0], "calendar_last": sessions[-1],
        "input_identities_verified_before_and_after": len(market["source_inputs"]), "cache_bytes_verified": manifest["bytes"], "output_identities": completed["outputs"],
        "exact_cached_column_comparisons": 303, "cached_array_values_compared": len(sessions) * 101 * 3, "exact_vendor_column_comparisons": 202, "vendor_array_values_compared": len(sessions) * 101 * 2, "settlement_indices_compared": len(sessions),
        "vendor_product_decimal_comparisons": product_count, "vendor_close_rows_different_from_cached_nominal": different_nominal,
        "source_coverage_only": {"all_calendar_symbol_rows": len(sessions) * 101, "missing_raw_rows": sum(row["missing_raw_rows"] for row in per_symbol), "invalid_raw_rows": sum(row["invalid_raw_rows"] for row in per_symbol), "missing_inside_observed_spans": sum(row["missing_inside_observed_span"] for row in per_symbol), "symbols_with_missing_raw_rows": [row["symbol"] for row in per_symbol if row["missing_raw_rows"]], "symbols_with_invalid_raw_rows": [row["symbol"] for row in per_symbol if row["invalid_raw_rows"]], "study_2017_2025_missing_adjusted_rows": sum(row["study_2017_2025_calendar_rows"] - row["study_2017_2025_valid_adjusted_rows"] for row in per_symbol), "study_2017_2025_missing_vendor_product_rows": sum(row["study_2017_2025_calendar_rows"] - row["study_2017_2025_valid_original_product_rows"] for row in per_symbol)},
        "by_symbol": per_symbol, "source_identities": market["source_inputs"], "findings": [],
        "limitations": ["Counts describe source availability only, not event eligibility, sample sufficiency, strategy filters or returns.", "Exact copying and source matching do not validate point-in-time vendor vintages, historical listing membership, corporate-action completeness or execution quality."],
        "market_build_reruns": 0, "financial_features_computed": 0, "labels_computed": 0, "model_fits": 0, "account_runs": 0, "network_requests": 0
    }


if __name__ == "__main__":
    result = verify()
    name = "market-artifact-verification-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    path = REVIEW / name
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"path": str(path), "sha256": sha(path), "status": result["status"], "inputs": result["input_identities_verified_before_and_after"], "product_checks": result["vendor_product_decimal_comparisons"], "source_coverage_only": result["source_coverage_only"]}, indent=2))
