"""Offline fixtures: pagination, interruption, source gaps and existing early close."""
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("intraday_capture", ROOT / "capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
REQUEST = json.loads((ROOT / "request.json").read_text(encoding="utf-8"))
CALENDAR = json.loads((ROOT / "calendar.json").read_text(encoding="utf-8"))


def bar(t):
    return {"t":t.isoformat(), "o":10, "h":11, "l":9, "c":10.5, "v":100, "n":5, "vw":10.4}


def reply(rows, token=None, status=200):
    return status, json.dumps({"bars":{"AAPL":rows}, "next_page_token":token}).encode(), {"date":"fixture"}


def test_pagination_resume_and_hash_corruption(tmp_path):
    calls=[]
    responses=[reply([], "next"), reply([])]
    def fetch(params):
        calls.append(params.copy())
        return responses.pop(0)
    p={"symbols":"AAPL", "start":"2016-01-04T14:30:00Z"}
    result=capture.capture_pages(tmp_path, "2016-01-04", p, fetch, REQUEST["transport"], lambda _:None)
    assert result["complete"] and len(calls)==2 and calls[1]["page_token"]=="next"
    def no_get(params):
        raise AssertionError("Cached page must not be downloaded again")
    again=capture.capture_pages(tmp_path, "2016-01-04", p, no_get, REQUEST["transport"], lambda _:None)
    assert again["complete"] and again["sources"]==result["sources"]
    (tmp_path/result["sources"][0]["raw_file"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        capture.capture_pages(tmp_path, "2016-01-04", p, no_get, REQUEST["transport"], lambda _:None)


def test_interrupted_next_page_preserves_first_page(tmp_path):
    calls=[]
    def interrupted(params):
        calls.append(params.copy())
        if len(calls)==1:
            return reply([], "next")
        raise KeyboardInterrupt()
    p={"symbols":"AAPL"}
    with pytest.raises(KeyboardInterrupt):
        capture.capture_pages(tmp_path,"2016-01-04",p,interrupted,REQUEST["transport"],lambda _:None)
    resumed=[]
    def finish(params):
        resumed.append(params.copy())
        return reply([])
    result=capture.capture_pages(tmp_path,"2016-01-04",p,finish,REQUEST["transport"],lambda _:None)
    assert result["complete"] and len(resumed)==1 and resumed[0]["page_token"]=="next"
    attempts=sorted((tmp_path/"cells/2016-01-04").glob("page-002-attempt-*.json"))
    assert len(attempts)==2 and json.loads(attempts[0].read_text())["state"]=="request_started"


def test_retry_failure_and_token_cycle_are_retained(tmp_path):
    responses=[reply([], status=503), reply([], "cycle"), reply([], "cycle")]
    result=capture.capture_pages(tmp_path,"2016-01-04",{"symbols":"AAPL"},lambda p:responses.pop(0),REQUEST["transport"],lambda _:None)
    assert not result["complete"] and result["error"]=="repeated_page_token"
    attempts=sorted((tmp_path/"cells/2016-01-04").glob("page-001-attempt-*.json"))
    assert len(attempts)==2 and json.loads(attempts[0].read_text())["status_code"]==503


def test_denied_access_stops_without_substitution(tmp_path):
    result=capture.capture_pages(tmp_path,"2016-01-04",{"symbols":"AAPL"},lambda p:reply([],status=403),REQUEST["transport"],lambda _:None)
    assert not result["complete"] and result["stop_all"] and result["error"]=="http_403"
    assert len(list((tmp_path/"cells/2016-01-04").glob("page-*.json")))==1


def test_coverage_missing_intervals_and_boundaries():
    session=next(x for x in CALENDAR if x["session"]=="2024-11-29")
    opening=datetime.fromisoformat(session["open"])
    values=[bar(opening+timedelta(minutes=i)) for i in range(210) if i not in (4,5,76)]
    values.append(bar(datetime.fromisoformat(session["close"])))
    row=capture.analyze_session({"AAPL":values},session,["AAPL"])[0]
    assert row["expected_minutes"]==210 and row["valid_unique_minutes"]==207
    assert row["missing_intervals"]==[{"start":(opening+timedelta(minutes=4)).isoformat(),"end_exclusive":(opening+timedelta(minutes=6)).isoformat(),"minutes":2},{"start":(opening+timedelta(minutes=76)).isoformat(),"end_exclusive":(opening+timedelta(minutes=77)).isoformat(),"minutes":1}]
    assert not row["opening_complete"] and not row["entry_bar_valid"] and row["exit_bar_valid"]
    assert row["out_of_window"]==1


def test_duplicate_and_invalid_prices_never_become_complete():
    session=CALENDAR[0];opening=datetime.fromisoformat(session["open"])
    values=[bar(opening+timedelta(minutes=i)) for i in range(session["minutes"])]
    values[0]["h"]=8
    values.insert(77,dict(values[76]))
    row=capture.analyze_session({"AAPL":values},session,["AAPL"])[0]
    assert row["invalid_records"]==1 and row["duplicate_timestamps"]==1
    assert not row["opening_complete"] and not row["entry_bar_valid"] and not row["full_session_complete"]


def test_reused_early_close_and_fixed_mapping():
    row=next(x for x in CALENDAR if x["session"]=="2024-11-29")
    params=capture.session_params(REQUEST,row)
    assert params["symbols"]=="F,T,HRL,BANF,SPY" and params["asof"]==row["session"]
    payload,sources=capture.reused_bars(REQUEST,row["session"],ROOT.parents[1])
    coverage=capture.analyze_session(payload,row,["AAPL","MSFT"])
    assert len(sources)==1 and all(x["full_session_complete"] and x["opening_complete"] and x["entry_bar_valid"] and x["exit_bar_valid"] for x in coverage)
    assert sum(x["raw_records"] for x in coverage)==420
    assert hashlib.sha256((ROOT/"calendar.json").read_bytes()).hexdigest()==REQUEST["calendar"]["sha256"]


def test_delay_and_calendar_anchors():
    by_day={x["session"]:x for x in CALENDAR}
    assert len(CALENDAR)==2514 and "2018-12-05" not in by_day and "2025-01-09" not in by_day
    assert by_day["2024-11-29"]["minutes"]==210
    opening=datetime.fromisoformat(by_day["2024-11-29"]["open"])
    signal_available=opening+timedelta(minutes=60+15+1)
    assert signal_available==opening+timedelta(minutes=REQUEST["coverage"]["entry_offset_minutes"])
    assert datetime.fromisoformat(by_day["2016-03-11"]["open"]).hour==14
    assert datetime.fromisoformat(by_day["2016-03-14"]["open"]).hour==13
