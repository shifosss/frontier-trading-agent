"""Exercise the local trust boundary and actual persisted replay through HTTP."""

import json

import pytest
from fastapi.testclient import TestClient

from frontier.data import import_dataset
from frontier.domain import RunConfig
from frontier.fixtures import generate_fixture
from frontier.web import create_app


@pytest.fixture
def service(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, app, tmp_path


def test_demo_dataset_preview_and_status(service):
    client, _, _ = service
    before = client.get("/api/status").json()
    assert before["dataset_count"] == 0
    first = client.post("/api/demo", json={})
    assert first.status_code == 200, first.text
    manifest = first.json()
    assert manifest["mode"] == "synthetic_fixture"
    assert client.post("/api/demo", json={}).json()["dataset_id"] == manifest["dataset_id"]
    assert len(client.get("/api/datasets").json()) == 1
    detail = client.get(f"/api/datasets/{manifest['dataset_id']}").json()
    assert detail["preview"]["bars"]
    assert detail["manifest"]["dataset_id"] == manifest["dataset_id"]
    assert client.get("/api/status").json()["capabilities"]["broker_connection"] is False


def test_http_trust_boundary(service):
    client, _, _ = service
    assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 400
    for origin in ("https://evil.example", "null", "http://127.0.0.1:9999"):
        response = client.post("/api/demo", json={}, headers={"origin": origin})
        assert response.status_code == 403
    assert (
        client.post(
            "/api/demo",
            json={},
            headers={
                "sec-fetch-site": "cross-site",
            },
        ).status_code
        == 403
    )
    assert client.post("/api/demo", content="{}").status_code == 415
    assert (
        client.post(
            "/api/demo",
            json={},
            headers={
                "origin": "http://127.0.0.1",
            },
        ).status_code
        == 200
    )
    missing = client.get("/api/not-real")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")


def test_import_confinement_and_report_registry_confinement(service):
    client, app, workspace = service
    assert (
        client.post(
            "/api/import",
            json={
                "source_directory": "../outside",
            },
        ).status_code
        == 403
    )
    source = generate_fixture(workspace / "data" / "imports" / "fixture")
    imported = client.post("/api/import", json={"source_directory": str(source)})
    assert imported.status_code == 200, imported.text
    config = RunConfig(dataset_id=imported.json()["dataset_id"])
    registry = app.state.registry
    run_id = registry.start_run(config, "synthetic_fixture", "http-path-test")
    outside = workspace / "outside"
    outside.mkdir()
    (outside / "report.html").write_text("private", encoding="utf-8")
    registry.finish_run(run_id, {}, str(outside))
    assert client.get(f"/api/runs/{run_id}/report").status_code == 403
    assert client.get(f"/api/runs/{run_id}").status_code == 403
    assert client.get("/api/runs/missing/report").status_code == 404


def test_actual_run_result_and_report(service):
    client, _, _ = service
    dataset_id = client.post("/api/demo", json={}).json()["dataset_id"]
    response = client.post(
        "/api/runs",
        json={
            "dataset_id": dataset_id,
            "initial_cash_usd": 10000,
            "initial_cash_cad": 10000,
        },
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    run_id = detail["record"]["id"]
    assert detail["record"]["status"] == "COMPLETED"
    assert detail["result"]["equity_curve"]
    assert detail["result"]["fills"]
    assert client.get(f"/api/runs/{run_id}").json() == detail
    report = client.get(f"/api/runs/{run_id}/report")
    assert report.status_code == 200
    assert "text/html" in report.headers["content-type"]
    assert len(client.get("/api/runs").json()) == 1


def test_known_action_failure_remains_in_registry(service):
    client, _, workspace = service
    source = generate_fixture(workspace / "data" / "imports" / "action-fixture")
    metadata = json.loads((source / "dataset.json").read_text(encoding="utf-8"))
    instrument = metadata["instruments"][0]
    import pandas as pd

    bars = pd.read_csv(source / "bars.csv")
    event = bars.loc[bars.instrument_id == instrument["id"], "event_time"].iloc[2]
    (source / "actions.csv").write_text(
        "instrument_id,event_time,available_at,type,cash_amount,currency,ratio\n"
        f"{instrument['id']},{event},{event},dividend,0.5,{instrument['currency']},\n",
        encoding="utf-8",
    )
    manifest = import_dataset(source, workspace / "data" / "datasets")
    response = client.post("/api/runs", json={"dataset_id": manifest.dataset_id})
    assert response.status_code == 422
    records = client.get("/api/runs").json()
    assert len(records) == 1
    assert records[0]["status"] == "FAILED"
    assert records[0]["error"]
    detail = client.get(f"/api/runs/{records[0]['id']}").json()
    assert detail["result"] is None


def test_actual_campaign_trials_retained(service):
    client, _, _ = service
    dataset_id = client.post("/api/demo", json={}).json()["dataset_id"]
    response = client.post("/api/campaigns", json={"dataset_id": dataset_id})
    assert response.status_code == 200, response.text
    campaign = response.json()
    assert campaign["kind"] == "exploratory_tournament"
    assert campaign["trial_count"] == len(campaign["run_ids"]) == 11
    assert len(client.get("/api/runs").json()) == 11
    assert len(campaign["ranking"]) == 11


def test_operator_status_is_local_and_setup_required(service, monkeypatch):
    client, _, _ = service

    def forbid_broker(*args, **kwargs):
        raise AssertionError("Status must not contact or construct a broker")

    monkeypatch.setattr("frontier.operator.AlpacaPaper", forbid_broker)
    response = client.get("/api/operator/status")
    assert response.status_code == 200
    assert response.json()["status"] == "setup_required"
    assert response.json()["mode"] == "paper"
    assert response.json()["orders"] == []
    assert response.json()["account"] is None
