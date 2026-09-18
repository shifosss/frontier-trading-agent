"""Resumable broad-market research, independent of the frozen paper mandate."""

import hashlib
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from uuid import uuid4

import exchange_calendars as xcals
import pandas as pd

from frontier.scan_data import capture_universe, normalize_chart


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _read(path, default=None):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def completed_sessions(as_of):
    stamp = pd.Timestamp(as_of)
    return {
        name: calendar.schedule.index[
            calendar.schedule["close"] + pd.Timedelta(minutes=1) <= stamp
        ][-1]
        .date()
        .isoformat()
        for name in ("XNYS", "XTSE")
        for calendar in [xcals.get_calendar(name)]
    }


def _worker_running(workspace):
    path = Path(workspace) / "data/research/worker.lock.sqlite"
    if not path.exists():
        return False
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        connection.rollback()
        return False
    except sqlite3.OperationalError as exc:
        if exc.sqlite_errorcode in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return True
        raise
    finally:
        connection.close()


def research_status(workspace):
    root = Path(workspace) / "artifacts/research-lab"
    state = _read(root / "status.json", {"status": "idle", "phase": "not_started"})
    if state["status"] == "running" and not _worker_running(workspace):
        state = {**state, "status": "interrupted", "message": "Worker stopped; resume the capture."}
    latest = _read(root / "latest.json")
    state["latest"] = latest
    state["schedule"] = "Weekday after-close follow-up; host and Codex must be available."
    return state


def research_result(workspace, run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Invalid research run ID")
    path = Path(workspace) / "artifacts/research-lab/runs" / run_id / "result.json"
    if not path.is_file():
        raise FileNotFoundError("Research result is not yet available")
    return _read(path)


def start_research_job(workspace, *, max_symbols=None, rediscover=False):
    from frontier.processes import start_background

    workspace = Path(workspace).resolve()
    current = research_status(workspace)
    if _worker_running(workspace):
        return current
    command = [
        sys.executable,
        "-u",
        "-m",
        "frontier.cli",
        "--workspace",
        str(workspace),
        "research-run",
    ]
    if max_symbols is not None:
        command.extend(["--max-symbols", str(max_symbols)])
    if rediscover:
        command.append("--rediscover")
    pid = start_background(command, workspace, workspace / "artifacts/research-lab/worker")
    return {"status": "starting", "pid": pid}


def _read_history(workspace, record):
    capture_root = workspace / "data/research/capture-workspace"
    path = (capture_root / record["path"]).resolve()
    if not path.is_relative_to(capture_root.resolve() / "data/scanner/raw"):
        raise ValueError("Research history source is outside its raw capture directory")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise ValueError("Research source bytes changed; recapture this instrument")
    return normalize_chart(json.loads(content), record["spec"], record["captured_at"])


def _read_histories(workspace, records, progress):
    # Normalization is CPU-bound (~0.2 s/name); use processes only for broad captures.
    if len(records) < 100:
        return [_read_history(workspace, record) for record in records]
    frames = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        for count, frame in enumerate(
            pool.map(partial(_read_history, workspace), records, chunksize=20), 1
        ):
            frames.append(frame)
            if count % 250 == 0 or count == len(records):
                progress(normalized=count)
    return frames


def _identity():
    digest = hashlib.sha256()
    for name in (
        "research_lab.py",
        "research_universe.py",
        "strategy_study.py",
        "forward_study.py",
        "scan_data.py",
    ):
        digest.update((Path(__file__).parent / name).read_text("utf-8").encode())
    return digest.hexdigest()


def run_research_lab(workspace, *, max_symbols=None, rediscover=False):
    """Capture all discovered candidates by default, retaining work across restarts."""
    source_identity = _identity()
    from frontier.research_universe import discover_universe, load_snapshot

    workspace = Path(workspace).resolve()
    cache_root = workspace / "data/research"
    cache_root.mkdir(parents=True, exist_ok=True)
    lock = sqlite3.connect(cache_root / "worker.lock.sqlite", timeout=0)
    try:
        lock.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError as exc:
        lock.close()
        raise RuntimeError("A broad research worker is already running") from exc
    run_id = uuid4().hex
    artifact_root = workspace / "artifacts/research-lab"
    run_root = artifact_root / "runs" / run_id
    state = {
        "run_id": run_id,
        "status": "running",
        "phase": "discovery",
        "pid": os.getpid(),
        "started_at": _now(),
        "updated_at": _now(),
        "attempted": 0,
        "usable": 0,
        "failed": 0,
    }

    def progress(**values):
        state.update(values, updated_at=_now())
        _save(artifact_root / "status.json", state)
        _save(run_root / "status.json", state)
        print(json.dumps(state), flush=True)

    try:
        progress()
        try:
            manifest = None if rediscover else load_snapshot(workspace)
        except FileNotFoundError:
            manifest = None
        if manifest is None:
            manifest = discover_universe(workspace)
        universe = manifest["instruments"]
        if max_symbols is not None:
            if max_symbols < 2:
                raise ValueError("At least two instruments are required")
            # A reproducible sample avoids interpreting alphabetical order as an investment rule.
            benchmarks = [s for s in universe if s["symbol"] in {"SPY", "XIU.TO"}]
            other = sorted(
                [s for s in universe if s not in benchmarks],
                key=lambda s: hashlib.sha256(s["symbol"].encode()).hexdigest(),
            )
            universe = benchmarks + other[: max(0, max_symbols - len(benchmarks))]
        freeze = {
            "run_id": run_id,
            "frozen_at": _now(),
            "code_identity": source_identity,
            "universe_snapshot": {
                "snapshot_id": manifest["snapshot_id"],
                "sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            },
            "instruments": universe,
            "budgets": [500, 2000, 10000, 100000],
            "max_symbols": max_symbols,
            "families": ["momentum", "trend_pullback", "mean_reversion", "breakout"],
            "horizons": [5, 10, 20],
            "cost_bps": [20, 40, 100],
            "promotion": "Research only; no automatic change to the paper policy or universe.",
        }
        _save(run_root / "definition.json", freeze)
        expected = completed_sessions(freeze["frozen_at"])
        index = _read(cache_root / "history-index.json", {})
        capture_workspace = cache_root / "capture-workspace"
        pending = [
            s
            for s in universe
            if s["symbol"] not in index
            or index[s["symbol"]].get("last_session", "") < expected[s["calendar"]]
        ]
        progress(
            phase="capture",
            discovered=len(manifest["instruments"]),
            requested=len(universe),
            cached=len(universe) - len(pending),
            pending=len(pending),
            expected_sessions=expected,
        )
        failures = []
        for offset in range(0, len(pending), 50):
            batch = pending[offset : offset + 50]
            captured, _ = capture_universe(capture_workspace, batch)
            for record in captured["captures"]:
                symbol = record["symbol"]
                if "error" in record:
                    failures.append(record)
                    continue
                index[symbol] = record
            _save(cache_root / "history-index.json", index)
            _save(run_root / "capture-failures.json", failures)
            progress(
                attempted=min(offset + 50, len(pending)),
                failed=len(failures),
                usable=sum(s["symbol"] in index for s in universe),
            )
            recent = captured["captures"]
            if sum("429" in r.get("error", "") for r in recent) >= max(2, len(recent) // 2):
                raise RuntimeError(
                    "Public data provider rate limited capture; saved data can resume later."
                )
        records = [{**index[s["symbol"]], "spec": s} for s in universe if s["symbol"] in index]
        if not records:
            raise ValueError("No usable market histories were captured")
        _save(run_root / "capture-index.json", records)
        progress(phase="evaluation", usable=len(records), failed=len(failures))
        if _identity() != source_identity:
            raise RuntimeError(
                "Research source changed during capture; resume under the final version."
            )
        frames = _read_histories(workspace, records, progress)
        frame = pd.concat(frames, ignore_index=True)
        del frames
        from frontier.strategy_study import evaluate_strategies

        if _identity() != freeze["code_identity"]:
            raise RuntimeError(
                "Research source changed during capture; resume under the final version."
            )
        freeze.update(evaluation_frozen_at=_now())
        _save(run_root / "evaluation-definition.json", freeze)
        evaluation_as_of = freeze["frozen_at"]
        result = evaluate_strategies(frame, universe, as_of=evaluation_as_of)
        result.update(
            run_id=run_id,
            created_at=_now(),
            definition=freeze,
            capture={
                "discovered": len(manifest["instruments"]),
                "requested": len(universe),
                "usable": len(records),
                "failed": failures,
                "rows": len(frame),
            },
        )
        if _identity() != freeze["code_identity"]:
            raise RuntimeError(
                "Research source changed during evaluation; repeat with a frozen version."
            )
        from frontier.forward_study import record_forward_study

        result["forward_observation"] = record_forward_study(workspace, result, frame)
        _save(run_root / "result.json", result)
        latest = {
            "run_id": run_id,
            "created_at": result["created_at"],
            "capture": result["capture"],
            "attempt_count": len(result["attempts"]),
            "summary_count": len(result["summaries"]),
        }
        _save(artifact_root / "latest.json", latest)
        progress(status="completed", phase="complete", message="Broad research results saved.")
        return result
    except Exception as exc:
        progress(status="failed", message=str(exc))
        raise
    finally:
        lock.rollback()
        lock.close()
