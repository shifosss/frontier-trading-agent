"""Immutable frozen strategies and as-of, no-order observation records."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd

from frontier.data import as_of, fx_as_of, load_dataset, session_endpoints
from frontier.domain import CALENDAR_BY_VENUE, RunConfig
from frontier.replay import code_identity
from frontier.signals import target_for_history


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _observation_code_identity() -> str:
    source = Path(__file__).read_text(encoding="utf-8")
    return hashlib.sha256((code_identity() + source).encode("utf-8")).hexdigest()


def _identity(config: RunConfig) -> str:
    identity = {
        "strategy": config.strategy.model_dump(exclude={"name"}),
        "source_dataset": config.dataset_id,
        "observation_code": _observation_code_identity(),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _write_once(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, allow_nan=False)


def freeze_run(run_record: dict, artifact_root: Path) -> dict:
    """Freeze a completed, artifact-backed run without modifying its replay."""
    if run_record.get("status") != "COMPLETED":
        raise ValueError("Only a completed replay run can be frozen")
    root = Path(artifact_root).resolve()
    source = Path(run_record["artifact_path"]).resolve()
    if not source.is_relative_to(root):
        raise ValueError("Run artifact must be inside artifact_root")
    result = json.loads((source / "result.json").read_text(encoding="utf-8"))
    config = RunConfig.model_validate(run_record["config"])
    if result.get("config") != config.model_dump(mode="json"):
        raise ValueError("Run artifact configuration differs from registry record")
    if result.get("summary") != run_record["summary"]:
        raise ValueError("Run artifact summary differs from registry record")
    if run_record.get("code_identity") != code_identity():
        raise ValueError("Run code identity is stale; replay with current code before freezing")
    frozen_id = uuid.uuid4().hex
    frozen = {
        "frozen_id": frozen_id,
        "created_at": _now().isoformat(),
        "source_run_id": run_record["id"],
        "source_run_artifact": str(source),
        "input_dataset_id": config.dataset_id,
        "strategy_identity": _identity(config),
        "source_code_identity": run_record["code_identity"],
        "observation_code_identity": _observation_code_identity(),
        "source_dataset": result["dataset"],
        "config": config.model_dump(mode="json"),
        "source_summary": run_record["summary"],
        "status": "frozen_exploratory_configuration",
        "authority": "observation only; no broker orders or automatic promotion",
    }
    path = root / "frozen" / f"{frozen_id}.json"
    _write_once(path, frozen)
    frozen["artifact_path"] = str(path)
    return frozen


def _next_open(available_at: pd.Timestamp, venue: str, interval: str) -> str:
    """Match replay's next bar opening, strictly after signal availability."""
    calendar = xcals.get_calendar(CALENDAR_BY_VENUE[venue])
    local_date = available_at.tz_convert("America/Toronto").date()
    sessions = calendar.sessions_in_range(
        pd.Timestamp(local_date),
        pd.Timestamp(local_date) + pd.Timedelta(days=14),
    )
    for session in sessions:
        endpoints = session_endpoints(calendar, session, interval)
        for index, _ in enumerate(endpoints):
            opening = calendar.session_open(session) if index == 0 else endpoints[index - 1]
            if opening > available_at:
                return opening.isoformat()
    raise ValueError(f"No eligible {interval} opening after {available_at}")


def _check_compatible_history(source, current) -> None:
    if source.manifest.interval != current.manifest.interval:
        raise ValueError("Observation interval differs from frozen run dataset")

    def identities(dataset):
        return sorted(
            (i.id, i.venue, i.currency, i.exposure_group) for i in dataset.manifest.instruments
        )

    if identities(source) != identities(current):
        raise ValueError("Observation instrument identities differ from frozen run dataset")
    appended = False
    for instrument in source.manifest.instruments:
        old = sorted(set(source.bars.loc[source.bars.instrument_id == instrument.id, "event_time"]))
        new = sorted(
            set(current.bars.loc[current.bars.instrument_id == instrument.id, "event_time"])
        )
        if new[: len(old)] != old:
            raise ValueError(
                f"Observation history is not an event-time extension for {instrument.id}"
            )
        appended = appended or len(new) > len(old)
    if not appended:
        raise ValueError("Observation dataset has no new bar event after frozen input")


def observe(
    frozen_id: str,
    dataset_id: str,
    data_root: Path,
    artifact_root: Path,
) -> dict:
    """Record a decision using only data available at the actual current time."""
    if (
        not isinstance(frozen_id, str)
        or len(frozen_id) != 32
        or any(character not in "0123456789abcdef" for character in frozen_id)
    ):
        raise ValueError("frozen_id must be a 32-character lowercase hex identifier")
    root = Path(artifact_root).resolve()
    frozen = json.loads((root / "frozen" / f"{frozen_id}.json").read_text(encoding="utf-8"))
    if frozen.get("frozen_id") != frozen_id:
        raise ValueError("Frozen identity mismatch")
    if dataset_id == frozen["input_dataset_id"]:
        raise ValueError("Observation needs a new dataset version, distinct from the source run")
    config = RunConfig.model_validate(frozen["config"])
    if frozen.get("source_code_identity") != code_identity():
        raise ValueError("Frozen replay code identity differs from current code")
    if frozen.get("observation_code_identity") != _observation_code_identity():
        raise ValueError("Frozen observation code differs; freeze a configuration again")
    source_dataset = load_dataset(data_root, frozen["input_dataset_id"])
    dataset = load_dataset(data_root, dataset_id)
    _check_compatible_history(source_dataset, dataset)
    current = _now()
    frozen_created = pd.Timestamp(frozen["created_at"])
    if frozen_created.tzinfo is None or frozen_created > pd.Timestamp(current):
        raise ValueError("Frozen creation time must be timezone-aware and no later than as_of")
    snapshot = as_of(dataset.bars, current)
    if snapshot.empty:
        raise ValueError("No bars were available at the actual observation time")
    if not any(
        snapshot.loc[snapshot.instrument_id == instrument.id, "event_time"].max()
        > source_dataset.bars.loc[
            source_dataset.bars.instrument_id == instrument.id, "event_time"
        ].max()
        for instrument in source_dataset.manifest.instruments
    ):
        raise ValueError("No appended bar was available at the actual observation time")
    fx = fx_as_of(dataset.fx, current)
    if fx is None:
        raise ValueError("No dated FX rate available at the actual observation time")
    groups = Counter(i.exposure_group for i in dataset.manifest.instruments)
    inputs: list[dict[str, Any]] = []
    for instrument in dataset.manifest.instruments:
        history = snapshot.loc[snapshot.instrument_id == instrument.id].sort_values("event_time")
        if history.empty:
            raise ValueError(f"No available bars for {instrument.id}")
        latest = history.iloc[-1]
        lookback = config.strategy.lookback
        due = (len(history) - 1) % config.strategy.rebalance_every == 0
        closes = history.close.iloc[-lookback:]
        signal: bool | None = None
        target_weight: float | None = None
        reason = "rebalance not due; existing position unknown"
        if due:
            signal, target_weight, reason = target_for_history(
                history.close, config.strategy, groups, instrument.exposure_group
            )
        inputs.append(
            {
                "instrument_id": instrument.id,
                "event_time": latest.event_time.isoformat(),
                "available_at": latest.available_at.isoformat(),
                "raw_close": float(latest.close),
                "known_close_window": [float(value) for value in closes],
                "history_count": len(history),
                "next_eligible_open": _next_open(
                    latest.available_at, instrument.venue, dataset.manifest.interval
                ),
                "rebalance_due": due,
                "signal": signal,
                "target_weight": target_weight,
                "reason": reason,
            }
        )
    event_key = [(row["instrument_id"], row["event_time"]) for row in inputs]
    observation_id = hashlib.sha256(
        json.dumps([frozen["strategy_identity"], event_key], sort_keys=True).encode()
    ).hexdigest()
    path = root / "observations" / f"{observation_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    prospective = (
        dataset.manifest.mode == "historical"
        and dataset.manifest.retrieved_at <= current
        and dataset.manifest.ingested_at <= current
        and frozen_created <= pd.Timestamp(current)
        and all(pd.Timestamp(row["next_eligible_open"]) > pd.Timestamp(current) for row in inputs)
    )
    record = {
        "observation_id": observation_id,
        "frozen_id": frozen_id,
        "strategy_identity": frozen["strategy_identity"],
        "source_run_id": frozen["source_run_id"],
        "input_dataset_id": frozen["input_dataset_id"],
        "observation_dataset_id": dataset_id,
        "as_of": current.isoformat(),
        "classification": "prospective_pending_next_open" if prospective else "historical_only",
        "next_fill_outcome": "pending" if prospective else "not_evaluated",
        "corporate_actions_status": dataset.manifest.corporate_actions_status,
        "known_actions_present": not dataset.actions.empty,
        "decision_timing": config.decision_timing,
        "fill_timing": config.fill_timing,
        "inputs": inputs,
        "fx": {
            "event_time": fx.event_time.isoformat(),
            "available_at": fx.available_at.isoformat(),
            "usd_cad": float(fx.usd_cad),
        },
        "limitations": [
            "No position state, broker order, execution, or outcome is inferred",
            "Prospective label requires source retrieval and ingestion before actual as_of, "
            "and every next eligible open after it",
            "Historical replay and inferred availability do not establish future performance",
        ],
        "artifact_path": str(path),
    }
    try:
        _write_once(path, record)
    except FileExistsError:
        return json.loads(path.read_text(encoding="utf-8"))
    return record
