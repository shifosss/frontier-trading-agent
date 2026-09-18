"""Funding conservation, fee application and publication-time counterexamples."""

import hashlib
import json
from decimal import Decimal

import pytest

from frontier.funding import plan_usd_funding
from frontier.sources import BOC_URL


def test_zero_conversion_does_not_request_fx(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Zero conversion must not fetch a rate")

    monkeypatch.setattr("frontier.funding.fetch_boc_fx", unexpected)
    cash = {"CAD": 700, "USD": 25}
    plan = plan_usd_funding(tmp_path, cash, 0, "2026-09-18T17:00Z")
    assert plan["mode"] == "existing_cash"
    assert plan["cash_before"] == plan["cash_after"] == cash
    assert plan["reference"] is None
    assert plan["fee_rate"] == 0
    assert plan["estimated_fee_cad"] == plan["estimated_usd_credit"] == 0
    assert plan["cash_before"] is not plan["cash_after"]


def _capture(tmp_path, monkeypatch, observations):
    payload = {"observations": observations}
    raw = tmp_path / "fx.json"
    raw.write_text(json.dumps(payload), encoding="utf-8")
    calls = []

    def fetch(start, end, capture_dir, **kwargs):
        calls.append((start, end, capture_dir, kwargs))
        return {
            "payload": payload,
            "raw_path": str(raw),
            "retrieved_at": "2026-09-18T21:00:00+00:00",
            "request": {"url": BOC_URL, "params": {"start_date": start, "end_date": end}},
        }

    monkeypatch.setattr("frontier.funding.fetch_boc_fx", fetch)
    return raw, calls


def test_one_conversion_preserves_other_cash_and_deducts_fee_once(tmp_path, monkeypatch):
    raw, calls = _capture(
        tmp_path,
        monkeypatch,
        [
            {"d": "2026-09-17", "FXUSDCAD": {"v": "1.3988"}},
            {"d": "2026-09-18", "FXUSDCAD": {"v": "1.0000"}},
        ],
    )
    plan = plan_usd_funding(tmp_path, {"CAD": 1000, "USD": 50}, 700, "2026-09-18T20:29Z")
    assert plan["mode"] == "planned_cad_to_usd"
    assert plan["cash_after"] == {"CAD": 300, "USD": 542.92}
    assert plan["estimated_fee_cad"] == 10.5
    assert plan["fee_rate"] == 0.015
    assert plan["estimated_usd_credit"] == 492.92
    assert plan["reference"]["usd_cad"] == 1.3988
    assert plan["reference"]["available_at"] == "2026-09-17T20:30:00+00:00"
    assert plan["reference"]["sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert plan["reference"]["request"]["params"]["end_date"] == "2026-09-18"
    assert calls == [
        ("2026-09-04", "2026-09-18", tmp_path / "artifacts/sources/cache", {"refresh": True})
    ]
    # Currency value falls only by the single fee plus less than one USD cent of rounding.
    residual = Decimal("700") - Decimal("10.5") - Decimal("492.92") * Decimal("1.3988")
    assert 0 <= residual < Decimal("0.013988")
    json.dumps(plan, allow_nan=False)


@pytest.mark.parametrize(
    "cash, convert",
    [
        ({"CAD": -1, "USD": 0}, 0),
        ({"CAD": 700, "USD": float("nan")}, 0),
        ({"CAD": 700, "USD": float("inf")}, 0),
        ({"CAD": 700, "USD": 0}, -1),
        ({"CAD": 700, "USD": 0}, float("nan")),
        ({"CAD": 700, "USD": 0}, float("inf")),
        ({"CAD": 700, "USD": 0}, 701),
        ({"CAD": 700, "EUR": 0}, 0),
    ],
)
def test_invalid_cash_and_conversion_are_rejected_before_fetch(
    tmp_path, monkeypatch, cash, convert
):
    monkeypatch.setattr(
        "frontier.funding.fetch_boc_fx", lambda *a, **kw: pytest.fail("fetch called")
    )
    with pytest.raises(ValueError):
        plan_usd_funding(tmp_path, cash, convert, "2026-09-18T17:00Z")


def test_no_published_fx_does_not_use_future_observation(tmp_path, monkeypatch):
    _capture(tmp_path, monkeypatch, [{"d": "2026-09-18", "FXUSDCAD": {"v": "1.4"}}])
    with pytest.raises(ValueError, match="No published"):
        plan_usd_funding(tmp_path, {"CAD": 700, "USD": 0}, 700, "2026-09-18T20:29Z")


@pytest.mark.parametrize(
    "amount, fee_rate, fee, credit",
    [
        (9999.99, 0.015, 149.99985, 4924.99),
        (10000, 0.01, 100, 4950),
        (24999.99, 0.01, 249.9999, 12374.99),
        (25000, 0.005, 125, 12437.5),
        (99999.99, 0.005, 499.99995, 49749.99),
        (100000, 0, 0, 50000),
    ],
)
def test_cash_conversion_tiers_apply_to_whole_transaction(
    tmp_path, monkeypatch, amount, fee_rate, fee, credit
):
    _capture(tmp_path, monkeypatch, [{"d": "2026-09-17", "FXUSDCAD": {"v": "2"}}])
    plan = plan_usd_funding(tmp_path, {"CAD": amount, "USD": 0}, amount, "2026-09-18T17:00Z")
    assert plan["fee_rate"] == fee_rate
    assert plan["estimated_fee_cad"] == fee
    assert plan["estimated_usd_credit"] == credit
    assert plan["cash_after"] == {"CAD": 0, "USD": credit}
