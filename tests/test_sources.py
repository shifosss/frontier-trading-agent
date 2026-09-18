"""Source timing, action identity, immutable capture and read-only command contracts."""

import json
import subprocess

import httpx
import pandas as pd
import pytest

from frontier.sources import (
    alpaca_action_rows,
    boc_rows,
    compare_daily,
    fetch_boc_fx,
    fetch_longbridge_history,
    hourly_rows,
    longbridge_status,
)


def candle(time, **changes):
    return {
        "timestamp": time,
        "open": "100",
        "high": "102",
        "low": "99",
        "close": "101",
        "volume": 500,
        "trade_session": "Intraday",
        **changes,
    }


def test_hourly_session_start_endpoint_and_final_partial_bar():
    frame = hourly_rows(
        [
            candle("2026-06-22T13:30:00Z"),
            candle("2026-06-22T19:30:00Z"),
        ],
        "2026-06-23T00:00:00Z",
    )
    assert pd.Timestamp(frame.event_time.iloc[0]) == pd.Timestamp("2026-06-22T14:30Z")
    assert pd.Timestamp(frame.event_time.iloc[1]) == pd.Timestamp("2026-06-22T20:00Z")
    assert pd.Timestamp(frame.available_at.iloc[1]) == pd.Timestamp("2026-06-22T20:01Z")
    early_close = hourly_rows([candle("2026-11-27T17:30:00Z")], "2026-11-28T00:00Z")
    assert pd.Timestamp(early_close.event_time.iloc[0]) == pd.Timestamp("2026-11-27T18:00Z")


@pytest.mark.parametrize(
    "opening,capture,error",
    [
        ("2026-06-22T19:30Z", "2026-06-22T19:59Z", "unfinished"),
        ("2026-06-22T19:30Z", "2026-06-22T20:00:30Z", "unfinished"),
        ("2026-06-22T13:00Z", "2026-06-23T00:00Z", "regular"),
        ("2026-07-03T13:30Z", "2026-07-04T00:00Z", "session"),
    ],
)
def test_reject_unfinished_off_session_and_holidays(opening, capture, error):
    with pytest.raises(ValueError, match=error):
        hourly_rows([candle(opening)], capture)


def test_action_window_uses_ex_date_not_processing_or_payment_date():
    source = {
        "announcements": {
            "cash_dividends": [
                {
                    "symbol": "SPY",
                    "rate": 1.903516,
                    "ex_date": "2026-06-18",
                    "payable_date": "2026-07-31",
                    "process_date": "2026-07-31",
                }
            ]
        }
    }
    actions, excluded = alpaca_action_rows(source, "2026-06-22", "2026-09-17")
    assert actions.empty
    assert excluded[0]["ex_date"] == "2026-06-18"
    actions, excluded = alpaca_action_rows(source, "2026-06-17", "2026-09-17")
    assert len(actions) == 1
    assert actions.event_time.iloc[0].startswith("2026-06-18")
    assert not excluded


def test_fx_publication_uses_toronto_dst_and_omits_future_rates():
    source = {
        "observations": [
            {"d": "2026-01-15", "FXUSDCAD": {"v": "1.4"}},
            {"d": "2026-07-15", "FXUSDCAD": {"v": "1.3"}},
        ]
    }
    frame = boc_rows(source, "2026-07-15T20:29Z")
    assert len(frame) == 1
    assert pd.Timestamp(frame.available_at.iloc[0]) == pd.Timestamp("2026-01-15T21:30Z")
    frame = boc_rows(source, "2026-07-15T20:30Z")
    assert pd.Timestamp(frame.available_at.iloc[-1]) == pd.Timestamp("2026-07-15T20:30Z")


def test_daily_comparison_retains_disagreement():
    hourly = hourly_rows(
        [candle("2026-06-22T13:30Z"), candle("2026-06-22T19:30Z", close="100")], "2026-06-23T00:00Z"
    )
    daily = {
        "Time Series (Daily)": {
            "2026-06-22": {
                "1. open": "99",
                "2. high": "103",
                "3. low": "98",
                "4. close": "100.5",
                "5. volume": "2000",
            }
        }
    }
    report = compare_daily(hourly, daily)
    assert report["matched_days"] == 1
    assert report["daily_comparison"][0]["close"]["difference"] == -0.5
    assert report["max_absolute_difference"]["volume"] == 1000


def test_boc_cache_captures_raw_bytes_and_explicit_refresh(tmp_path):
    calls = []

    def reply(request):
        calls.append(request)
        assert request.url.host == "www.bankofcanada.ca"
        assert request.url.params["start_date"] == "2026-06-01"
        return httpx.Response(200, content=b'{"observations": [], "revision": 1}')

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        first = fetch_boc_fx("2026-06-01", "2026-06-30", tmp_path, client=client)
        cached = fetch_boc_fx("2026-06-01", "2026-06-30", tmp_path, client=client)
        assert not first["cache_hit"] and cached["cache_hit"]
        assert first["raw_path"] == cached["raw_path"]
        assert len(calls) == 1
        fetch_boc_fx("2026-06-01", "2026-06-30", tmp_path, client=client, refresh=True)
        assert len(calls) == 2


def test_expired_longbridge_never_starts_login_or_quote_fetch(monkeypatch, tmp_path):
    commands = []

    def run(args, **kwargs):
        commands.append(args)
        assert kwargs["shell"] is False
        assert kwargs["timeout"] > 0
        return subprocess.CompletedProcess(args, 0, '{"token":{"status":"expired"}}', "")

    monkeypatch.setattr(subprocess, "run", run)
    status = longbridge_status()
    assert status["status"] == "expired" and not status["authenticated"]
    with pytest.raises(RuntimeError, match="longbridge auth login"):
        fetch_longbridge_history("SPY.US", "2026-06-22", "2026-09-17", tmp_path)
    assert all(command[1:] == ["auth", "status", "--format", "json"] for command in commands)


def test_longbridge_history_command_and_cache_are_read_only(monkeypatch, tmp_path):
    commands = []

    def run(args, **kwargs):
        commands.append(args)
        result = (
            {"token": {"status": "valid"}} if args[1] == "auth" else [candle("2026-06-22T13:30Z")]
        )
        return subprocess.CompletedProcess(args, 0, json.dumps(result), "")

    monkeypatch.setattr(subprocess, "run", run)
    first = fetch_longbridge_history("SPY.US", "2026-06-22", "2026-06-23", tmp_path)
    cached = fetch_longbridge_history("SPY.US", "2026-06-22", "2026-06-23", tmp_path)
    assert cached["cache_hit"] and first["raw_path"] == cached["raw_path"]
    assert len(commands) == 2
    assert commands[1][1:] == [
        "kline",
        "history",
        "SPY.US",
        "--period",
        "1h",
        "--start",
        "2026-06-22",
        "--end",
        "2026-06-23",
        "--adjust",
        "none",
        "--session",
        "intraday",
        "--format",
        "json",
    ]
    with pytest.raises(ValueError, match="1000-row"):
        fetch_longbridge_history("SPY.US", "2026-01-01", "2026-12-31", tmp_path)
    with pytest.raises(ValueError, match="US symbols"):
        fetch_longbridge_history("XIU.CA", "2026-06-22", "2026-06-23", tmp_path)
    assert len(commands) == 2
