"""Offline frozen ETF prices and causal signals; no forward labels/accounts."""
import hashlib
import importlib.util
import json
import sqlite3
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from frontier.historical_data import normalize_history, read_history
from frontier.historical_settlement import build_settlement_indices

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
DEFINITION_SHA = "60fb844f622b2513533dc197d813d892a88c109ea16bf9ab447d561ce85ebbd8"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def normalized_atr(close, adjusted, high, low):
    factor = adjusted/close
    previous = np.roll(adjusted, 1)
    previous[0] = np.nan
    tr = np.maximum.reduce([high*factor-low*factor, np.abs(high*factor-previous), np.abs(low*factor-previous)])
    return pd.Series(tr).rolling(14).mean().to_numpy()/factor


def source_panel(payload, record, sessions, frame=None):
    raw = payload["chart"]["result"][0]
    dates = pd.to_datetime(raw["timestamp"], unit="s", utc=True).tz_convert("America/New_York").strftime("%Y-%m-%d").tolist()
    if len(dates) != len(set(dates)):
        raise ValueError("Frozen source contains duplicate sessions")
    if frame is None:
        frame = normalize_history(payload, record["spec"], record["captured_at"], as_of=record.get("requested_as_of"))
    fields = {"close": "close", "high": "high", "low": "low", "adjusted": "adjusted_close", "volume": "volume"}
    aligned = frame.set_index("session").reindex(sessions)
    arrays = {name: aligned[column].to_numpy(dtype=float) for name, column in fields.items()}
    arrays["atr"] = normalized_atr(arrays["close"], arrays["adjusted"], arrays["high"], arrays["low"])
    invalid, wanted = [], set(sessions)
    quote = raw["indicators"]["quote"][0]
    for i, day in enumerate(dates):
        if day not in wanted:
            continue
        values = [quote[k][i] for k in ["close", "high", "low", "volume"]]+[raw["indicators"]["adjclose"][0]["adjclose"][i]]
        numeric = np.asarray(values, dtype=float)
        if not np.isfinite(numeric).all():
            invalid.append({"row": i, "session": day, "raw_values": values, "reason": "nonfinite source values omitted by existing normalizer"})
    return arrays, {"raw_rows": len(dates), "requested_sessions": len(sessions),
        "accepted_sessions": int(np.isfinite(arrays["close"]).sum()),
        "missing_or_rejected_sessions": [sessions[i] for i in np.flatnonzero(~np.isfinite(arrays["close"]))],
        "raw_invalid_rows": invalid, "actions": raw.get("events", {}),
        "split_reconstruction": frame.attrs.get("split_reconstruction"),
        "source_instrument_type": raw["meta"].get("instrumentType"),
        "no_forward_fill": True}


def main():
    assert digest(ROOT/"definition.json") == DEFINITION_SHA, "Frozen strategy definition changed"
    spec = read(ROOT/"definition.json")
    symbols = sorted(spec["universe"]+[spec["reference"]])
    inputs = spec["source"]
    inventory = read(REPO/inputs["inventory"])
    index = {row["symbol"]: row for row in read(REPO/inputs["capture_index"])}
    rows = {row["symbol"]: row for row in inventory["rows"]}
    source_files = []
    for symbol in symbols:
        record = index[symbol]
        path = REPO/inputs["capture_workspace"]/record["path"]
        assert rows[symbol]["source"]["sha256"] == record["sha256"]
        assert rows[symbol]["status"] == "available_identity_verified"
        assert path.relative_to(REPO).as_posix() == rows[symbol]["source"]["path"]
        source_files.append((path, record["sha256"]))
    assert inventory["listing_sha256"] == digest(REPO/inputs["listing"])
    assert inventory["index_sha256"] == digest(REPO/inputs["capture_index"])
    paths = [ROOT/name for name in ["definition.json", "reasoning.md", "prepare_market.py", "signals.py", "test_signals.py", "test_preparation.py"]]
    paths += [REPO/inputs[name] for name in ["inventory", "capture_index", "listing", "calendar"]]
    paths += [REPO/"src/frontier"/(name+".py") for name in ["historical_data", "historical_settlement", "scan_data"]]
    identities = {path.relative_to(REPO).as_posix(): digest(path) for path in paths}
    identities.update({path.relative_to(REPO).as_posix(): expected for path, expected in source_files})
    definition = {"strategy_sha256": DEFINITION_SHA, "inputs": identities,
                  "dependencies": {name: version(name) for name in ["numpy", "pandas", "exchange-calendars"]},
                  "mode": "causal prices/ATR/signals only, no future labels or accounts"}
    lock = sqlite3.connect(REPO/"data/historical/worker.lock.sqlite", timeout=0)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        assert not (ROOT/"preparation-completed.json").exists(), "Preserve the completed preparation"
        attempt = ROOT/"attempts"/uuid4().hex
        attempt.mkdir(parents=True)
        save(attempt/"definition.json", definition)
        calendar = [row for row in read(REPO/inputs["calendar"])["sessions"] if inputs["price_start"] <= row["session"] <= inputs["price_end"]]
        sessions = [row["session"] for row in calendar]
        arrays = {key: np.full((len(sessions), len(symbols)), np.nan) for key in ["close", "high", "low", "volume", "adjusted", "atr"]}
        audits = {}
        for j, symbol in enumerate(symbols):
            path, expected = source_files[j]
            assert digest(path) == expected, "Frozen raw source changed"
            record = index[symbol]
            frame = read_history(REPO/inputs["capture_workspace"], record)
            values, audit = source_panel(read(path), record, sessions, frame)
            for key in arrays:
                arrays[key][:, j] = values[key]
            audits[symbol] = {**audit, "source": {"path": path.relative_to(REPO).as_posix(), "sha256": expected,
                              "captured_at": record["captured_at"], "url": record["url"]}}
        arrays["settlement_index"] = build_settlement_indices(sessions, "USD")
        arrays["dates"] = np.array(sessions, dtype="datetime64[D]")
        metadata = {"sessions": sessions, "symbols": symbols, "benchmark": symbols.index("SPY"), "benchmark_symbol": "SPY",
                    "n": len(sessions), "signal_available_at": [(pd.Timestamp(row["close"])+pd.Timedelta(minutes=1)).isoformat() for row in calendar],
                    "first": sessions.index(spec["timing"]["first_signal"]), "last": sessions.index(spec["timing"]["liquidation_tail_end"]),
                    "strategy_sha256": DEFINITION_SHA}
        module_spec = importlib.util.spec_from_file_location("frozen_etf_signals", ROOT/"signals.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        signals = module.build_signals({**metadata, **arrays})
        signal_arrays = {key: value for key, value in signals.items() if key not in {"ranking", "counts"}}
        signal_arrays.update({f"{arm}_{key}": signals[key][arm] for arm in module.ARMS for key in ["ranking", "counts"]})
        np.savez(attempt/"market-arrays.npz", **arrays)
        np.savez(attempt/"signals.npz", **signal_arrays)
        save(attempt/"market-inputs.json", metadata)
        save(attempt/"source-audits.json", audits)
        for name, expected in identities.items():
            assert digest(REPO/name) == expected, "Preparation input changed: "+name
        completed = {"status": "complete", "attempt": attempt.relative_to(REPO).as_posix(),
            "files": {path.name: digest(path) for path in attempt.iterdir()}, "sessions": len(sessions), "symbols": symbols,
            "source_missing_sessions": {symbol: len(audit["missing_or_rejected_sessions"]) for symbol, audit in audits.items()},
            "causal_candidates": {arm: int(signals["counts"][arm].sum()) for arm in module.ARMS},
            "network_requests": 0, "account_runs": 0, "forward_labels_computed": False}
        save(ROOT/"preparation-completed.json", completed)
        print(json.dumps(completed, indent=2), flush=True)
    finally:
        lock.rollback()
        lock.close()


if __name__ == "__main__":
    main()
