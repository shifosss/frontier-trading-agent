"""Predeclared strategy comparisons using the existing frozen daily cash engine."""
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

import joblib
import numpy as np

from frontier.candidate_daily import load_saved_history
from frontier.ensemble_features import build_features
from frontier.execution_costs import get_cost_profile
from frontier.historical_lab import _save
from frontier.historical_settlement import build_settlement_indices
from frontier.historical_study import _build_market, _metrics
from frontier.short_horizon_study import _simulate_daily, _summarize
from frontier.strategy_study import BOOKS

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status(phase, **details):
    item = dict(phase=phase, pid=os.getpid(), updated_at=datetime.now(timezone.utc).isoformat(), **details)
    _save(ROOT / "status.json", item)
    print(json.dumps(item), flush=True)


def benchmark(market, budget, costs, start, end):
    j = market["benchmark"]
    values = market["adjusted"][start + 1:end + 1, j]
    price = float(market["close"][start + 1, j])
    if not np.isfinite(values).all() or (values <= 0).any():
        return {"status": "incomplete", "missing": ["SPY reference prices"]}
    q = costs.maximum_quantity(math.floor(budget / price), price, budget)
    equity = np.full(end - start + 1, budget, dtype=float)
    cash = equity.copy()
    fees = 0.0
    if q:
        notional = q * price
        entry_fee = costs.fee(q, notional, "buy")
        free = budget - notional - entry_fee
        marks = notional * values / values[0]
        equity[1:] = free + marks
        cash[1:] = free
        exit_fee = costs.fee(q, float(marks[-1]), "sell")
        equity[-1] -= exit_fee
        cash[-1] = equity[-1]
        fees = entry_fee + exit_fee
    return _metrics(dict(status="complete", missing=[], equity=equity, cash=cash, fees=fees, trades=int(q > 0)), market["sessions"][start:end + 1], budget)


def main():
    from signals import build_strategy_signals

    request = read(ROOT / "request.json")
    paths = [ROOT / "request.json", ROOT / "signals.py", Path(__file__), REPO / "docs/strategy-experiment-2026-09-28.md"]
    paths += sorted((REPO / "src/frontier").glob("*.py"))
    identity = {
        "files": {p.relative_to(REPO).as_posix(): sha(p) for p in paths},
        "dependencies": {p: version(p) for p in ("numpy", "pandas", "exchange-calendars", "scikit-learn", "joblib")},
    }
    saved = ROOT / "definition.json"
    if saved.exists():
        assert read(saved) == identity, "Declared code or experiment changed; preserve this attempt."
    else:
        _save(saved, identity)
    lock_path = REPO / "data/historical/worker.lock.sqlite"
    connection = sqlite3.connect(lock_path.as_uri() + "?mode=rw", uri=True, timeout=0)
    connection.execute("BEGIN EXCLUSIVE")
    try:
        cache = ROOT / "market-signals.joblib"
        cache_manifest = ROOT / "cache-manifest.json"
        if cache.exists() and cache_manifest.exists():
            assert sha(cache) == read(cache_manifest)["sha256"]
            status("loading_verified_cache")
            market, scores, context = joblib.load(cache)
        else:
            status("loading_frozen_histories", requested_start=request["history_start"])
            frame, universe, current, evidence = load_saved_history(
                REPO, request["source_run_id"], request["last_session"], window_start=request["history_start"]
            )
            _save(ROOT / "source-evidence.json", evidence)
            status("building_market", histories=evidence["usable_usd_histories"], rows=len(frame))
            market = _build_market(frame, universe, current, "USD", None, include_activity=True)
            del frame
            gc.collect()
            specs = {s["symbol"]: s for s in universe}
            status("building_causal_features", symbols=len(market["symbols"]), sessions=market["n"])
            features = build_features(
                market,
                stock_mask=np.array([specs[s]["asset_type"] == "stock" for s in market["symbols"]]),
                liquidity_floor=BOOKS["USD"][2],
                turnover=market.pop("turnover"), dollar_volume=market.pop("dollar_volume"),
            )
            # The signal builder receives no future outcome arrays.
            features.pop("labels")
            features.pop("label_end")
            status("building_strategy_signals")
            built = build_strategy_signals(market, features)
            scores, context = built["scores"], built["context"]
            assert set(scores) == set(request["policies"])
            _save(ROOT / "signal-specification.json", built["specification"])
            del features, built
            market["settlement_index"] = build_settlement_indices(market["sessions"], "USD")
            market["dates"] = np.array(market["sessions"], dtype="datetime64[D]")
            market.pop("ranking")
            market.pop("counts")
            gc.collect()
            status("saving_reusable_market_and_signals")
            temporary = cache.with_suffix(".tmp")
            joblib.dump((market, scores, context), temporary, compress=0)
            temporary.replace(cache)
            _save(cache_manifest, {"sha256": sha(cache), "definition_sha256": sha(saved)})
        first = market["sessions"].index(request["first_signal"])
        last = market["sessions"].index(request["last_session"])
        sessions = market["sessions"][first:last + 1]
        assert first >= 273, "Insufficient pre-evaluation regime warmup"
        output = ROOT / "accounts"
        output.mkdir(exist_ok=True)
        results = []
        for policy in request["policies"]:
            values = scores[policy]
            assert values.shape == market["close"].shape
            counts = np.isfinite(values).sum(axis=1).astype(np.int32)
            ranking = np.argsort(-np.where(np.isfinite(values), values, -np.inf), axis=1, kind="stable").astype(np.int32)
            for horizon in request["holding_sessions"]:
                for profile in request["cost_profiles"]:
                    name = f"{policy}-{horizon}-{profile}"
                    path = output / f"{name}.json"
                    status("evaluating_accounts", completed=len(results), total=request["planned_accounts"], current=name)
                    if path.exists():
                        report = read(path)
                    else:
                        try:
                            simulation = _simulate_daily(
                                market, policy, horizon, request["capital_usd"], request["round_trip_bps"], first, last,
                                audit=True, signal_ranking=ranking, signal_counts=counts,
                                cost_model=get_cost_profile(profile, request["round_trip_bps"]),
                            )
                            report = _summarize(simulation, sessions, request["capital_usd"])
                        except Exception as exc:
                            report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "total_return": None, "max_drawdown": None}
                        report.update(policy=policy, horizon=horizon, cost_profile=profile, definition_sha256=sha(saved), qualification="exploratory_current_member_adjusted_vintage")
                        _save(path, report)
                    assert report["definition_sha256"] == sha(saved)
                    results.append({k:v for k,v in report.items() if k not in {"equity_curve","trade_records","period_returns"}})
            del ranking
        references = {name: benchmark(market, request["capital_usd"], get_cost_profile(name, request["round_trip_bps"]), first, last) for name in request["cost_profiles"]}
        summary = dict(request=request, results=results, references=references, cash_reference_return=0, source_evidence="source-evidence.json", definition_sha256=sha(saved))
        assert len(results) == request["planned_accounts"]
        _save(ROOT / "summary.json", summary)
        assert read(saved) == identity
        for name,digest in identity["files"].items():
            assert sha(REPO/name) == digest, name
        _save(ROOT / "result-hashes.json", {p.name: sha(p) for p in output.glob("*.json")})
        status("complete", completed=len(results), incomplete=sum(r["status"] != "complete" for r in results), summary=str(ROOT / "summary.json"))
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        status("failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        raise
