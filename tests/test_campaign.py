import json
from pathlib import Path

import pytest

from frontier.campaign import run_campaign, verify_replay
from frontier.data import import_dataset
from frontier.domain import RunConfig, StrategyConfig
from frontier.fixtures import generate_fixture
from frontier.replay import run_research
from frontier.store import Registry


def test_campaign_freezes_all_attempts_and_global_exposure(tmp_path):
    source = generate_fixture(tmp_path / "source")
    root = tmp_path / "datasets"
    manifest = import_dataset(source, root)
    registry = Registry(tmp_path / "registry.sqlite")
    artifacts = tmp_path / "artifacts"
    strategies = [StrategyConfig(family="cash"), StrategyConfig(family="passive")]
    campaign = run_campaign(manifest.dataset_id, root, registry, artifacts, strategies)
    assert campaign["trial_count"] == 2
    assert len(campaign["run_ids"]) == len(campaign["ranking"]) == 2
    frozen = json.loads(
        (artifacts / campaign["campaign_id"] / "frozen_candidates.json").read_text()
    )
    assert frozen["candidate_count"] == 2
    assert frozen["frozen_at"] <= registry.list_runs()[0]["created_at"]
    assert verify_replay(campaign["run_ids"][0], root, registry)["identical"]
    second = run_campaign(manifest.dataset_id, root, registry, artifacts, strategies)
    assert len(second["evaluation_access"]["prior_overlaps"]) == 4
    # All unsupported-action attempts still have durable failed trial records.
    metadata = json.loads((source / "dataset.json").read_text())
    metadata["corporate_actions_status"] = "unknown"
    (source / "dataset.json").write_text(json.dumps(metadata))
    unknown = import_dataset(source, root)
    failed = run_campaign(unknown.dataset_id, root, registry, artifacts, strategies)
    assert len(failed["trials"]) == 2
    assert all(row["status"] == "FAILED" for row in failed["trials"])
    assert failed["ranking"] == []


def test_registry_result_and_report_contract(tmp_path):
    root = tmp_path / "datasets"
    manifest = import_dataset(generate_fixture(tmp_path / "source"), root)
    registry = Registry(tmp_path / "registry.sqlite")
    record = run_research(
        RunConfig(dataset_id=manifest.dataset_id), root, registry, tmp_path / "artifacts"
    )
    directory = Path(record["artifact_path"])
    result = json.loads((directory / "result.json").read_text())
    assert record["summary"] == result["summary"]
    assert (directory / "report.html").is_file()
    assert result["schema_version"] == 1
    assert result["engine_identity"]["account_count"] == 1


@pytest.mark.parametrize("changed_module", ["metrics.py", "signals.py"])
def test_source_identity_survives_checkout_line_endings_but_detects_edits(
    tmp_path, monkeypatch, changed_module
):
    import frontier.replay as replay

    original = Path(replay.__file__).parent
    package = tmp_path / "src" / "frontier"
    package.mkdir(parents=True)
    for source in original.glob("*.py"):
        (package / source.name).write_bytes(source.read_text(encoding="utf-8").encode("utf-8"))
    lock = original.parent.parent / "uv.lock"
    (tmp_path / "uv.lock").write_bytes(lock.read_text(encoding="utf-8").encode("utf-8"))
    monkeypatch.setattr(replay, "__file__", str(package / "replay.py"))
    before = replay.code_identity()
    for path in [*package.glob("*.py"), tmp_path / "uv.lock"]:
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert replay.code_identity() == before
    changed = package / changed_module
    changed.write_bytes(changed.read_bytes() + b"\nCHANGED_IMPLEMENTATION = True\n")
    assert replay.code_identity() != before
