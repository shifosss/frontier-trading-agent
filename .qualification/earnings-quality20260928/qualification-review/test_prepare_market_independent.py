"""Bounded synthetic provenance and membership review for market extraction."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path

import joblib
import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("independent_market_preparation", HERE.parent / "model-inputs/prepare_market.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(tmp_path, monkeypatch):
    repo = tmp_path
    root = repo / "inputs"
    root.mkdir()
    capture = repo / "capture"
    capture.mkdir()
    code = repo / "prepare_market.py"
    code.write_bytes(Path(m.__file__).read_bytes())
    monkeypatch.setattr(m, "REPO", repo)
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "__file__", str(code))
    selected = [{"symbol": f"S{i:03}", "cik": str(i+1).zfill(10)} for i in range(100)]
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    cache_symbols = ["S000", "SPY"]
    old = {"symbols": cache_symbols, "sessions": days, "settlement_index": np.array([1, 2, 3])}
    old["close"] = np.array([[50., 100.], [60., 110.], [np.nan, 120.]])
    old["adjusted"] = old["close"] / 2
    old["atr"] = np.ones((3, 2))
    joblib.dump((old, None), repo / "cache.joblib")
    def save(name, value):
        (repo / name).write_text(json.dumps(value))
    records, hashes = [], []
    for symbol in cache_symbols:
        payload = {"chart": {"result": [{"meta": {"symbol": symbol, "currency": "USD"}, "timestamp": [int(datetime.fromisoformat(day + "T21:00:00+00:00").timestamp()) for day in days], "indicators": {"quote": [{"close": [5, 6, None], "volume": [100, 200, 300]}]}}]}}
        path = capture / (symbol + ".json")
        path.write_text(json.dumps(payload))
        digest = m.sha(path)
        records.append({"symbol": symbol, "path": path.name, "sha256": digest, "captured_at": "2026-09-18T21:00:00+00:00", "url": "synthetic-original"})
        hashes.append({"symbol": symbol, "sha256": digest})
    save("cohort.json", {"selected": selected})
    save("calendar.json", {"sessions": [{"session": day} for day in days]})
    save("manifest.json", {"sha256": m.sha(repo / "cache.joblib")})
    save("evidence.json", {"source_hashes": hashes})
    save("index.json", records)
    paths = {"cohort": "cohort.json", "calendar": "calendar.json", "cache": "cache.joblib", "cache_manifest": "manifest.json", "cache_source_evidence": "evidence.json", "capture_index": "index.json", "capture_workspace": "capture"}
    names = {value for key, value in paths.items() if key != "capture_workspace"} | {"prepare_market.py"}
    definition = {"paths": paths, "inputs": {name: m.sha(repo / name) for name in names}, "dependencies": {}}
    save("definition.json", definition)
    return repo / "definition.json", old, selected


def test_all_issuers_retained_with_original_units_and_missing_future_rows(tmp_path, monkeypatch):
    definition, old, selected = fixture(tmp_path, monkeypatch)
    attempt = m.prepare(definition)
    market = m.read(attempt / "market-inputs.json")
    assert market["cohort_order"] == selected
    assert len(market["symbols"]) == 101
    with np.load(attempt / "market-arrays.npz") as arrays:
        index = market["symbols"].index("S000")
        missing = market["symbols"].index("S099")
        np.testing.assert_array_equal(arrays["close"][:, index], old["close"][:, 0])
        np.testing.assert_array_equal(arrays["vendor_quote_close"][:, index], [5, 6, np.nan])
        np.testing.assert_array_equal(arrays["vendor_quote_volume"][:, index], [100, 200, 300])
        for key in ("close", "adjusted", "atr", "vendor_quote_close", "vendor_quote_volume"):
            assert np.isnan(arrays[key][:, missing]).all()
    assert not market["features_or_returns_computed"]
    assert next(row for row in market["source_by_symbol"] if row["symbol"] == "S099")["cache_status"] == "unavailable"


def test_changed_frozen_cache_is_rejected_before_extraction(tmp_path, monkeypatch):
    definition, _, _ = fixture(tmp_path, monkeypatch)
    with (tmp_path / "cache.joblib").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="Frozen preparation input changed"):
        m.prepare(definition)


def test_changed_raw_bytes_are_rejected(tmp_path, monkeypatch):
    definition, _, _ = fixture(tmp_path, monkeypatch)
    with (tmp_path / "capture/S000.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="Original quote bytes changed"):
        m.prepare(definition)


def test_cache_and_raw_quote_vintage_disagreement_is_rejected(tmp_path, monkeypatch):
    definition, _, _ = fixture(tmp_path, monkeypatch)
    evidence = m.read(tmp_path / "evidence.json")
    evidence["source_hashes"][0]["sha256"] = "0" * 64
    (tmp_path / "evidence.json").write_text(json.dumps(evidence))
    declared = m.read(definition)
    declared["inputs"]["evidence.json"] = m.sha(tmp_path / "evidence.json")
    definition.write_text(json.dumps(declared))
    with pytest.raises(ValueError, match="different vintages"):
        m.prepare(definition)


@pytest.mark.parametrize("kind", ["raw", "definition", "cache"])
def test_source_changed_after_verified_read_cannot_complete(tmp_path, monkeypatch, kind):
    definition, _, _ = fixture(tmp_path, monkeypatch)
    original_vendor_arrays = m.vendor_arrays
    changed = False
    observed = []
    def changed_vendor_arrays(payload, symbol, sessions):
        nonlocal changed
        if symbol == "S000" and not changed:
            changed = True
            if kind == "raw":
                target = tmp_path / "capture/S000.json"
                changed_payload = m.read(target)
                changed_payload["chart"]["result"][0]["indicators"]["quote"][0]["close"][0] = 999
                target.write_text(json.dumps(changed_payload))
            elif kind == "definition":
                with definition.open("a") as stream:
                    stream.write(" ")
            else:
                with (tmp_path / "cache.joblib").open("ab") as stream:
                    stream.write(b"changed after initial identity check")
        result = original_vendor_arrays(payload, symbol, sessions)
        if symbol == "S000":
            observed.append(float(result[0][0]))
        return result
    monkeypatch.setattr(m, "vendor_arrays", changed_vendor_arrays)
    with pytest.raises(ValueError, match="changed"):
        m.prepare(definition)
    assert changed and observed == [5.0]
    attempts = list((tmp_path / "inputs/market-attempts").iterdir())
    assert len(attempts) == 1
    assert (attempts[0] / "failure.json").is_file()
    assert not (attempts[0] / "completion.json").exists()
