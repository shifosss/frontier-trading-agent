"""Alpaca paper-only HTTP transport. Live hosts and submission retries are excluded."""

import os
import sys
from urllib.parse import quote

import httpx

PAPER_URL = "https://paper-api.alpaca.markets"
TIMEOUT = httpx.Timeout(15, connect=5)


class SubmissionUncertain(RuntimeError):
    """The submission may exist at the broker; reconcile before doing anything else."""


def _paper_credentials():
    names = ("FRONTIER_ALPACA_PAPER_KEY", "FRONTIER_ALPACA_PAPER_SECRET")
    values = [os.environ.get(name) for name in names]
    # Windows app hosts can retain an old environment after user variables change.
    # Read this exact pair only, without mixing a partial process pair with registry values.
    if not any(values) and sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                values = [winreg.QueryValueEx(key, name)[0] for name in names]
        except OSError:
            values = [None, None]
    if not all(isinstance(value, str) and value for value in values):
        raise RuntimeError("Alpaca paper credentials are not configured")
    return values


class AlpacaPaper:
    def __init__(self, client: httpx.Client | None = None):
        if client is None:
            key, secret = _paper_credentials()
            client = httpx.Client(
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                timeout=TIMEOUT,
                follow_redirects=False,
            )
        self.client = client

    def close(self):
        self.client.close()

    def _request(self, method, path, *, params=None, payload=None, missing=False, result_type=dict):
        try:
            response = self.client.request(
                method,
                PAPER_URL + path,
                params=params,
                json=payload,
                timeout=TIMEOUT,
                follow_redirects=False,
            )
        except httpx.TransportError as exc:
            error = SubmissionUncertain if method == "POST" else RuntimeError
            raise error(f"Alpaca paper transport failure ({type(exc).__name__})") from None
        if missing and response.status_code == 404:
            return None
        if not response.is_success:
            code = None
            try:
                body = response.json()
                if isinstance(body, dict) and type(body.get("code")) is int:
                    code = body["code"]
            except ValueError:
                pass
            error = (
                SubmissionUncertain
                if method == "POST" and (response.status_code == 408 or response.status_code >= 500)
                else RuntimeError
            )
            message = f"Alpaca paper HTTP {response.status_code}"
            if code is not None:
                message += f" (code {code})"
            raise error(message)
        if method == "DELETE":
            return None
        try:
            data = response.json()
            if not isinstance(data, result_type):
                raise ValueError("Unexpected response shape")
        except ValueError:
            error = SubmissionUncertain if method == "POST" else RuntimeError
            raise error(f"Alpaca paper invalid response (HTTP {response.status_code})") from None
        return data

    def snapshot(self):
        account = self._request("GET", "/v2/account")
        positions = self._request("GET", "/v2/positions", result_type=list)
        orders = self._request(
            "GET", "/v2/orders", params={"status": "open", "limit": 500}, result_type=list
        )
        if len(orders) >= 500:
            raise RuntimeError("Alpaca paper open-order snapshot reached its 500-order limit")
        clock = self._request("GET", "/v2/clock")
        return {"account": account, "positions": positions, "orders": orders, "clock": clock}

    def get_order(self, client_order_id):
        return self._request(
            "GET",
            "/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id},
            missing=True,
        )

    def submit(self, payload):
        return self._request("POST", "/v2/orders", payload=payload)

    def cancel(self, order_id):
        self._request("DELETE", f"/v2/orders/{quote(str(order_id), safe='')}")

    def asset(self, symbol):
        return self._request("GET", f"/v2/assets/{quote(symbol, safe='')}")
