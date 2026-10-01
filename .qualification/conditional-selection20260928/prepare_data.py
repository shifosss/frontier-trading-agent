"""Prepare the existing frozen capture; no conditional fit or account evaluation."""
import gc
import hashlib
import json
import os
import sqlite3
import traceback
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np

from frontier.candidate_daily import load_saved_history
from frontier.ensemble_features import build_features
from frontier.historical_settlement import build_settlement_indices
from frontier.historical_study import _build_market
from frontier.strategy_study import BOOKS

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
OUT = ROOT / "preparation"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(piece)
    return result.hexdigest()


def save(name, value):
    path = OUT / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def status(phase, **details):
    value = dict(phase=phase, pid=os.getpid(), at=datetime.now(timezone.utc).isoformat(), **details)
    save("status.json", value)
    print(json.dumps(value), flush=True)


def main():
    OUT.mkdir(exist_ok=True)
    paths = [Path(__file__)] + [REPO / "src/frontier" / (name + ".py") for name in (
        "candidate_daily", "historical_data", "historical_lab", "historical_study",
        "strategy_study", "ensemble_features", "historical_settlement",
    )]
    definition = {
        "source_run_id": "814780d48b4141b9a82a3fb917d1b85a",
        "history_start": "2010-01-04", "first_signal": "2016-01-04", "last_session": "2026-09-18",
        "files": {p.relative_to(REPO).as_posix(): digest(p) for p in paths},
        "dependencies": {p: version(p) for p in ("numpy", "pandas", "exchange-calendars", "joblib")},
        "mode": "data/causal-feature preparation only; no conditional learner or account outcomes",
    }
    existing = OUT / "definition.json"
    if existing.exists():
        assert json.loads(existing.read_text()) == definition, "Preserve changed preparation attempt"
    else:
        save("definition.json", definition)
    lock = sqlite3.connect((REPO / "data/historical/worker.lock.sqlite").as_uri() + "?mode=rw", uri=True, timeout=0)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        cache, manifest = OUT / "market-features.joblib", OUT / "cache-manifest.json"
        if cache.exists() and manifest.exists():
            expected = json.loads(manifest.read_text())
            assert digest(cache) == expected["sha256"]
            status("complete", reused_verified_cache=True)
            return
        status("loading_frozen_histories")
        frame, universe, current, evidence = load_saved_history(
            REPO, definition["source_run_id"], definition["last_session"], window_start=definition["history_start"]
        )
        save("source-evidence.json", evidence)
        status("building_market", rows=len(frame), usable_histories=evidence["usable_usd_histories"])
        market = _build_market(frame, universe, current, "USD", None, include_activity=True)
        del frame
        gc.collect()
        first = market["sessions"].index(definition["first_signal"])
        last = market["sessions"].index(definition["last_session"])
        assert first - 756 >= 273, "Insufficient pre-fit feature warmup"
        benchmark = market["adjusted"][:first + 1, market["benchmark"]]
        assert np.isfinite(benchmark).all() and (benchmark > 0).all(), "Missing benchmark warmup"
        blocks = []
        for start in range(first, last + 1, 252):
            boundaries = dict(fit_start=start-756, calibration_start=start-252, test_start=start, test_end=min(last,start+251))
            blocks.append({**boundaries, "sessions": {k: market["sessions"][i] for k,i in boundaries.items()}})
        save("coverage-preflight.json", dict(passed=True, first_signal_index=first, earliest_fit_index=first-756,
             available_feature_warmup=first-756, required_feature_warmup=273, test_sessions=last-first+1,
             total_symbols=len(market["symbols"]), blocks=blocks))
        specs = {s["symbol"]: s for s in universe}
        status("building_causal_features", symbols=len(market["symbols"]), sessions=market["n"])
        features = build_features(market, stock_mask=np.array([specs[s]["asset_type"] == "stock" for s in market["symbols"]]),
                                  liquidity_floor=BOOKS["USD"][2], turnover=market.pop("turnover"), dollar_volume=market.pop("dollar_volume"))
        market["settlement_index"] = build_settlement_indices(market["sessions"], "USD")
        market["dates"] = np.array(market["sessions"], dtype="datetime64[D]")
        market.pop("ranking")
        market.pop("counts")
        status("saving_reusable_cache")
        temporary = cache.with_suffix(".tmp")
        joblib.dump((market, features), temporary, compress=0)
        temporary.replace(cache)
        save("cache-manifest.json", {"sha256": digest(cache), "definition_sha256": digest(existing), "bytes": cache.stat().st_size})
        for name, expected in definition["files"].items():
            assert digest(REPO/name) == expected, name
        status("complete", test_blocks=len(blocks), test_sessions=last-first+1, cache_bytes=cache.stat().st_size)
    finally:
        lock.rollback()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        OUT.mkdir(exist_ok=True)
        status("failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        raise
