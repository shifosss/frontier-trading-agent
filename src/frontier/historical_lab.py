"""Durable historical experiments; no broker routes or forward-data dependency."""

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from frontier.historical_data import DEFAULT_START, capture_histories, read_history
from frontier.research_lab import _read, completed_sessions


def _save(path, value):
    # Stream large daily equity audit arrays instead of materializing a second JSON string.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, allow_nan=False, separators=(",", ":"))
    # Windows readers/virus scanners can briefly deny replacement of an open file.
    for attempt in range(6):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def compact_result(value):
    if isinstance(value, dict):
        return {
            key: compact_result(item)
            for key, item in value.items()
            if key not in {"equity_curve", "trade_batches", "selection_candidates"}
        }
    if isinstance(value, list):
        return [compact_result(item) for item in value]
    return value


def _now():
    return datetime.now(timezone.utc).isoformat()


_LOADED_CAPTURE_IDENTITIES = {
    name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
    for name in ("historical_lab.py", "historical_data.py", "research_lab.py", "scan_data.py")
}


def _identity():
    names = (
        "historical_lab.py",
        "historical_data.py",
        "historical_study.py",
        "strategy_study.py",
        "research_lab.py",
        "scan_data.py",
    )
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((Path(__file__).parent / name).read_text("utf-8").encode())
    return digest.hexdigest()


def _running(workspace):
    path = Path(workspace).resolve() / "data/historical/worker.lock.sqlite"
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


def historical_status(workspace):
    root = Path(workspace) / "artifacts/historical-lab"
    state = _read(root / "status.json", {"status": "idle", "phase": "not_started"})
    if state["status"] == "running" and not _running(workspace):
        state = {**state, "status": "interrupted", "message": "Worker stopped; resume saved data."}
    state["latest"] = _read(root / "latest.json")
    return state


def historical_result_path(workspace, run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Invalid historical run ID")
    path = Path(workspace) / "artifacts/historical-lab/runs" / run_id / "result.json"
    if not path.is_file():
        raise FileNotFoundError("Historical result is not yet available")
    return path


def historical_result(workspace, run_id, *, compact=False):
    path = historical_result_path(workspace, run_id)
    if compact:
        saved = path.with_name("summary.json")
        return _read(saved) if saved.exists() else compact_result(_read(path))
    return _read(path)


def start_historical_job(workspace, *, rediscover=False):
    from frontier.processes import start_background

    workspace = Path(workspace).resolve()
    if _running(workspace):
        return historical_status(workspace)
    command = [
        sys.executable,
        "-u",
        "-m",
        "frontier.cli",
        "--workspace",
        str(workspace),
        "historical-run",
    ]
    if rediscover:
        command.append("--rediscover")
    pid = start_background(command, workspace, workspace / "artifacts/historical-lab/worker")
    return {"status": "starting", "pid": pid}


def run_historical_lab(workspace, *, start=DEFAULT_START, rediscover=False, capture_only=False):
    """Acquire long histories, then freeze and evaluate all declared retrospective tests."""
    from frontier.research_universe import discover_universe, load_snapshot

    start = pd.Timestamp(start).date().isoformat()
    workspace = Path(workspace).resolve()
    cache = workspace / "data/historical"
    cache.mkdir(parents=True, exist_ok=True)
    lock = sqlite3.connect(cache / "worker.lock.sqlite", timeout=0)
    try:
        lock.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError as exc:
        lock.close()
        raise RuntimeError("A historical worker is already running") from exc
    run_id = uuid4().hex
    root = workspace / "artifacts/historical-lab"
    run_root = root / "runs" / run_id
    state = {
        "run_id": run_id,
        "status": "running",
        "phase": "discovery",
        "pid": os.getpid(),
        "started_at": _now(),
        "requested_start": start,
    }

    def progress(**values):
        state.update(values, updated_at=_now())
        _save(root / "status.json", state)
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
        as_of = _now()
        definition = {
            "run_id": run_id,
            "frozen_at": as_of,
            "requested_start": start,
            "universe_snapshot": manifest["snapshot_id"],
            "universe_sha256": hashlib.sha256(
                json.dumps(manifest, sort_keys=True).encode()
            ).hexdigest(),
            "instruments": universe,
            "capture_only": capture_only,
            "data_source_identity": hashlib.sha256(
                Path(__file__).with_name("historical_data.py").read_bytes()
            ).hexdigest(),
        }
        _save(run_root / "capture-definition.json", definition)
        expected = completed_sessions(as_of)
        index = _read(cache / "history-index.json", {})
        pending = [
            s
            for s in universe
            if s["symbol"] not in index
            or index[s["symbol"]].get("requested_start", "9999") > start
            or index[s["symbol"]].get("last_session", "") < expected[s["calendar"]]
        ]
        progress(
            phase="capture",
            discovered=len(universe),
            requested=len(universe),
            cached=len(universe) - len(pending),
            attempted=0,
            failed=0,
        )
        failures = []
        capture_workspace = cache / "capture-workspace"
        for offset in range(0, len(pending), 50):
            records = capture_histories(
                capture_workspace, pending[offset : offset + 50], start=start, as_of=as_of
            )
            for record in records:
                if "error" in record:
                    failures.append(record)
                else:
                    index[record["symbol"]] = record
            _save(cache / "history-index.json", index)
            _save(run_root / "capture-failures.json", failures)
            progress(
                attempted=min(offset + 50, len(pending)),
                failed=len(failures),
                usable=sum(s["symbol"] in index for s in universe),
            )
            if sum("429" in r.get("error", "") for r in records) >= max(2, len(records) // 2):
                raise RuntimeError(
                    "Public provider rate limited capture; saved histories can resume."
                )
        records = [
            {**index[s["symbol"]], "spec": s}
            for s in universe
            if s["symbol"] in index and index[s["symbol"]].get("requested_start", "9999") <= start
        ]
        _save(run_root / "capture-index.json", records)
        if not records:
            raise ValueError("No usable historical data was captured")
        if capture_only:
            progress(
                status="completed",
                phase="captured",
                message="Long histories saved; evaluation not started.",
            )
            return {"run_id": run_id, "captured": len(records)}
        if any(
            hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != digest
            for name, digest in _LOADED_CAPTURE_IDENTITIES.items()
        ):
            raise RuntimeError(
                "Historical capture code changed; restart to evaluate saved sources."
            )
        from frontier.historical_study import evaluate_historical

        # Capture and evaluation are distinct stages: the experiment version is frozen
        # before any evaluation, while immutable raw inputs retain their capture version.
        identity = _identity()
        definition.update(evaluation_frozen_at=_now(), code_identity=identity)
        _save(run_root / "definition.json", definition)
        result = None
        row_count = 0
        coverage = []
        normalization_audit = []
        for currency in ("USD", "CAD"):
            selected = [r for r in records if r["spec"]["currency"] == currency]
            if not selected:
                continue
            progress(
                phase="normalization",
                currency=currency,
                normalized=0,
                market_histories=len(selected),
            )
            frames = []
            for count, record in enumerate(selected, 1):
                normalized = read_history(capture_workspace, record)
                normalization_audit.append({"symbol": record["symbol"], **normalized.attrs})
                frames.append(normalized)
                if count % 250 == 0:
                    progress(normalized=count)
            _save(run_root / "normalization-audit.json", normalization_audit)
            frame = pd.concat(frames, ignore_index=True)
            del frames, normalized
            # Membership symbols with unavailable histories remain in the declared universe.
            specs = [s for s in universe if s["currency"] == currency]
            row_count += len(frame)
            coverage.append(
                {
                    "currency": currency,
                    "histories": len(selected),
                    "rows": len(frame),
                    "first_session": frame.session.min(),
                    "last_session": frame.session.max(),
                }
            )
            progress(phase="evaluation", normalized=len(selected), rows=row_count)
            part = evaluate_historical(
                frame, specs, as_of=as_of, progress=lambda value: progress(**value)
            )
            del frame
            if _identity() != identity:
                raise RuntimeError(
                    "Historical source changed during evaluation; repeat under a frozen version."
                )
            _save(run_root / f"{currency.lower()}-result.json", part)
            if result is None:
                result = part
            else:
                for key in ("portfolios", "benchmarks", "walk_forward"):
                    result[key].extend(part[key])
                for key in ("markets", "instruments"):
                    result["coverage"][key].extend(part["coverage"][key])
        result.update(
            run_id=run_id,
            created_at=_now(),
            definition=definition,
            capture={
                "discovered": len(universe),
                "usable": len(records),
                "rows": row_count,
                "failed": failures,
                "markets": coverage,
                "stale_symbols": [
                    r["symbol"]
                    for r in records
                    if r["last_session"] < expected[r["spec"]["calendar"]]
                ],
            },
        )
        _save(run_root / "result.json", result)
        summary = compact_result(result)
        for full, brief in zip(result["walk_forward"], summary["walk_forward"]):
            for source, target in (
                (full, brief),
                (full.get("benchmark", {}), brief.get("benchmark", {})),
            ):
                points = source.get("equity_curve", [])
                by_month = {row["session"][:7]: row for row in points}
                sampled = list(by_month.values())
                if points and (not sampled or sampled[0] != points[0]):
                    sampled.insert(0, points[0])
                target["monthly_equity_curve"] = sampled
        _save(run_root / "summary.json", summary)
        _save(
            root / "latest.json",
            {"run_id": run_id, "created_at": result["created_at"], "capture": result["capture"]},
        )
        progress(
            status="completed",
            phase="complete",
            message="Historical portfolio and walk-forward tests saved.",
        )
        return result
    except Exception as exc:
        progress(status="failed", message=str(exc))
        raise
    finally:
        lock.rollback()
        lock.close()
