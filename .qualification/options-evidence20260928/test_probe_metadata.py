"""Offline metadata scope and evidence-retention tests; no real credentials/network."""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil

import httpx
import pytest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("option_metadata_probe", HERE / "probe_metadata.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def setup(tmp_path, monkeypatch):
    shutil.copyfile(HERE / "request-definition.json", tmp_path / "request-definition.json")
    calls = []
    monkeypatch.setattr(m, "_paper_credentials", lambda: ("offline-key", "offline-secret"))
    async def no_wait(seconds):
        pass
    monkeypatch.setattr(m.asyncio, "sleep", no_wait)
    return calls


def response_contracts(request):
    strike = int(request.url.params["strike_price_gte"])
    return [{"id": f"id-{strike}-{kind}", "symbol": f"SPY240315{kind}{strike*1000:08d}",
             "root_symbol": "SPY", "underlying_symbol": "SPY", "expiration_date": "2024-03-15",
             "type": name, "style": "american", "strike_price": str(strike), "size": "100",
             "status": "inactive", "tradable": False,
             "deliverables": [{"type": "equity", "symbol": "SPY", "amount": "100"}]}
            for kind, name in [("C", "call"), ("P", "put")]]


def invoke(tmp_path, handler):
    return asyncio.run(m.run(tmp_path, transport=httpx.MockTransport(handler)))


def test_exact_three_calls_and_six_contracts(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch)
    def handler(req):
        calls.append(req)
        assert req.method == "GET"
        assert req.url.host == "paper-api.alpaca.markets"
        assert req.url.path == "/v2/options/contracts"
        assert dict(req.url.params) == {"underlying_symbols": "SPY", "root_symbol": "SPY",
            "status": "inactive", "expiration_date": "2024-03-15",
            "strike_price_gte": req.url.params["strike_price_gte"],
            "strike_price_lte": req.url.params["strike_price_gte"],
            "show_deliverables": "true", "limit": "10"}
        return httpx.Response(200, json={"option_contracts": response_contracts(req), "next_page_token": None})
    r = invoke(tmp_path, handler)
    assert len(calls) == 3 and r["status"] == "complete"
    assert len(r["contracts"]) == 6 and all(c["status"] == "matched" for c in r["contracts"])
    assert all(c["terms"]["size"] == "100" and c["terms"]["deliverables"] for c in r["contracts"])
    assert r["historical_quotes_qualified"] is False and r["asof_membership_qualified"] is False
    assert len(list(tmp_path.glob("raw-*.json"))) == 3


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_failures_stop_and_preserve_denominator(tmp_path, monkeypatch, status):
    calls = setup(tmp_path, monkeypatch)
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"message": "fixture access failure"})
    r = invoke(tmp_path, handler)
    assert len(calls) == 1 and r["status"] == "incomplete"
    assert [x["status"] for x in r["requests"]] == ["failed", "unattempted", "unattempted"]
    assert len(r["contracts"]) == 6
    assert sum(c["status"] == "unattempted" for c in r["contracts"]) == 4
    assert (tmp_path / r["requests"][0]["raw"]).exists()


def test_empty_and_paginated_results_remain_gaps_without_followup(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch)
    def handler(req):
        calls.append(req)
        n = len(calls)
        return httpx.Response(200, json={"option_contracts": [] if n == 1 else response_contracts(req),
            "next_page_token": "retained-not-followed" if n == 2 else None})
    r = invoke(tmp_path, handler)
    assert len(calls) == 3 and r["status"] == "complete_with_coverage_gaps"
    assert sum(x["status"] == "missing" for x in r["contracts"]) == 2
    assert r["requests"][1]["page_limited"] and r["requests"][1]["next_page_token"] == "retained-not-followed"


def test_duplicate_and_mismatched_identity_not_qualified(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    def handler(req):
        rows = response_contracts(req)
        rows[1]["strike_price"] = "999"
        return httpx.Response(200, json={"option_contracts": [rows[0], rows[0], rows[1]]})
    r = invoke(tmp_path, handler)
    assert r["status"] == "complete_with_coverage_gaps"
    assert sum(c["status"] == "ambiguous" for c in r["contracts"]) == 3
    assert sum(c["status"] == "identity_mismatch" for c in r["contracts"]) == 3


def test_request_mutation_rejected_before_credentials_or_transport(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    p = tmp_path / "request-definition.json"
    d = json.loads(p.read_text()); d["metadata_probe"]["requests"][0]["url"] = "https://api.alpaca.markets/v2/orders"
    p.write_text(json.dumps(d))
    monkeypatch.setattr(m, "_paper_credentials", lambda: pytest.fail("credentials must remain unread"))
    with pytest.raises(ValueError, match="definition"):
        invoke(tmp_path, lambda req: pytest.fail("no request permitted"))


def test_completed_or_interrupted_attempt_is_never_overwritten(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    (tmp_path / "attempt.json").write_text('{"status":"started"}')
    monkeypatch.setattr(m, "_paper_credentials", lambda: pytest.fail("credentials must remain unread"))
    with pytest.raises(FileExistsError):
        invoke(tmp_path, lambda req: pytest.fail("no retry permitted"))
    assert json.loads((tmp_path / "attempt.json").read_text())["status"] == "started"


def test_size_cap_preserves_bounded_prefix_and_stops(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch)
    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=b"x" * (1048576 + 200))
    r = invoke(tmp_path, handler)
    assert len(calls) == 1 and r["requests"][0]["truncated"]
    assert (tmp_path / r["requests"][0]["raw"]).stat().st_size == 1048576
    assert r["status"] == "incomplete"


def test_malformed_success_and_transport_failure_stop(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    r = invoke(tmp_path, lambda req: httpx.Response(200, json={"option_contracts": "invalid"}))
    assert r["status"] == "incomplete" and r["requests"][0]["error_kind"] == "schema_failure"


def test_whole_call_deadline_is_enforced(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    real_sleep, real_timeout = asyncio.sleep, asyncio.timeout
    # setup replaced sleep globally, so use an unresolved Future as the blocked network.
    async def handler(req):
        await asyncio.Future()
    monkeypatch.setattr(m.asyncio, "timeout", lambda seconds: real_timeout(.01))
    r = invoke(tmp_path, handler)
    assert r["status"] == "incomplete" and r["requests"][0]["error_kind"] == "TimeoutError"
    assert sum(x["status"] == "unattempted" for x in r["requests"]) == 2
