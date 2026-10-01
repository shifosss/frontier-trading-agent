from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from event_inputs import FEATURE_NAMES, prepare_events, extract_labels


def fixture():
    days = []
    day = datetime(2016, 1, 4)
    while len(days) < 230:
        if day.weekday() < 5:
            days.append(day.date().isoformat())
        day += timedelta(days=1)
    zone = ZoneInfo("America/New_York")
    calendar = {"sessions": [{"session": day, "close": datetime.fromisoformat(day+"T16:00:00").replace(tzinfo=zone).isoformat()} for day in days]}
    adjusted = np.column_stack((100 + np.arange(230, dtype=float), 200 + 2*np.arange(230, dtype=float)))
    market = {"sessions": days, "symbols": ["AAA", "SPY"], "benchmark": 1,
              "adjusted": adjusted, "vendor_quote_close": np.full((230, 2), 20.),
              "vendor_quote_volume": np.full((230, 2), 10.)}
    market["vendor_quote_volume"][204, 0] = 20
    event = {"symbol": "AAA", "cik": "0000000001", "accession": "0000000001-16-000001",
             "feature_status": "qualified", "q_status": "qualified", "execution_status": "qualified",
             "strategy_source_status": "qualified", "S": "1.25", "Q": "0.005",
             "decision_time": days[205]+"T09:00:00-04:00", "availability_floor": days[205]+"T01:00:00-04:00",
             "entry_session": days[205], "exit_session": days[210],
             "entry_time": calendar["sessions"][205]["close"], "exit_time": calendar["sessions"][210]["close"],
             "history_accessions": ["old-1", "old-2"], "source_sha256": "source-example"}
    cohort = {"selected": [{"symbol": "AAA", "cik": "0000000001"}]}
    return market, event, cohort, calendar


def prepare(market, event, cohort, calendar):
    return prepare_events(market, [event], cohort, calendar)["rows"][0]


def test_exact_formulas_and_unchanged_original_event():
    market, event, cohort, calendar = fixture()
    original = deepcopy(event)
    result = prepare_events(market, [event], cohort, calendar)
    row = result["rows"][0]
    assert result["feature_names"] == FEATURE_NAMES
    assert row["model_input_status"] == "qualified"
    assert row["model_inputs"] == pytest.approx([1.25, .005, 0, 2, 608/409 - 1])
    assert all(row[k] == v for k, v in original.items()) and event == original
    assert row["prior_price_index"] == 204 and row["entry_index"] == 205 and row["planned_label_end_index"] == 210


class PriorOnly:
    def __init__(self, array, entry):
        self.array, self.entry, self.shape = array, entry, array.shape
    def __getitem__(self, key):
        interval, _ = key
        assert isinstance(interval, slice) and interval.stop <= self.entry, "Future data accessed"
        return self.array[key]


def test_future_prices_are_never_read_to_prepare_inputs():
    market, event, cohort, calendar = fixture()
    expected = prepare(market, event, cohort, calendar)
    for key in ("adjusted", "vendor_quote_close", "vendor_quote_volume"):
        market[key] = PriorOnly(market[key], 205)
    assert prepare(market, event, cohort, calendar) == expected


def test_future_missing_prices_keep_eligibility_and_only_invalidate_labels():
    market, event, cohort, calendar = fixture()
    before = prepare(market, event, cohort, calendar)
    market["adjusted"][208, 0] = np.nan
    after = prepare(market, event, cohort, calendar)
    assert before == after and after["model_input_status"] == "qualified"
    assert extract_labels(market, [after])[after["event_id"]]["status"] == "unavailable"


def test_two_labels_use_all_five_subsequent_closes():
    market, event, cohort, calendar = fixture()
    row = prepare(market, event, cohort, calendar)
    market["adjusted"][205:211, 0] = [100, 95, 103, 90, 99, 105]
    result = extract_labels(market, [row])[row["event_id"]]
    assert result["status"] == "qualified" and result["targets"] == pytest.approx([.05, .10])


@pytest.mark.parametrize("key,index,column,reason", [
    ("adjusted", 201, 0, "prior_relative_return_5"),
    ("adjusted", 100, 1, "prior_spy_sma200_distance"),
    ("vendor_quote_volume", 190, 0, "prior_dollar_activity_ratio_20"),
    ("vendor_quote_close", 204, 0, "prior_dollar_activity_ratio_20"),
])
def test_missing_prior_inputs_are_not_filled(key, index, column, reason):
    market, event, cohort, calendar = fixture()
    market[key][index, column] = np.nan
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "unavailable"
    assert any(r.startswith(reason) for r in row["model_input_reasons"])


def test_zero_current_activity_valid_but_zero_denominator_unavailable():
    market, event, cohort, calendar = fixture()
    market["vendor_quote_volume"][204, 0] = 0
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "qualified" and row["model_inputs"][3] == 0
    market["vendor_quote_volume"][184:204, 0] = 0
    assert prepare(market, event, cohort, calendar)["model_input_status"] == "unavailable"


def test_financial_and_original_industry_gates_retain_events():
    market, event, cohort, calendar = fixture()
    event.update(strategy_source_status="unavailable", q_status="unavailable", Q=None)
    row = prepare(market, event, cohort, calendar)
    assert row["model_input_status"] == "unavailable" and row["Q"] is None
    assert row["S"] == event["S"] and row["history_accessions"] == event["history_accessions"]


@pytest.mark.parametrize("field,value", [("decision_time", "2016-10-17T08:59:00-04:00"),
    ("availability_floor", "2099-01-01T01:00:00-05:00"), ("exit_session", "2016-10-18"),
    ("entry_time", "2016-10-17T12:00:00-04:00")])
def test_inconsistent_clocks_cannot_become_eligible(field, value):
    market, event, cohort, calendar = fixture()
    event[field] = value
    row = prepare(market, event, cohort, calendar)
    assert "execution_clock:inconsistent" in row["model_input_reasons"]


def test_absent_price_symbol_keeps_original_event():
    market, event, cohort, calendar = fixture()
    event["symbol"] = "MISSING";cohort["selected"][0]["symbol"] = "MISSING"
    row = prepare(market, event, cohort, calendar)
    assert row["symbol"] == "MISSING" and "price_symbol:unavailable" in row["model_input_reasons"]


def test_identity_mismatch_and_duplicate_original_are_fatal():
    market, event, cohort, calendar = fixture()
    with pytest.raises(ValueError, match="Duplicate original"):
        prepare_events(market, [event, event], cohort, calendar)
    event["cik"] = "0000000002"
    with pytest.raises(ValueError, match="outside"):
        prepare(market, event, cohort, calendar)


def test_multiple_originals_same_session_remain_distinct_rows():
    market, event, cohort, calendar = fixture()
    other = dict(event, accession="0000000001-16-000002")
    rows = prepare_events(market, [other, event], cohort, calendar)["rows"]
    assert len(rows) == 2 and rows[0]["accession"] == event["accession"]
    assert len({r["event_id"] for r in rows}) == 2
