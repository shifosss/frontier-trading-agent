"""Frozen observation chronology, immutability and idempotency."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd
import pytest

from frontier.data import import_dataset
from frontier.domain import MarketDataset, RunConfig, StrategyConfig
from frontier.fixtures import generate_fixture
from frontier.observation import _next_open, freeze_run, observe
from frontier.replay import code_identity, run_research
from frontier.store import Registry


def test_freeze_and_historical_observation_are_immutable_and_idempotent(tmp_path, monkeypatch):
    source = generate_fixture(tmp_path / "source")
    data_root = tmp_path / "datasets"
    first = import_dataset(source, data_root)
    registry = Registry(tmp_path / "registry.sqlite")
    artifacts = tmp_path / "artifacts"
    run = run_research(
        RunConfig(dataset_id=first.dataset_id, strategy=StrategyConfig(family="trend")),
        data_root,
        registry,
        artifacts,
    )
    frozen = freeze_run(run, artifacts)
    frozen_file = Path(frozen["artifact_path"])
    original = frozen_file.read_bytes()
    assert frozen["input_dataset_id"] == first.dataset_id
    assert frozen["source_run_id"] == run["id"]
    assert "artifact_path" not in json.loads(original)

    metadata_file = source / "dataset.json"
    metadata = json.loads(metadata_file.read_text())
    metadata["name"] = "second immutable vintage"
    metadata_file.write_text(json.dumps(metadata))
    bars_file = source / "bars.csv"
    bars = pd.read_csv(bars_file)
    additions = []
    for instrument in metadata["instruments"]:
        previous = bars.loc[bars.instrument_id == instrument["id"]].iloc[-1]
        calendar = xcals.get_calendar(instrument["venue"])
        close_time = calendar.session_close("2025-09-02")
        closing = float(previous.close) * 1.001
        additions.append(
            {
                "instrument_id": instrument["id"],
                "event_time": close_time.isoformat(),
                "available_at": (close_time + pd.Timedelta(minutes=1)).isoformat(),
                "open": float(previous.close),
                "high": closing * 1.005,
                "low": float(previous.close) * 0.995,
                "close": closing,
                "volume": 100_000,
            }
        )
    pd.concat([bars, pd.DataFrame(additions)], ignore_index=True).to_csv(bars_file, index=False)
    second = import_dataset(source, data_root)
    with pytest.raises(ValueError, match="new dataset version"):
        observe(frozen["frozen_id"], first.dataset_id, data_root, artifacts)
    before = datetime.now(timezone.utc)
    record = observe(frozen["frozen_id"], second.dataset_id, data_root, artifacts)
    after = datetime.now(timezone.utc)
    assert before <= datetime.fromisoformat(record["as_of"]) <= after
    assert record["classification"] == "historical_only"
    assert record["next_fill_outcome"] == "not_evaluated"
    assert record["inputs"]
    assert all("target_weight" in row and "available_at" in row for row in record["inputs"])
    assert observe(frozen["frozen_id"], second.dataset_id, data_root, artifacts) == record
    assert frozen_file.read_bytes() == original
    assert len(list((artifacts / "observations").glob("*.json"))) == 1
    passive_run = run_research(
        RunConfig(
            dataset_id=first.dataset_id,
            strategy=StrategyConfig(family="passive", lookback=1000, rebalance_every=1),
        ),
        data_root,
        registry,
        artifacts,
    )
    passive_frozen = freeze_run(passive_run, artifacts)
    passive_record = observe(passive_frozen["frozen_id"], second.dataset_id, data_root, artifacts)
    assert all(
        row["signal"] is True and row["target_weight"] > 0 for row in passive_record["inputs"]
    )
    future_id = "f" * 32
    future = json.loads(frozen_file.read_text())
    future["frozen_id"] = future_id
    future["created_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    (artifacts / "frozen" / f"{future_id}.json").write_text(json.dumps(future))
    with pytest.raises(ValueError, match="Frozen creation time"):
        observe(future_id, second.dataset_id, data_root, artifacts)
    metadata["interval"] = "1h"
    metadata["name"] = "wrong interval"
    metadata_file.write_text(json.dumps(metadata))
    wrong_interval = import_dataset(source, data_root)
    with pytest.raises(ValueError, match="interval differs"):
        observe(frozen["frozen_id"], wrong_interval.dataset_id, data_root, artifacts)
    metadata["interval"] = "1d"
    metadata["instruments"][0]["exposure_group"] = "changed-group"
    metadata["name"] = "wrong universe"
    metadata_file.write_text(json.dumps(metadata))
    wrong_universe = import_dataset(source, data_root)
    with pytest.raises(ValueError, match="instrument identities differ"):
        observe(frozen["frozen_id"], wrong_universe.dataset_id, data_root, artifacts)
    metadata["instruments"][0]["exposure_group"] = "fictional-us"
    metadata["name"] = "missing historical event"
    metadata_file.write_text(json.dumps(metadata))
    truncated = pd.read_csv(bars_file).drop(index=0)
    truncated.to_csv(bars_file, index=False)
    wrong_history = import_dataset(source, data_root)
    with pytest.raises(ValueError, match="not an event-time extension"):
        observe(frozen["frozen_id"], wrong_history.dataset_id, data_root, artifacts)
    monkeypatch.setattr("frontier.observation.code_identity", lambda: "changed-code")
    with pytest.raises(ValueError, match="code identity differs"):
        observe(frozen["frozen_id"], second.dataset_id, data_root, artifacts)


def test_freeze_rejects_unfinished_record(tmp_path):
    with pytest.raises(ValueError, match="completed"):
        freeze_run({"status": "RUNNING"}, tmp_path)


def test_next_hourly_open_must_follow_signal_availability():
    calendar = xcals.get_calendar("XNYS")
    session = "2025-08-28"
    first_hour_end = calendar.session_open(session) + pd.Timedelta(hours=1)
    available = first_hour_end + pd.Timedelta(minutes=1)
    assert (
        _next_open(available, "XNYS", "1h") == (first_hour_end + pd.Timedelta(hours=1)).isoformat()
    )
    assert (
        _next_open(calendar.session_close(session) + pd.Timedelta(minutes=1), "XNYS", "1d")
        == calendar.session_open("2025-08-29").isoformat()
    )


def test_future_source_timestamps_cannot_get_prospective_label(tmp_path, monkeypatch):
    import frontier.observation as observation_module
    from frontier.data import load_dataset

    data_root = tmp_path / "datasets"
    manifest = import_dataset(generate_fixture(tmp_path / "source"), data_root)
    source = load_dataset(data_root, manifest.dataset_id)
    addition = source.bars.loc[source.bars.instrument_id == "FICTUS.XNYS"].iloc[-1].copy()
    session_end = xcals.get_calendar("XNYS").session_close("2025-09-02")
    addition["event_time"] = session_end
    addition["available_at"] = session_end + pd.Timedelta(minutes=1)
    appended = pd.concat([source.bars, pd.DataFrame([addition])], ignore_index=True)
    new_id = "b" * 64
    later = datetime.now(timezone.utc) + timedelta(days=1)
    new_manifest = source.manifest.model_copy(
        update={
            "dataset_id": new_id,
            "mode": "historical",
            "retrieved_at": later,
            "ingested_at": later,
        }
    )
    newer = MarketDataset(new_manifest, appended, source.actions, source.fx)
    monkeypatch.setattr(
        observation_module,
        "load_dataset",
        lambda _root, dataset_id: source if dataset_id == manifest.dataset_id else newer,
    )
    monkeypatch.setattr(
        observation_module,
        "_next_open",
        lambda *_args: (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    frozen_id = "a" * 32
    config = RunConfig(
        dataset_id=manifest.dataset_id, strategy=StrategyConfig(family="passive", rebalance_every=1)
    )
    frozen = {
        "frozen_id": frozen_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_code_identity": code_identity(),
        "observation_code_identity": observation_module._observation_code_identity(),
        "input_dataset_id": manifest.dataset_id,
        "strategy_identity": "passive-fixture",
        "source_run_id": "fixture",
        "config": config.model_dump(mode="json"),
    }
    artifacts = tmp_path / "artifacts"
    (artifacts / "frozen").mkdir(parents=True)
    (artifacts / "frozen" / f"{frozen_id}.json").write_text(json.dumps(frozen))
    record = observe(frozen_id, new_id, data_root, artifacts)
    assert record["classification"] == "historical_only"
    assert record["next_fill_outcome"] == "not_evaluated"


def test_observation_identity_binds_source_history_and_implementation(monkeypatch):
    from frontier.observation import _identity

    monkeypatch.setattr("frontier.observation._observation_code_identity", lambda: "version-a")
    first = RunConfig(dataset_id="a" * 64, strategy=StrategyConfig(name="original"))
    renamed = first.model_copy(deep=True)
    renamed.strategy.name = "cosmetic rename"
    assert _identity(first) == _identity(renamed)
    changed_history = first.model_copy(update={"dataset_id": "b" * 64})
    assert _identity(first) != _identity(changed_history)
    initial = _identity(first)
    monkeypatch.setattr("frontier.observation._observation_code_identity", lambda: "version-b")
    assert _identity(first) != initial
