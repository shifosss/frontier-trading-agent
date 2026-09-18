import json

import pytest

from frontier.domain import RunConfig
from frontier.store import Registry


def test_running_failure_retained_and_completed_immutable(tmp_path):
    path = tmp_path / "registry.sqlite"
    registry = Registry(path)
    config = RunConfig(dataset_id="a" * 64)
    failed = registry.start_run(config, "synthetic_fixture", "test-code")
    assert Registry(path).get_run(failed)["status"] == "RUNNING"
    registry.fail_run(failed, "known corporate actions unsupported")
    record = Registry(path).get_run(failed)
    assert record["status"] == "FAILED"
    assert record["error"] == "known corporate actions unsupported"
    assert record["config"] == config.model_dump(mode="json")
    assert record["runtime_identity"]["nautilus_trader"] == "1.231.0"
    assert record["completed_at"]
    completed = registry.start_run(config, "synthetic_fixture", "test-code")
    registry.finish_run(completed, {"nav": 123.5}, "artifacts/example")
    for operation in (
        lambda: registry.finish_run(completed, {"nav": 999}, "elsewhere"),
        lambda: registry.fail_run(completed, "overwrite"),
        lambda: registry.finish_run(failed, {}, "retry"),
    ):
        with pytest.raises(ValueError, match="immutable"):
            operation()
    assert registry.get_run(completed)["summary"] == {"nav": 123.5}
    assert len(json.loads(json.dumps(registry.list_runs()))) == 2
    with pytest.raises(KeyError):
        registry.get_run("missing")


def test_global_overlap_persists_across_campaign_names(tmp_path):
    path = tmp_path / "registry.sqlite"
    registry = Registry(path)
    assert (
        registry.record_evaluation_access(
            "dataset-a", "2025-01-01", "2025-03-01", "old", "final test"
        )
        == []
    )
    previous = Registry(path).record_evaluation_access(
        "dataset-a", "2025-02-01", "2025-04-01", "renamed", "test again"
    )
    assert len(previous) == 1
    assert previous[0]["campaign_id"] == "old"
    assert (
        registry.record_evaluation_access(
            "dataset-b", "2025-02-01", "2025-04-01", "different-data", "test"
        )
        == []
    )
    assert (
        registry.record_evaluation_access(
            "dataset-a", "2025-05-01", "2025-06-01", "non-overlap", "test"
        )
        == []
    )
    touching = registry.record_evaluation_access(
        "dataset-a", "2025-04-01T00:00:00+00:00", "2025-04-02", "touch", "test"
    )
    assert [r["campaign_id"] for r in touching] == ["renamed"]
    with pytest.raises(ValueError, match="start"):
        registry.record_evaluation_access("a", "2025-03-01", "2025-01-01", "c", "test")
