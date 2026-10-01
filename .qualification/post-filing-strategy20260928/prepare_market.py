"""Reuse the frozen daily cache and the separately declared missing T source."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json

import joblib
import numpy as np
import pandas as pd
from frontier.historical_lab import _save

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PREP = ROOT.parent / "conditional-selection20260928/preparation"
SYMBOLS = sorted(["AAPL", "MSFT", "F", "T", "HRL", "BANF", "SPY"])


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text())


def source_rows(source, root):
    rows, seen = {}, set()
    for page in source["pages"]:
        path = root / page["raw"]
        assert digest(path) == page["sha256"] and page["status"] == 200
        body = read(path)
        assert set(body.get("bars", {})) <= {"T"}
        for bar in body.get("bars", {}).get("T", []):
            stamp = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
            local = stamp.astimezone(ZoneInfo("America/New_York"))
            assert local.hour == local.minute == local.second == 0
            session = local.date().isoformat()
            assert session not in seen
            seen.add(session)
            values = np.array([bar[k] for k in ["o", "h", "l", "c", "v"]], dtype=float)
            assert np.isfinite(values).all() and min(values[:4]) > 0 and values[4] >= 0
            assert bar["l"] <= min(bar["o"], bar["c"]) <= max(bar["o"], bar["c"]) <= bar["h"]
            rows[session] = bar
    return rows


def normalized_atr(close, adjusted, high, low):
    """The existing study's14-session adjusted true range, in current raw units."""
    factor = adjusted / close
    ahigh, alow = high * factor, low * factor
    previous = np.roll(adjusted, 1)
    previous[0] = np.nan
    tr = np.maximum.reduce([ahigh-alow, np.abs(ahigh-previous), np.abs(alow-previous)])
    return pd.Series(tr).rolling(14).mean().to_numpy() / factor


def main():
    assert not (ROOT / "market-inputs.json").exists(), "Already prepared; preserve original market inputs"
    manifest = read(PREP / "cache-manifest.json")
    cache = PREP / "market-features.joblib"
    assert digest(cache) == manifest["sha256"]
    old, _ = joblib.load(cache, mmap_mode="r")
    sessions = old["sessions"]
    calendar = read(ROOT / "calendar.json")
    assert [r["session"] for r in calendar["sessions"]] == sessions
    columns = {s: j for j, s in enumerate(SYMBOLS)}
    arrays = {k: np.full((len(sessions), len(SYMBOLS)), np.nan) for k in ["close", "adjusted", "atr"]}
    for symbol in SYMBOLS:
        if symbol == "T":
            continue
        oldj, newj = old["symbols"].index(symbol), columns[symbol]
        for key in arrays:
            arrays[key][:, newj] = old[key][:, oldj]
            assert np.array_equal(arrays[key][:, newj], old[key][:, oldj], equal_nan=True)
    source_root = ROOT / "T-price-source"
    completed = read(source_root / "completion.json")
    assert completed["status"] == "captured"
    sources = {s["adjustment"]: source_rows(s, source_root) for s in completed["sources"]}
    assert set(sources) == {"raw", "all"} and set(sources["raw"]) == set(sources["all"])
    assert set(sources["raw"]) <= set(sessions)
    j = columns["T"]
    high, low = np.full(len(sessions), np.nan), np.full(len(sessions), np.nan)
    for i, day in enumerate(sessions):
        if day in sources["raw"]:
            raw, adj = sources["raw"][day], sources["all"][day]
            arrays["close"][i, j], arrays["adjusted"][i, j] = raw["c"], adj["c"]
            high[i], low[i] = raw["h"], raw["l"]
    arrays["atr"][:, j] = normalized_atr(arrays["close"][:, j], arrays["adjusted"][:, j], high, low)
    arrays["settlement_index"] = old["settlement_index"]
    np.savez(ROOT / "market-arrays.npz", **arrays)
    requested = [d for d in sessions if "2016-01-04" <= d <= "2026-09-18"]
    evidence = read(PREP / "source-evidence.json")
    hashes = {r["symbol"]: r["sha256"] for r in evidence["source_hashes"]}
    result = {"symbols": SYMBOLS, "sessions": sessions, "benchmark": columns["SPY"],
              "source_cache_sha256": manifest["sha256"], "arrays_sha256": digest(ROOT / "market-arrays.npz"),
              "calendar_sha256": digest(ROOT / "calendar.json"), "T_completion_sha256": digest(source_root / "completion.json"),
              "source_by_symbol": {s: {"provider": "Alpaca SIP" if s == "T" else "Frozen Yahoo capture",
                  "identity": completed["request_sha256"] if s == "T" else hashes[s]} for s in SYMBOLS},
              "T_observed_sessions": len(sources["raw"]), "T_missing_requested_sessions": sorted(set(requested)-set(sources["raw"])),
              "T_adjustments_aligned": True, "prior_six_columns_unchanged": True,
              "limitation": "Mixed retrospective provider vintages; adjusted-notional marks are total-return proxies, not a qualified corporate-action cash ledger",
              "strategy_returns_computed": False}
    _save(ROOT / "market-inputs.json", result)
    print(json.dumps({k: result[k] for k in ["T_observed_sessions", "T_missing_requested_sessions", "T_adjustments_aligned", "prior_six_columns_unchanged", "arrays_sha256"]}))


if __name__ == "__main__":
    main()
