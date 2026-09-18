"""Exercise workflow routing with real replay and a deterministic test provider."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frontier.web import _ENGINE_LOCK, create_app
from frontier.workflow import list_artifacts


class ProviderFixture:
    def propose(self, prompt, schema, artifact_dir):
        return {
            "proposal": {
                "name": "HTTP fixture trend",
                "economic_mechanism": "Test fixture",
                "family": "trend",
                "lookback": 10,
                "rebalance_every": 5,
                "max_weight": 0.2,
                "price_basis": "raw",
                "required_inputs": ["raw_close", "raw_open", "dated_usd_cad_fx"],
                "failure_condition": "Test fixture",
            },
            "usage": {"input_tokens": 12, "output_tokens": 5},
            "auth_method": "test fixture, not a model call",
        }


def test_model_campaign_freeze_and_saved_reload(tmp_path, monkeypatch):
    monkeypatch.setattr("frontier.research.CodexProvider", ProviderFixture)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        dataset = client.post("/api/demo", json={}).json()["dataset_id"]
        payload = {"dataset_id": dataset, "max_proposals": 2}
        response = client.post("/api/model-campaigns", json=payload)
        assert response.status_code == 200, response.text
        campaign = response.json()
        assert [a["status"] for a in campaign["attempts"]] == ["accepted", "duplicate"]
        assert campaign["call_count"] == 2
        assert client.get("/api/model-campaigns").json() == [campaign]
        run_id = campaign["accepted_run_ids"][0]
        frozen_response = client.post("/api/frozen", json={"run_id": run_id})
        assert frozen_response.status_code == 200, frozen_response.text
        frozen = frozen_response.json()
        saved = client.get("/api/frozen").json()
        assert saved[0]["frozen_id"] == frozen["frozen_id"]
        assert saved[0]["source_run_id"] == run_id
        rejected = client.post(
            "/api/observations",
            json={
                "frozen_id": frozen["frozen_id"],
                "dataset_id": dataset,
            },
        )
        assert rejected.status_code == 422
        assert "new dataset version" in rejected.json()["detail"]
        assert client.get("/api/observations").json() == []
        assert client.post("/api/frozen", json={"run_id": "missing"}).status_code == 404
        assert (
            client.post(
                "/api/model-campaigns",
                json={
                    **payload,
                    "max_proposals": 3,
                },
            ).status_code
            == 422
        )
        _ENGINE_LOCK.acquire()
        try:
            assert client.post("/api/model-campaigns", json=payload).status_code == 409
        finally:
            _ENGINE_LOCK.release()
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as restarted:
        assert restarted.get("/api/model-campaigns").json() == [campaign]
        assert restarted.get("/api/frozen").json() == saved


def test_saved_collections_are_distinct_and_sorted(tmp_path):
    samples = [
        ("abc/campaign.json", {"campaign_id": "baseline", "created_at": "2026-01-01"}),
        (
            "model-campaigns/xyz/campaign.json",
            {
                "campaign_id": "model",
                "created_at": "2026-01-02",
            },
        ),
        ("frozen/first.json", {"frozen_id": "first", "created_at": "2026-01-01"}),
        ("frozen/second.json", {"frozen_id": "second", "created_at": "2026-01-02"}),
    ]
    for name, value in samples:
        path = Path(tmp_path) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    assert [r["campaign_id"] for r in list_artifacts(tmp_path, "campaigns")] == ["baseline"]
    assert [r["campaign_id"] for r in list_artifacts(tmp_path, "model-campaigns")] == ["model"]
    assert [r["frozen_id"] for r in list_artifacts(tmp_path, "frozen")] == ["second", "first"]


def test_source_status_is_read_only_and_does_not_claim_missing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "frontier.sources.longbridge_status",
        lambda: {
            "status": "authentication_required",
            "message": "Run longbridge auth login",
        },
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.get("/api/sources/status")
        assert response.status_code == 200
        state = response.json()
        assert state["longbridge"]["status"] == "authentication_required"
        assert state["acquisition"]["us_hourly"] == "No hourly snapshot imported"


@pytest.mark.parametrize(
    ("endpoint", "worker"),
    [
        ("/api/runs", "frontier.replay.run_research"),
        ("/api/campaigns", "frontier.campaign.run_campaign"),
        ("/api/model-campaigns", "frontier.research.run_model_campaign"),
    ],
)
def test_engine_jobs_reject_busy_and_release_lock_after_failure(
    tmp_path, monkeypatch, endpoint, worker
):
    attempts = []

    def fail(*args, **kwargs):
        assert _ENGINE_LOCK.locked()
        attempts.append(1)
        raise ValueError("fixture job failed")

    monkeypatch.setattr(worker, fail)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        payload = {"dataset_id": "a" * 64}
        _ENGINE_LOCK.acquire()
        try:
            assert client.post(endpoint, json=payload).status_code == 409
            assert attempts == []
        finally:
            _ENGINE_LOCK.release()
        for count in (1, 2):
            response = client.post(endpoint, json=payload)
            assert response.status_code == 422
            assert response.json() == {"detail": "fixture job failed"}
            assert len(attempts) == count
            assert not _ENGINE_LOCK.locked()
