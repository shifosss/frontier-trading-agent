"""Extract fixed-cohort arrays from the verified existing cache and original quotes."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import traceback
from uuid import uuid4
from zoneinfo import ZoneInfo

import joblib
import numpy as np

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)


def vendor_arrays(payload, symbol, sessions):
    """Retain original quote units; never pair reconstructed nominal close with vendor volume."""
    result = payload["chart"]["result"][0]
    if result["meta"].get("symbol") != symbol or result["meta"].get("currency") != "USD":
        raise ValueError("Original quote identity/currency mismatch")
    stamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    if any(len(quote[key]) != len(stamps) for key in ("close", "volume")):
        raise ValueError("Original quote array lengths differ")
    indices = {day: i for i, day in enumerate(sessions)}
    close, volume = np.full(len(sessions), np.nan), np.full(len(sessions), np.nan)
    seen, outside, invalid = set(), [], []
    for stamp, price, shares in zip(stamps, quote["close"], quote["volume"], strict=True):
        day = datetime.fromtimestamp(stamp, timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if day not in indices:
            if sessions[0] <= day <= sessions[-1]:
                outside.append(day)
            continue
        if day in seen:
            raise ValueError("Duplicate original quote session: " + day)
        seen.add(day)
        i = indices[day]
        if isinstance(price, (int, float)) and np.isfinite(price) and price > 0:
            close[i] = price
        if isinstance(shares, (int, float)) and np.isfinite(shares) and shares >= 0:
            volume[i] = shares
        if not np.isfinite(close[i]) or not np.isfinite(volume[i]):
            invalid.append(day)
    return close, volume, {"observed_session_count": len(seen), "missing_sessions": sorted(set(sessions)-seen),
                            "invalid_sessions": invalid, "noncalendar_sessions_inside_window": outside,
                            "unit_convention": "Original vendor quote close times same-row original vendor volume"}


def prepare(definition_path):
    definition_path = Path(definition_path).resolve()
    definition_sha = sha(definition_path)
    definition = read(definition_path)
    paths, inputs = definition["paths"], definition["inputs"]
    required = {paths[key] for key in ("cohort", "calendar", "cache", "cache_manifest", "cache_source_evidence", "capture_index")}
    required.add(Path(__file__).relative_to(REPO).as_posix())
    if required - inputs.keys():
        raise ValueError("Definition omits a required market preparation identity")
    for name, expected in inputs.items():
        if sha(REPO/name) != expected:
            raise ValueError("Frozen preparation input changed: " + name)
    for package, expected in definition["dependencies"].items():
        if importlib.metadata.version(package) != expected:
            raise ValueError("Dependency changed: " + package)
    attempt = ROOT/"market-attempts"/uuid4().hex
    attempt.mkdir(parents=True)
    write(attempt/"attempt.json", {"started_at": datetime.now(timezone.utc).isoformat(),
          "definition_sha256": sha(definition_path), "definition": definition})
    try:
        cohort = read(REPO/paths["cohort"])
        selected = cohort["selected"]
        if len(selected) != 100 or len({r["cik"] for r in selected}) != 100 or len({r["symbol"] for r in selected}) != 100:
            raise ValueError("Expected the exact frozen100-issuer cohort")
        symbols = sorted({r["symbol"] for r in selected} | {"SPY"})
        manifest = read(REPO/paths["cache_manifest"])
        if inputs[paths["cache"]] != manifest["sha256"]:
            raise ValueError("Shared cache differs from its retained manifest")
        old, _ = joblib.load(REPO/paths["cache"], mmap_mode="r")
        calendar = read(REPO/paths["calendar"])
        sessions = [r["session"] for r in calendar["sessions"]]
        if sessions != old["sessions"]:
            raise ValueError("Shared cache/calendar session identities differ")
        evidence = read(REPO/paths["cache_source_evidence"])
        cache_hashes = {r["symbol"]: r["sha256"] for r in evidence["source_hashes"]}
        records = read(REPO/paths["capture_index"])
        indexed = {r["symbol"]: r for r in records}
        if len(indexed) != len(records):
            raise ValueError("Duplicate source capture identities")
        arrays = {key: np.full((len(sessions), len(symbols)), np.nan) for key in
                  ("close", "adjusted", "atr", "vendor_quote_close", "vendor_quote_volume")}
        arrays["settlement_index"] = np.asarray(old["settlement_index"])
        source_inputs, source_status = dict(inputs), []
        capture_root = (REPO/paths["capture_workspace"]).resolve()
        for j, symbol in enumerate(symbols):
            status = {"symbol": symbol, "cache_status": "unavailable", "vendor_quote_status": "unavailable"}
            if symbol in old["symbols"] and symbol in cache_hashes:
                oldj = old["symbols"].index(symbol)
                for key in ("close", "adjusted", "atr"):
                    arrays[key][:, j] = old[key][:, oldj]
                status.update(cache_status="copied_exactly", source_sha256=cache_hashes[symbol])
            else:
                status["cache_reason"] = "No original qualified history in the retained shared cache"
            record = indexed.get(symbol)
            if record is None or "path" not in record:
                status["vendor_quote_reason"] = "No frozen original capture record"
            else:
                path = (capture_root/record["path"]).resolve()
                if not path.is_relative_to(capture_root):
                    raise ValueError("Quote source escapes capture workspace")
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                    raise ValueError("Original quote bytes changed: " + symbol)
                if symbol in cache_hashes and cache_hashes[symbol] != record["sha256"]:
                    raise ValueError("Raw quotes and shared price cache have different vintages: " + symbol)
                source_inputs[path.relative_to(REPO).as_posix()] = record["sha256"]
                close, volume, audit = vendor_arrays(json.loads(raw), symbol, sessions)
                arrays["vendor_quote_close"][:, j] = close
                arrays["vendor_quote_volume"][:, j] = volume
                status.update(vendor_quote_status="mapped", raw_path=path.relative_to(REPO).as_posix(),
                              source_sha256=record["sha256"], captured_at=record["captured_at"], url=record["url"], **audit)
            source_status.append(status)
        np.savez(attempt/"market-arrays.npz", **arrays)
        market = {"symbols": symbols, "sessions": sessions, "benchmark": symbols.index("SPY"),
                  "benchmark_symbol": "SPY", "source_by_symbol": source_status,
                  "cohort_order": [{"symbol": r["symbol"], "cik": r["cik"]} for r in selected],
                  "arrays_sha256": sha(attempt/"market-arrays.npz"), "source_inputs": source_inputs,
                  "features_or_returns_computed": False,
                  "limitations": ["Current-member cohort; historical membership and delisted coverage unqualified",
                  "Retrospective vendor price vintage, not an as-of series",
                  "Reported-action nominal sizing and adjusted-notional marks do not establish complete corporate-action cash accounting"]}
        write(attempt/"market-inputs.json", market)
        if sha(definition_path) != definition_sha:
            raise ValueError("Preparation definition changed during extraction")
        for name, expected in source_inputs.items():
            if sha(REPO/name) != expected:
                raise ValueError("Source input changed during extraction: " + name)
        write(attempt/"completion.json", {"status": "complete", "definition_sha256": definition_sha,
              "completed_at": datetime.now(timezone.utc).isoformat(), "symbols": len(symbols),
              "copied_histories": sum(r["cache_status"] == "copied_exactly" for r in source_status),
              "mapped_quotes": sum(r["vendor_quote_status"] == "mapped" for r in source_status),
              "outputs": {name: sha(attempt/name) for name in ("market-inputs.json", "market-arrays.npz")}})
    except BaseException as error:
        write(attempt/"failure.json", {"status": "failed", "error": type(error).__name__+": "+str(error),
                                      "traceback": traceback.format_exc()})
        raise
    return attempt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--definition", required=True)
    args = parser.parse_args()
    print(prepare(args.definition))
