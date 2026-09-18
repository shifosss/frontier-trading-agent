"""CLI workflow integration uses injected proposals and retained local artifacts."""

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from frontier.cli import app
from frontier.data import import_dataset
from frontier.fixtures import generate_fixture


class SavedProposalProvider:
    def __init__(self):
        self.calls = 0

    def propose(self, prompt, schema, artifact_dir):
        self.calls += 1
        Path(artifact_dir).mkdir(parents=True, exist_ok=True)
        proposal = {
            "name": "saved fixture trend",
            "economic_mechanism": "trailing close momentum may persist",
            "family": "trend",
            "lookback": 2,
            "rebalance_every": 1,
            "max_weight": 0.2,
            "price_basis": "raw",
            "required_inputs": ["raw_close", "raw_open", "dated_usd_cad_fx"],
            "failure_condition": "fees dominate raw-price performance",
        }
        return {"proposal": proposal, "requested_model": "saved-test-fixture"}


def invoke(tmp_path, *args):
    return CliRunner().invoke(app, ["--workspace", str(tmp_path), *args])


def test_model_campaign_freeze_and_new_dataset_observation(tmp_path, monkeypatch):
    from frontier import research

    provider = SavedProposalProvider()
    monkeypatch.setattr(research, "CodexProvider", lambda: provider)
    source = generate_fixture(tmp_path / "source")
    bars = pd.read_csv(source / "bars.csv")
    bars.loc[bars.event_time.str[:10] <= "2025-01-10"].to_csv(source / "bars.csv", index=False)
    data_root = tmp_path / "data/datasets"
    first = import_dataset(source, data_root)
    campaign = invoke(tmp_path, "model-campaign", first.dataset_id, "--max-proposals", "1")
    assert campaign.exit_code == 0, campaign.output
    result = json.loads(campaign.stdout)
    assert provider.calls == result["call_count"] == 1
    assert result["attempts"][0]["status"] == "accepted"
    frozen = invoke(tmp_path, "freeze", result["accepted_run_ids"][0])
    assert frozen.exit_code == 0, frozen.output
    frozen_record = json.loads(frozen.stdout)
    bars.loc[bars.event_time.str[:10] <= "2025-01-13"].to_csv(source / "bars.csv", index=False)
    second = import_dataset(source, data_root)
    observation = invoke(tmp_path, "observe", frozen_record["frozen_id"], second.dataset_id)
    assert observation.exit_code == 0, observation.output
    record = json.loads(observation.stdout)
    assert record["observation_dataset_id"] == second.dataset_id
    assert record["classification"] == "historical_only"
    assert record["source_run_id"] == result["accepted_run_ids"][0]
    assert provider.calls == 1
    same = invoke(tmp_path, "observe", frozen_record["frozen_id"], first.dataset_id)
    assert same.exit_code != 0


def test_model_proposal_budget_rejected_before_any_provider_call(tmp_path, monkeypatch):
    from frontier import research

    def unavailable():
        pytest.fail("invalid proposal budget must never construct a model provider")

    monkeypatch.setattr(research, "CodexProvider", unavailable)
    result = invoke(tmp_path, "model-campaign", "a" * 64, "--max-proposals", "3")
    assert result.exit_code == 2


@pytest.mark.parametrize("kind", ["campaigns", "model-campaigns", "frozen", "observations"])
def test_saved_artifact_lists_delegate_to_shared_workflow(tmp_path, monkeypatch, kind):
    from frontier import workflow

    saved = [
        {"id": "new", "created_at": "2026-09-18T12:00:00Z"},
        {"id": "old", "created_at": "2026-09-17T12:00:00Z"},
    ]
    calls = []

    def list_saved(root, requested):
        calls.append((root, requested))
        return saved

    monkeypatch.setattr(workflow, "list_artifacts", list_saved)
    result = invoke(tmp_path, kind)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == saved
    assert calls == [(tmp_path / "artifacts", kind)]


def test_source_helpers_forward_only_read_only_parameters(tmp_path, monkeypatch):
    from frontier import sources

    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return {"cache_hit": True, "raw_path": "saved.json", "payload": []}

    monkeypatch.setattr(sources, "fetch_boc_fx", capture)
    monkeypatch.setattr(sources, "fetch_longbridge_history", capture)
    boc = invoke(tmp_path, "fetch-boc", "2026-09-01", "2026-09-17", "--refresh")
    quotes = invoke(tmp_path, "fetch-longbridge", "SPY.US", "2026-09-01", "2026-09-17")
    assert boc.exit_code == quotes.exit_code == 0
    assert calls == [
        (
            ("2026-09-01", "2026-09-17", tmp_path / "data/raw/captures"),
            {"refresh": True, "timeout": 15},
        ),
        (
            ("SPY.US", "2026-09-01", "2026-09-17", tmp_path / "data/raw/captures"),
            {"refresh": False, "timeout": 30},
        ),
    ]
    monkeypatch.setattr(sources, "import_longbridge_snapshot", capture)
    imported = invoke(tmp_path, "import-session-hourly", "--captured-at", "2026-09-18T12:00:00Z")
    assert imported.exit_code == 0, imported.output
    assert calls[-1] == ((tmp_path,), {"captured_at": "2026-09-18T12:00:00Z"})


def test_source_status_is_sanitized_and_unavailable_cli_is_actionable(tmp_path, monkeypatch):
    from frontier import sources

    status = {
        "provider": "longbridge_standalone_cli",
        "status": "expired",
        "authenticated": False,
        "hint": "Authenticate manually",
    }
    monkeypatch.setattr(sources, "longbridge_status", lambda: status)
    result = invoke(tmp_path, "source-status")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["longbridge"] == status
    assert payload["boc"]["connectivity"] == "not probed"

    def missing():
        raise FileNotFoundError("Longbridge executable missing")

    monkeypatch.setattr(sources, "longbridge_status", missing)
    failed = invoke(tmp_path, "source-status")
    assert failed.exit_code == 0
    assert json.loads(failed.stdout)["longbridge"]["status"] == "unavailable"
