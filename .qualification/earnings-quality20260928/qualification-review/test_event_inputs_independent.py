"""Independent synthetic causal-input review; no actual source corpus or models."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parent / "model-inputs"
sys.path.insert(0, str(INPUTS))
try:
    spec = importlib.util.spec_from_file_location("independent_event_input_fixtures", INPUTS / "test_event_inputs.py")
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
finally:
    sys.path.pop(0)
prepare_events = fixture_module.prepare_events
extract_labels = fixture_module.extract_labels
fixture = fixture_module.fixture


def prepare(market, event, cohort, calendar):
    return prepare_events(market, [event], cohort, calendar)["rows"][0]


def test_independent_nontrivial_five_input_arithmetic():
    market, event, cohort, calendar = fixture()
    p = 204
    market["adjusted"][:, 0] = 50 + np.arange(230, dtype=float) ** 2 / 100
    market["adjusted"][:, 1] = 90 + np.arange(230, dtype=float) * 1.5
    market["vendor_quote_close"][184:205, 0] = np.arange(10, 31, dtype=float)
    market["vendor_quote_volume"][184:205, 0] = np.arange(1, 22, dtype=float)
    row = prepare(market, event, cohort, calendar)
    d = lambda number: Decimal(str(number))
    stock = market["adjusted"][:, 0]
    spy = market["adjusted"][:, 1]
    relative = (d(stock[p]) / d(stock[p-5]) - 1) - (d(spy[p]) / d(spy[p-5]) - 1)
    products = sorted(d(market["vendor_quote_close"][j, 0]) * d(market["vendor_quote_volume"][j, 0]) for j in range(p-20, p))
    median = (products[9] + products[10]) / 2
    activity = d(market["vendor_quote_close"][p, 0]) * d(market["vendor_quote_volume"][p, 0]) / median
    distance = d(spy[p]) / (sum(d(spy[j]) for j in range(p-199, p+1)) / 200) - 1
    assert row["model_input_status"] == "qualified"
    assert row["model_inputs"] == pytest.approx([float(Decimal(event["S"])), float(Decimal(event["Q"])), float(relative), float(activity), float(distance)])


def test_zero_volume_allowed_without_current_day_in_denominator():
    market, event, cohort, calendar = fixture()
    market["vendor_quote_close"][184:205, 0] = 1
    market["vendor_quote_volume"][184:204, 0] = np.arange(20, dtype=float)
    market["vendor_quote_volume"][204, 0] = 10000
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "qualified"
    assert row["model_inputs"][3] == pytest.approx(10000 / 9.5)


class GuardedPriceArray:
    def __init__(self, array, last_completed):
        self._array, self.last_completed, self.shape = array, last_completed, array.shape
        self.reads = []

    def __getitem__(self, key):
        interval, column = key
        assert isinstance(interval, slice)
        assert interval.start >= 0 and interval.stop <= self.last_completed + 1
        self.reads.append((interval.start, interval.stop, column))
        return self._array[key]


def test_exact_prior_only_read_windows():
    market, event, cohort, calendar = fixture()
    for key in ("adjusted", "vendor_quote_close", "vendor_quote_volume"):
        market[key] = GuardedPriceArray(market[key], 204)
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "qualified"
    assert market["adjusted"].reads == [(199, 205, 0), (199, 205, 1), (5, 205, 1)]
    assert market["vendor_quote_close"].reads == [(184, 205, 0)]
    assert market["vendor_quote_volume"].reads == [(184, 205, 0)]


@pytest.mark.parametrize("offset", range(6))
def test_missing_entry_or_any_label_close_never_changes_eligibility(offset):
    market, event, cohort, calendar = fixture()
    before = prepare(market, event, cohort, calendar)
    market["adjusted"][205+offset, 0] = np.nan
    after = prepare(market, event, cohort, calendar)
    assert after == before and after["model_input_status"] == "qualified"
    labels = extract_labels(market, [after])[after["event_id"]]
    assert labels["status"] == "unavailable" and labels["targets"] is None


def test_nonmonotonic_labels_use_every_close_independently():
    market, event, cohort, calendar = fixture()
    row = prepare(market, event, cohort, calendar)
    prices = [Decimal("40"), Decimal("39"), Decimal("28"), Decimal("44"), Decimal("43"), Decimal("42")]
    market["adjusted"][205:211, 0] = list(map(float, prices))
    labels = extract_labels(market, [row])[row["event_id"]]
    moves = [price / prices[0] - 1 for price in prices[1:]]
    assert labels["targets"] == pytest.approx([float(moves[-1]), float(max(Decimal(0), -min(moves)))])


def test_full_event_population_and_original_fields_retained():
    market, event, cohort, calendar = fixture()
    other = dict(event, accession="0000000001-16-000002", strategy_source_status="excluded", S="2.5")
    unavailable = dict(event, accession="0000000001-16-000003", Q=None, q_status="unavailable")
    originals = [unavailable, event, other]
    saved = deepcopy(originals)
    rows = prepare_events(market, originals, cohort, calendar)["rows"]
    assert originals == saved and len(rows) == 3
    assert [row["accession"] for row in rows] == sorted(row["accession"] for row in saved)
    by_id = {row["accession"]: row for row in rows}
    for original in saved:
        assert all(by_id[original["accession"]][key] == value for key, value in original.items())
    assert [row["model_input_status"] for row in rows] == ["qualified", "unavailable", "unavailable"]


def test_utc_equivalent_clock_and_official_early_close_are_accepted():
    market, event, cohort, calendar = fixture()
    day = market["sessions"][205]
    event["decision_time"] = day + "T13:00:00+00:00"
    event["availability_floor"] = event["decision_time"]
    calendar["sessions"][205]["close"] = day + "T13:00:00-04:00"
    event["entry_time"] = day + "T17:00:00+00:00"
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "qualified"
    assert row["prior_price_index"] == 204


@pytest.mark.parametrize("clock", ["2016-10-17T09:00:00", "2016-10-17T09:00:00.000001-04:00", "2016-10-17T09:00:00-05:00"])
def test_naive_fractional_or_wrong_offset_decisions_remain_unavailable(clock):
    market, event, cohort, calendar = fixture()
    day = market["sessions"][205]
    event["decision_time"] = day + clock[10:]
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "unavailable"
    assert "execution_clock:inconsistent" in row["model_input_reasons"]
