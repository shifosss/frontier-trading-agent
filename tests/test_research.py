"""Model attempts use typed templates and actual replay feedback."""

import json
from pathlib import Path

from frontier.data import import_dataset
from frontier.fixtures import generate_fixture
from frontier.research import run_model_campaign
from frontier.store import Registry


def proposal(**changes):
    value = {
        "name": "raw trend",
        "economic_mechanism": "slow adjustment may cause close trends to persist",
        "family": "trend",
        "lookback": 10,
        "rebalance_every": 1,
        "max_weight": 0.2,
        "price_basis": "raw",
        "required_inputs": ["raw_close", "raw_open", "dated_usd_cad_fx"],
        "failure_condition": "raw NAV return fails to exceed cash after costs",
    }
    value.update(changes)
    return value


class ScriptedProvider:
    def __init__(self, proposals):
        self.proposals = proposals
        self.prompts = []

    def propose(self, prompt, schema, artifact_dir, timeout_seconds=180):
        self.prompts.append(json.loads(prompt))
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        Path(artifact_dir).mkdir(parents=True, exist_ok=True)
        return {
            "proposal": self.proposals[len(self.prompts) - 1],
            "usage": {"input_tokens": 12, "output_tokens": 5},
            "elapsed_seconds": 0.1,
            "requested_model": "fixture",
            "cli_version": "fixture",
            "auth_method": "fixture",
            "event_log": Path(artifact_dir) / "events.jsonl",
        }


def setup(tmp_path):
    dataset_root = tmp_path / "datasets"
    manifest = import_dataset(generate_fixture(tmp_path / "source"), dataset_root)
    return (
        manifest.dataset_id,
        dataset_root,
        Registry(tmp_path / "registry.sqlite"),
        tmp_path / "runs",
    )


def test_unsupported_input_gets_precise_feedback_and_bounded_repair(tmp_path):
    dataset_id, data_root, registry, artifacts = setup(tmp_path)
    worker = ScriptedProvider(
        [
            proposal(required_inputs=["adjusted_close", "raw_open", "dated_usd_cad_fx"]),
            proposal(name="repaired raw trend"),
        ]
    )
    result = run_model_campaign(dataset_id, data_root, registry, artifacts, provider=worker)
    assert result["call_count"] == 2
    assert [a["status"] for a in result["attempts"]] == ["rejected", "accepted"]
    assert "adjusted_close" in result["attempts"][0]["reasons"][0]
    assert worker.prompts[1]["feedback_from_previous_attempt"]["status"] == "rejected"
    assert len(result["accepted_run_ids"]) == 1
    assert registry.get_run(result["accepted_run_ids"][0])["status"] == "COMPLETED"
    frozen = json.loads((Path(result["artifact_path"]) / "frozen_inputs.json").read_text())
    assert frozen["costs"] == {"commission_per_order": 1, "slippage_bps": 5}
    assert (Path(result["attempts"][1]["artifact_path"]) / "frozen_config.json").is_file()


def test_real_feedback_precedes_next_call_and_duplicate_counts(tmp_path):
    dataset_id, data_root, registry, artifacts = setup(tmp_path)
    worker = ScriptedProvider([proposal(), proposal(name="same economic strategy")])
    result = run_model_campaign(dataset_id, data_root, registry, artifacts, provider=worker)
    assert [a["status"] for a in result["attempts"]] == ["accepted", "duplicate"]
    feedback = worker.prompts[1]["feedback_from_previous_attempt"]
    actual = registry.get_run(result["accepted_run_ids"][0])["summary"]
    assert feedback["raw_price_return"] == actual["raw_price_return"]
    assert feedback["trade_count"] == actual["trade_count"]
    assert len(result["accepted_run_ids"]) == 1
    assert result["call_count"] == 2
    assert len(registry.list_runs()) == 1
