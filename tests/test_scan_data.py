import hashlib
import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from frontier.scan_data import capture_universe, normalize_chart, read_capture
from frontier.web import _ENGINE_LOCK, create_app

SPEC = {"symbol": "TEST.TO", "currency": "CAD", "calendar": "XTSE"}


def chart():
    dates = ["2026-06-30", "2026-07-01", "2026-07-02"]
    stamps = [int(pd.Timestamp(day + " 09:30", tz="America/Toronto").timestamp()) for day in dates]
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "CAD", "symbol": "TEST.TO"},
                    "timestamp": stamps,
                    "indicators": {
                        "quote": [
                            {
                                "close": [10, 11, 12],
                                "high": [11, 12, 13],
                                "low": [9, 10, 11],
                                "volume": [1000, 1100, 1200],
                            }
                        ],
                        "adjclose": [{"adjclose": [9.5, 10.5, 12]}],
                    },
                }
            ],
            "error": None,
        }
    }


def test_chart_respects_calendar_completion_and_separates_adjusted_price():
    frame = normalize_chart(chart(), SPEC, "2026-07-02T18:00:00Z")
    assert frame.session.tolist() == ["2026-06-30"]
    assert frame.iloc[0].close == 10
    assert frame.iloc[0].adjusted_close == 9.5
    assert frame.iloc[0].available_at == pd.Timestamp("2026-06-30T20:01:00Z")
    assert len(normalize_chart(chart(), SPEC, "2026-07-02T20:01:00Z")) == 2
    with pytest.raises(ValueError, match="symbol"):
        normalize_chart(chart(), {**SPEC, "symbol": "WRONG.TO"}, "2026-07-02T20:01:00Z")
    with pytest.raises(ValueError, match="currency"):
        normalize_chart(chart(), {**SPEC, "currency": "USD"}, "2026-07-02T20:01:00Z")


def test_source_failure_is_retained_and_raw_tampering_rejected(tmp_path, monkeypatch):
    def get(url, **kwargs):
        if "FAIL" in url:
            raise httpx.ConnectError("offline fixture")
        return httpx.Response(200, json=chart(), request=httpx.Request("GET", url))

    monkeypatch.setattr("frontier.scan_data.httpx.get", get)
    universe = [SPEC, {**SPEC, "symbol": "FAIL.TO"}]
    manifest, cached = capture_universe(tmp_path, universe)
    assert not cached
    assert manifest["captures"][1] == {"symbol": "FAIL.TO", "error": "offline fixture"}
    saved, cached = capture_universe(tmp_path, universe, refresh=False)
    assert cached and saved == manifest
    frame = read_capture(tmp_path, manifest)
    assert set(frame.symbol) == {"TEST.TO"}
    raw = tmp_path / manifest["captures"][0]["path"]
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bytes changed"):
        read_capture(tmp_path, manifest)


def test_scanner_rejects_mismatched_price_arrays_and_source_escape(tmp_path):
    value = chart()
    value["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"].pop()
    with pytest.raises(ValueError, match="different lengths"):
        normalize_chart(value, SPEC, "2026-07-02T20:01:00Z")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(chart()))
    manifest = {
        "universe": [SPEC],
        "captures": [
            {
                "symbol": SPEC["symbol"],
                "path": "outside.json",
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
            }
        ],
    }
    with pytest.raises(ValueError, match="outside"):
        read_capture(tmp_path, manifest)


def test_scan_api_uses_simulated_native_budgets_and_busy_lock(tmp_path, monkeypatch):
    calls = []

    def run(workspace, **kwargs):
        calls.append(kwargs)
        assert _ENGINE_LOCK.locked()
        return {"scan_id": "fixture"}

    monkeypatch.setattr("frontier.scan_data.run_scan", run)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/scans").json() == []
        assert client.get("/api/scans/missing").status_code == 404
        assert client.post("/api/scans", json={}).json() == {"scan_id": "fixture"}
        assert calls == [{"refresh": True, "initial_cash_usd": 0, "initial_cash_cad": 700}]
        assert not _ENGINE_LOCK.locked()
        assert client.post("/api/scans", json={"initial_cash_cad": -1}).status_code == 422
        _ENGINE_LOCK.acquire()
        try:
            assert client.post("/api/scans", json={}).status_code == 409
        finally:
            _ENGINE_LOCK.release()
        assert len(calls) == 1
