"""Immutable prospective research selections and subsequently observed daily outcomes."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from frontier.strategy_study import BOOKS, HORIZONS, STRATEGIES, cash_weighted_returns


def _write_new(path, value):
    content = json.dumps(value, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory hard-link creation publishes a complete file without replacement.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _selection_identity(plans):
    # Entry schedule follows the FIRST observation of a plan, not a later rerun.
    schedule_fields = {
        "entry_session",
        "entry_close",
        "entry_available_at",
        "exit_session",
        "exit_available_at",
    }
    return [
        {key: value for key, value in plan.items() if key not in schedule_fields} for plan in plans
    ]


def _read_snapshot(path):
    snapshot = json.loads(path.read_text("utf-8"))
    payload_hash = snapshot.pop("payload_hash", None)
    if payload_hash != "sha256:" + _digest(snapshot):
        raise ValueError(f"Forward snapshot payload integrity check failed: {path.name}")
    snapshot["payload_hash"] = payload_hash
    if snapshot["snapshot_id"] != path.stem or _digest(snapshot["identity"]) != path.stem:
        raise ValueError(f"Forward snapshot identity check failed: {path.name}")
    if _selection_identity(snapshot["plans"]) != snapshot["identity"]["selections"]:
        raise ValueError(f"Forward snapshot selections differ from frozen identity: {path.name}")
    return snapshot


def _code_identity():
    return {
        key: "sha256:"
        + hashlib.sha256(Path(__file__).with_name(filename).read_text("utf-8").encode()).hexdigest()
        for key, filename in (
            ("study_code_identity", "strategy_study.py"),
            ("forward_code_identity", "forward_study.py"),
        )
    }


def _snapshot(result, recorded):
    plans, stale = [], []
    budgets = result["methodology"]["budgets"]
    for market in result["coverage"]["markets"]:
        currency = market["currency"]
        calendar_name, benchmark, _ = BOOKS[currency]
        calendar = xcals.get_calendar(
            calendar_name,
            start=str(recorded.date() - pd.Timedelta(days=400)),
            end=str(recorded.date() + pd.Timedelta(days=100)),
        )
        schedule = calendar.schedule
        ready = schedule["close"] + pd.Timedelta(minutes=1) <= recorded
        latest = schedule.index[ready][-1].date().isoformat()
        source_session = market["latest_completed_session"]
        if source_session != latest:
            stale.append(
                {"currency": currency, "source_session": source_session, "expected_session": latest}
            )
            continue
        future = schedule.loc[schedule["close"] > recorded]
        for strategy in STRATEGIES:
            candidates = sorted(
                (
                    row
                    for row in result["latest_candidates"]
                    if row["currency"] == currency and row["strategy"] == strategy
                ),
                key=lambda row: (row["rank"], row["symbol"]),
            )
            if any(row["session"] != source_session for row in candidates):
                raise ValueError("Prospective candidate session differs from its source session")
            for budget in budgets:
                key = str(int(budget) if float(budget).is_integer() else budget)
                selected = [row for row in candidates if row["quantities_by_budget"][key] > 0][:5]
                for horizon in HORIZONS:
                    plans.append(
                        {
                            "currency": currency,
                            "strategy": strategy,
                            "horizon": horizon,
                            "budget": budget,
                            "source_session": source_session,
                            "entry_session": future.index[0].date().isoformat(),
                            "entry_close": future["close"].iloc[0].isoformat(),
                            "entry_available_at": (
                                future["close"].iloc[0] + pd.Timedelta(minutes=1)
                            ).isoformat(),
                            "exit_session": future.index[horizon].date().isoformat(),
                            "exit_available_at": (
                                future["close"].iloc[horizon] + pd.Timedelta(minutes=1)
                            ).isoformat(),
                            "selected": [row["symbol"] for row in selected],
                            "planned_quantities": [
                                row["quantities_by_budget"][key] for row in selected
                            ],
                            "signal_prices": [row["price"] for row in selected],
                            "benchmark": benchmark,
                        }
                    )
    if stale:
        return None, stale
    identity = {
        "model_signature": result["methodology"]["model_signature"],
        **_code_identity(),
        "universe": sorted(
            (row["symbol"], row["currency"]) for row in result["coverage"]["instruments"]
        ),
        "selections": _selection_identity(plans),
    }
    snapshot_id = _digest(identity)
    snapshot = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "created_at": recorded.isoformat(),
        "source_as_of": result["as_of"],
        "identity": identity,
        "plans": plans,
        "limitations": [
            "Prospective research observations only; no submitted orders or executable fills.",
            "Selections and planned quantities were frozen before the scheduled entry close.",
            "Refreshed provider-adjusted endpoint returns remain subject to later data revisions; "
            "each evaluation preserves the observations it used.",
            "Daily snapshots can have overlapping holding periods; these are independent "
            "cash-weighted cohorts, not a compounded portfolio track record.",
        ],
    }
    snapshot["payload_hash"] = "sha256:" + _digest(snapshot)
    return snapshot, []


def _observations(frame, recorded):
    data = frame[["symbol", "session", "available_at", "close", "adjusted_close"]].copy()
    data["session"] = pd.to_datetime(data.session, errors="raise").dt.strftime("%Y-%m-%d")
    if data.duplicated(["symbol", "session"]).any():
        raise ValueError("Forward study requires one observation per symbol/session")
    aware = data.available_at.astype(str).str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    data["available_at"] = pd.to_datetime(data.available_at, utc=True, errors="coerce")
    data[["close", "adjusted_close"]] = data[["close", "adjusted_close"]].apply(
        pd.to_numeric, errors="coerce"
    )
    prices = data[["close", "adjusted_close"]].to_numpy(dtype=float)
    valid = np.isfinite(prices).all(axis=1) & (prices > 0).all(axis=1)
    return data.loc[valid & aware & (data.available_at <= recorded)].set_index(
        ["symbol", "session"]
    )


def _evaluate(snapshot, observed, recorded):
    outcomes = []
    lookup = {}
    mismatches = [
        key for key, value in _code_identity().items() if snapshot["identity"].get(key) != value
    ]
    for plan in snapshot["plans"]:
        row = {
            **plan,
            "snapshot_id": snapshot["snapshot_id"],
            "recorded_at": snapshot["created_at"],
            "status": "pending",
            "stage": "awaiting_entry",
            "observations": [],
            "missing": [],
            "returns_by_cost": {},
        }
        outcomes.append(row)
        if mismatches:
            row.update(status="version_mismatch", stage="blocked", code_mismatches=mismatches)
            continue
        if recorded < pd.Timestamp(plan["entry_available_at"]):
            continue
        for symbol in [*plan["selected"], plan["benchmark"]]:
            for key in ("entry_session", "exit_session"):
                availability_key = key.replace("session", "available_at")
                if recorded < pd.Timestamp(plan[availability_key]):
                    continue
                index = (symbol, plan[key])
                if index not in lookup:
                    if index in observed.index:
                        value = observed.loc[index]
                        lookup[index] = {
                            "symbol": symbol,
                            "session": plan[key],
                            "close": float(value.close),
                            "adjusted_close": float(value.adjusted_close),
                            "available_at": value.available_at.isoformat(),
                        }
                    else:
                        lookup[index] = None
                value = lookup[index]
                if value:
                    row["observations"].append(value)
                else:
                    row["missing"].append(symbol + ":" + key.removesuffix("_session"))
        if recorded < pd.Timestamp(plan["exit_available_at"]):
            row["stage"] = "awaiting_exit"
            continue
        row["stage"] = "matured"
        if row["missing"]:
            row["status"] = "incomplete"
            continue
        entries = [lookup[(symbol, plan["entry_session"])] for symbol in plan["selected"]]
        exits = [lookup[(symbol, plan["exit_session"])] for symbol in plan["selected"]]
        benchmark_entry = lookup[(plan["benchmark"], plan["entry_session"])]
        benchmark_exit = lookup[(plan["benchmark"], plan["exit_session"])]
        row["returns_by_cost"] = cash_weighted_returns(
            plan["budget"],
            plan["planned_quantities"],
            [entry["close"] for entry in entries],
            [
                exit_["adjusted_close"] / entry["adjusted_close"] - 1
                for entry, exit_ in zip(entries, exits)
            ],
            benchmark_entry["close"],
            benchmark_exit["adjusted_close"] / benchmark_entry["adjusted_close"] - 1,
        )
        row["status"] = "complete"
    return outcomes


def record_forward_study(workspace, result, frame):
    """Freeze fresh selections now and append a new evaluation of every saved snapshot.

    The real recording time, not the historical study cutoff, determines prospective
    entry eligibility. Old plans are evaluated from stored selections without reranking.
    """
    recorded = pd.Timestamp(datetime.now(timezone.utc))
    root = Path(workspace) / "artifacts/forward-studies"
    snapshot, stale = _snapshot(result, recorded)
    created = False
    if snapshot is not None:
        path = root / "snapshots" / (snapshot["snapshot_id"] + ".json")
        try:
            _write_new(path, snapshot)
            created = True
        except FileExistsError:
            snapshot = _read_snapshot(path)
    snapshots = [_read_snapshot(path) for path in sorted((root / "snapshots").glob("*.json"))]
    plans = [plan for saved in snapshots for plan in saved["plans"]]
    symbols = {symbol for plan in plans for symbol in [*plan["selected"], plan["benchmark"]]}
    sessions = {plan[key] for plan in plans for key in ("entry_session", "exit_session")}
    endpoints = frame.loc[frame.symbol.isin(symbols) & frame.session.isin(sessions)]
    observed = _observations(endpoints, recorded)
    outcomes = [row for saved in snapshots for row in _evaluate(saved, observed, recorded)]
    evaluation = {
        "schema_version": 1,
        "evaluated_at": recorded.isoformat(),
        "cohorts": outcomes,
        "input_rows": len(frame),
        "valid_available_endpoint_rows": len(observed),
        "stale_markets": stale,
    }
    evaluation_path = root / "evaluations" / (uuid4().hex + ".json")
    _write_new(evaluation_path, evaluation)
    return {
        "snapshot_id": snapshot["snapshot_id"] if snapshot else None,
        "snapshot_created": created,
        "created_at": recorded.isoformat(),
        "snapshot_recorded_at": snapshot["created_at"] if snapshot else None,
        "status": "skipped_stale_signal"
        if stale
        else "recorded"
        if created
        else "already_recorded",
        "stale_markets": stale,
        "planned_cohorts": len(snapshot["plans"]) if snapshot else 0,
        "tracked_cohorts": len(outcomes),
        "pending_count": sum(row["status"] == "pending" for row in outcomes),
        "complete_count": sum(row["status"] == "complete" for row in outcomes),
        "incomplete_count": sum(row["status"] == "incomplete" for row in outcomes),
        "version_mismatch_count": sum(row["status"] == "version_mismatch" for row in outcomes),
        "evaluation_path": str(evaluation_path.relative_to(workspace)).replace("\\", "/"),
    }
