"""Paper transport contracts, entirely through httpx.MockTransport."""

import json
import traceback

import httpx
import pytest

from frontier.paper_broker import AlpacaPaper, SubmissionUncertain


def test_snapshot_and_order_methods_lock_host_and_preserve_raw_results(monkeypatch):
    monkeypatch.delenv("FRONTIER_ALPACA_PAPER_KEY", raising=False)
    monkeypatch.delenv("FRONTIER_ALPACA_PAPER_SECRET", raising=False)
    requests = []
    payload = {"symbol": "AAPL", "qty": "0.5", "side": "buy", "client_order_id": "paper-1"}
    replies = [
        {"id": "paper-account", "cash": "500.00"},
        [{"symbol": "AAPL", "qty": "1.5"}],
        [{"id": "pending-order", "status": "new"}],
        {"is_open": True},
        {"id": "paper-1", "status": "filled"},
        {"id": "paper-2", "status": "accepted"},
        None,
        {"symbol": "BRK.B", "fractionable": True},
    ]

    def reply(request):
        requests.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == "paper-api.alpaca.markets"
        assert request.extensions["timeout"] == {"connect": 5, "read": 15, "write": 15, "pool": 15}
        body = replies[len(requests) - 1]
        return httpx.Response(204) if body is None else httpx.Response(200, json=body)

    with httpx.Client(
        base_url="https://api.alpaca.markets", transport=httpx.MockTransport(reply)
    ) as client:
        broker = AlpacaPaper(client)
        assert broker.snapshot() == dict(zip(("account", "positions", "orders", "clock"), replies))
        assert broker.get_order("paper-1") == replies[4]
        assert broker.submit(payload) == replies[5]
        assert broker.cancel("paper-2") is None
        assert broker.asset("BRK.B") == replies[7]
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/v2/account"),
        ("GET", "/v2/positions"),
        ("GET", "/v2/orders"),
        ("GET", "/v2/clock"),
        ("GET", "/v2/orders:by_client_order_id"),
        ("POST", "/v2/orders"),
        ("DELETE", "/v2/orders/paper-2"),
        ("GET", "/v2/assets/BRK.B"),
    ]
    assert dict(requests[2].url.params) == {"status": "open", "limit": "500"}
    assert dict(requests[4].url.params) == {"client_order_id": "paper-1"}
    assert json.loads(requests[5].content) == payload


def test_default_client_uses_only_paper_credentials_and_hides_error_body(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setenv("FRONTIER_ALPACA_PAPER_KEY", "paper-secret-key")
    monkeypatch.setenv("FRONTIER_ALPACA_PAPER_SECRET", "paper-secret-value")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setenv("APCA_API_KEY_ID", "wrong-live-key")

    def reply(request):
        assert request.url.host == "paper-api.alpaca.markets"
        assert request.headers["APCA-API-KEY-ID"] == "paper-secret-key"
        assert request.headers["APCA-API-SECRET-KEY"] == "paper-secret-value"
        return httpx.Response(
            401, json={"code": 40110000, "message": "paper-secret-key paper-secret-value"}
        )

    monkeypatch.setattr(
        "frontier.paper_broker.httpx.Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(reply), **kwargs),
    )
    broker = AlpacaPaper()
    try:
        with pytest.raises(RuntimeError, match=r"HTTP 401 \(code 40110000\)") as error:
            broker.asset("AAPL")
        rendered = "".join(traceback.format_exception(error.value))
        assert "paper-secret-key" not in rendered
        assert "paper-secret-value" not in rendered
    finally:
        broker.close()


def test_missing_paper_configuration_does_not_fall_back_to_live_keys(monkeypatch):
    monkeypatch.delenv("FRONTIER_ALPACA_PAPER_KEY", raising=False)
    monkeypatch.delenv("FRONTIER_ALPACA_PAPER_SECRET", raising=False)
    monkeypatch.setenv("APCA_API_KEY_ID", "live-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "live-secret")
    with pytest.raises(RuntimeError, match="paper credentials are not configured"):
        AlpacaPaper()


def test_redirects_are_not_followed_even_with_redirecting_injected_client():
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://api.alpaca.markets/v2/orders"})

    with httpx.Client(transport=httpx.MockTransport(reply), follow_redirects=True) as client:
        with pytest.raises(RuntimeError, match="HTTP 307"):
            AlpacaPaper(client).submit({"symbol": "AAPL"})
    assert len(requests) == 1
    assert requests[0].url.host == "paper-api.alpaca.markets"


def test_only_order_lookup_404_means_missing():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(404, json={"message": "secret"}))
    ) as client:
        broker = AlpacaPaper(client)
        assert broker.get_order("missing-order") is None
        with pytest.raises(RuntimeError, match="HTTP 404"):
            broker.asset("missing-symbol")
        with pytest.raises(RuntimeError, match="HTTP 404"):
            broker.cancel("missing-order")


@pytest.mark.parametrize("method", ["submit", "get_order"])
def test_timeout_is_sanitized_never_missing_and_never_retried(method):
    requests = []

    def reply(request):
        requests.append(request)
        raise httpx.ReadTimeout("sensitive-key and request details", request=request)

    expected = SubmissionUncertain if method == "submit" else RuntimeError
    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(expected, match=r"transport failure \(ReadTimeout\)") as error:
            getattr(AlpacaPaper(client), method)({} if method == "submit" else "paper-1")
    assert len(requests) == 1
    assert "sensitive-key" not in "".join(traceback.format_exception(error.value))
    assert isinstance(error.value, SubmissionUncertain) == (method == "submit")


@pytest.mark.parametrize("status", [408, 500, 503])
def test_submission_server_failure_is_uncertain_and_not_retried(status):
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(status, json={"code": "sensitive-secret", "message": "secret"})

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(SubmissionUncertain) as error:
            AlpacaPaper(client).submit({})
    assert str(error.value) == f"Alpaca paper HTTP {status}"
    assert len(requests) == 1


@pytest.mark.parametrize(
    "response", [httpx.Response(200, text="secret"), httpx.Response(200, json=[])]
)
def test_successful_submission_with_unreadable_response_remains_uncertain(response):
    with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client:
        with pytest.raises(SubmissionUncertain, match="invalid response"):
            AlpacaPaper(client).submit({})


def test_snapshot_rejects_open_order_page_limit():
    def reply(request):
        return httpx.Response(
            200,
            json={"id": "paper-account"}
            if request.url.path == "/v2/account"
            else ([{"id": str(i)} for i in range(500)] if request.url.path == "/v2/orders" else []),
        )

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(RuntimeError, match="500-order limit"):
            AlpacaPaper(client).snapshot()


def test_explicit_submission_rejection_is_distinct_from_uncertain_failure():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, json={"code": 40310000, "message": "private balance"})
        )
    ) as client:
        with pytest.raises(RuntimeError, match="HTTP 403") as error:
            AlpacaPaper(client).submit({})
    assert not isinstance(error.value, SubmissionUncertain)
    assert str(error.value) == "Alpaca paper HTTP 403 (code 40310000)"
