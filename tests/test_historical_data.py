"""Historical price units, cutoffs and raw capture provenance."""

import copy
import hashlib
import json

import httpx
import numpy as np
import pandas as pd
import pytest

from frontier.historical_data import capture_histories, normalize_history, read_history
from frontier.scan_data import normalize_chart

SPEC = {"symbol": "AAA", "currency": "USD", "calendar": "XNYS"}


def payload(dates):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "AAA", "currency": "USD"},
                    "timestamp": [int(pd.Timestamp(date).timestamp()) for date in dates],
                    "indicators": {
                        "quote": [
                            {
                                "close": [10.0] * len(dates),
                                "high": [11.0] * len(dates),
                                "low": [9.0] * len(dates),
                                "volume": [100.0] * len(dates),
                            }
                        ],
                        "adjclose": [{"adjclose": [8.0] * len(dates)}],
                    },
                }
            ],
            "error": None,
        }
    }


def test_recent_normalization_matches_existing_and_excludes_unfinished_close():
    raw = payload(["2026-09-16T13:30:00Z", "2026-09-17T13:30:00Z", "2026-09-18T13:30:00Z"])
    cutoff = "2026-09-18T19:00:00Z"
    pd.testing.assert_frame_equal(
        normalize_history(raw, SPEC, cutoff), normalize_chart(raw, SPEC, cutoff)
    )


def test_explicit_calendar_accepts_dotcom_history_and_skips_holiday():
    raw = payload(["2000-01-01T14:30:00Z", "2000-01-03T14:30:00Z"])
    frame = normalize_history(raw, SPEC, "2026-09-18T19:00:00Z")
    assert frame.session.tolist() == ["2000-01-03"]
    assert frame.available_at.iloc[0] == pd.Timestamp("2000-01-03T21:01:00Z")


def test_mismatched_currency_and_bad_prices_are_not_accepted():
    raw = payload(["2000-01-03T14:30:00Z"])
    wrong = copy.deepcopy(raw)
    wrong["chart"]["result"][0]["meta"]["currency"] = "CAD"
    with pytest.raises(ValueError, match="currency"):
        normalize_history(wrong, SPEC, "2026-09-18T19:00:00Z")
    raw["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [-1]
    with pytest.raises(ValueError, match="Non-positive"):
        normalize_history(raw, SPEC, "2026-09-18T19:00:00Z")


def split_event(date, numerator, denominator=1):
    return {
        "date": int(pd.Timestamp(date).timestamp()),
        "numerator": numerator,
        "denominator": denominator,
    }


def test_reported_splits_reconstruct_nominal_price_and_volume_by_session():
    raw = payload(["2000-01-03T14:30:00Z", "2000-01-04T14:30:00Z", "2000-01-05T14:30:00Z"])
    # Split timestamp is later intraday than the daily bar on its effective session.
    raw["chart"]["result"][0]["events"] = {
        "splits": {
            "first": split_event("2000-01-04T20:00:00Z", 2),
            "second": split_event("2000-01-05T14:30:00Z", 1, 10),
        }
    }
    unchanged = copy.deepcopy(raw)
    frame = normalize_history(raw, SPEC, "2026-09-18T19:00:00Z")
    np.testing.assert_allclose(frame.close, [2, 1, 10])
    np.testing.assert_allclose(frame.high, [2.2, 1.1, 11])
    np.testing.assert_allclose(frame.low, [1.8, 0.9, 9])
    np.testing.assert_allclose(frame.volume, [500, 1000, 100])
    np.testing.assert_allclose(frame.adjusted_close, [8, 8, 8])
    np.testing.assert_allclose(frame.close * frame.volume, [1000, 1000, 1000])
    assert frame.attrs["split_reconstruction"]["reported_effective_events"] == 2
    assert raw == unchanged


def test_aapl_2000_provider_sample_matches_independent_nominal_close():
    # Captured Yahoo sample cross-checked against Longbridge raw AAPL Jan 3, 2000.
    raw = payload(["2000-01-03T14:30:00Z"])
    result = raw["chart"]["result"][0]
    result["indicators"]["quote"][0].update(
        close=[0.9994419813156128],
        high=[1.004464030265808],
        low=[0.9079239964485168],
        volume=[535796800],
    )
    result["events"] = {
        "splits": {
            str(i): split_event(day, ratio)
            for i, (day, ratio) in enumerate(
                [
                    ("2000-06-21T13:30:00Z", 2),
                    ("2005-02-28T14:30:00Z", 2),
                    ("2014-06-09T13:30:00Z", 7),
                    ("2020-08-31T13:30:00Z", 4),
                ]
            )
        }
    }
    frame = normalize_history(raw, SPEC, "2026-09-18T19:00:00Z")
    assert frame.close.iloc[0] == pytest.approx(111.938, abs=0.001)
    assert frame.volume.iloc[0] == pytest.approx(4784100, rel=0.0001)
    assert frame.attrs["split_reconstruction"]["maximum_factor"] == 112
    # A USD500 account with a 20% position cap could not buy one then-priced share.
    assert np.floor(100 / (frame.close.iloc[0] * 1.001)) == 0
    assert np.floor(100 / (0.9994419813156128 * 1.001)) == 99


def test_historical_cutoff_fetches_current_split_events_then_filters_locally(tmp_path, monkeypatch):
    raw = payload(["2000-01-03T14:30:00Z", "2005-02-28T14:30:00Z"])
    raw["chart"]["result"][0]["events"] = {
        "splits": {"later": split_event("2005-02-28T14:30:00Z", 2)}
    }
    requested = []

    def get(url, **kwargs):
        requested.append(kwargs["params"])
        return httpx.Response(
            200, json=raw, request=httpx.Request("GET", url, params=kwargs["params"])
        )

    monkeypatch.setattr("frontier.historical_data.httpx.get", get)
    cutoff = "2000-01-04T22:00:00Z"
    before = pd.Timestamp.now(tz="UTC").timestamp()
    record = capture_histories(tmp_path, [SPEC], as_of=cutoff)[0]
    assert "error" not in record
    assert requested[0]["period2"] >= int(before)
    assert record["last_session"] == "2000-01-03"
    assert record["split_reconstruction"]["maximum_factor"] == 2
    frame = read_history(tmp_path, {**record, "spec": SPEC})
    assert frame.session.tolist() == ["2000-01-03"]
    assert frame.close.iloc[0] == 20


def test_old_request_cannot_hide_later_current_vintage_splits(tmp_path):
    raw = payload(["2000-01-03T14:30:00Z"])
    raw["chart"]["result"][0]["meta"]["regularMarketTime"] = int(
        pd.Timestamp("2026-09-17T20:00:00Z").timestamp()
    )
    content = json.dumps(raw).encode()
    path = tmp_path / "data/scanner/raw/AAA.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    record = {
        "path": "data/scanner/raw/AAA.json",
        "sha256": hashlib.sha256(content).hexdigest(),
        "spec": SPEC,
        "captured_at": "2026-09-18T19:00:00Z",
        "url": "https://query1.finance.yahoo.com/v8/finance/chart/AAA?period2=978307200",
    }
    with pytest.raises(ValueError, match="current-vintage split"):
        read_history(tmp_path, record)


def test_invalid_split_ratio_is_not_treated_as_no_split():
    raw = payload(["2000-01-03T14:30:00Z"])
    raw["chart"]["result"][0]["events"] = {
        "splits": {"bad": split_event("2005-02-28T14:30:00Z", 2, 0)}
    }
    with pytest.raises(ValueError, match="Invalid reported split ratio"):
        normalize_history(raw, SPEC, "2026-09-18T19:00:00Z")
