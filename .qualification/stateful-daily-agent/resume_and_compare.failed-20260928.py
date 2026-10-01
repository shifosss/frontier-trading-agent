"""Resume the declared real model journal and compare with the same engine in one pass."""
import json
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits
from frontier import candidate_replay as replay
from frontier.execution_costs import get_cost_profile
from frontier.short_horizon_study import _simulate_daily, _summarize

root = Path.cwd()
evidence = root / ".qualification/stateful-daily-agent"
first = json.loads((evidence / "first-chunk.json").read_text())
prepared_cache = {}
original_prepare = replay._prepare_replay

def remember(*args):
    prepared = original_prepare(*args)
    prepared_cache.update(prepared)
    print("Saved model and source preparation completed", flush=True)
    return prepared

replay._prepare_replay = remember  # observe the real preparation; no substituted inputs
started = time.monotonic()
with threadpool_limits(limits=2):
    report = replay.replay_candidate(root, "a46d3876559b4374924e884c712e1ed7",
        end_session="2026-09-18", replay_id=first["replay_id"], chunk_sessions=17)
    p = prepared_cache
    costs = get_cost_profile("proportional", round_trip_bps=40)
    simulation = _simulate_daily(p["market"], "calibrated_ensemble", 5, 2000, 40,
        p["start"], p["end"], audit=True, signal_ranking=p["ranking"],
        signal_counts=p["counts"], signal_known=p["known"], cost_model=costs,
        process_through=p["end"])
    for name, actual in report["curves"].items():
        assert np.array_equal(np.asarray(actual), simulation[name]), name
    for name in ("state", "trade_records", "trades", "activity"):
        assert report[name] == simulation[name], name
    assert abs(report["fees"] - simulation["fees"]) < 1e-9
    sessions = p["market"]["sessions"][p["start"]:p["end"]+1]
    summary = _summarize(simulation, sessions, 2000, curves=False)
    checks = dict(replay_id=report["replay_id"], status=report["status"],
        chunk_count=report["chunk_count"], exact_curves_trades_state=True,
        trade_count=report["trades"], fees=report["fees"],
        fee_accumulation_difference=report["fees"]-simulation["fees"],
        first_chunk_held=len(first["state"]["held"]),
        first_chunk_pending=len(first["state"]["pending"]),
        first_chunk_receivables=len(first["state"]["receivables"]),
        elapsed_seconds=time.monotonic()-started)
    (evidence / "resumed-vs-one-shot.json").write_text(json.dumps(checks, indent=2)+"\n")
    (evidence / "proportional-summary.json").write_text(replay._json(summary)+"\n")
    print(json.dumps(checks), flush=True)
    print(json.dumps({k: summary.get(k) for k in ("total_return", "max_drawdown", "ending_equity")}), flush=True)
