"""Declare the isolated source-only request without making network calls."""
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SYMBOLS = ["AAPL", "MSFT", "F", "T", "HRL", "BANF", "SPY"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declare():
    assert not (ROOT / "request.json").exists(), "Frozen request already exists"
    calendar = xcals.get_calendar("XNYS", start="2016-01-01", end="2025-12-31")
    sessions = []
    for day in calendar.sessions:
        opening, closing = calendar.session_open(day), calendar.session_close(day)
        sessions.append({"session": str(day.date()), "open": opening.isoformat(), "close": closing.isoformat(),
                         "minutes": int((closing-opening).total_seconds()/60),
                         "phase": "warmup" if day.year == 2016 else "evaluation"})
    by_day = {row["session"]: row for row in sessions}
    assert "2018-12-05" not in by_day and "2025-01-09" not in by_day
    assert by_day["2024-11-29"]["minutes"] == 210
    assert pd.Timestamp(by_day["2016-03-11"]["open"]).hour == 14
    assert pd.Timestamp(by_day["2016-03-14"]["open"]).hour == 13
    assert all(pd.Timestamp(row["open"]).tz_convert("America/New_York").strftime("%H:%M") == "09:30" for row in sessions)
    fixture = REPO / ".qualification/hourly-expansion20260919/sip-minute-20241129-regular-early-close.capture.json"
    meta = json.loads(fixture.read_text(encoding="utf-8"))
    raw = fixture.parent / meta["raw_file"]
    assert digest(raw) == meta["sha256"] and not json.loads(raw.read_bytes()).get("next_page_token")
    assert meta["params"]["asof"] == "2024-11-29" and meta["params"]["feed"] == "sip"
    assert meta["params"]["adjustment"] == "raw" and meta["params"]["timeframe"] == "1Min"
    calendar_path = ROOT / "calendar.json"
    calendar_path.write_text(json.dumps(sessions, indent=2)+"\n", encoding="utf-8")
    request = {
        "study": "intraday-opening-source-20260928-v1", "declared_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Historical source capture and coverage only; no strategy outcomes, account calls, orders or new spending",
        "symbols": SYMBOLS, "first_session": sessions[0]["session"], "last_session": sessions[-1]["session"],
        "warmup_year": 2016, "evaluation_years": list(range(2017,2026)),
        "endpoint": "https://data.alpaca.markets/v2/stocks/bars", "method": "GET",
        "params": {"timeframe":"1Min", "feed":"sip", "adjustment":"raw", "currency":"USD", "sort":"asc", "limit":10000},
        "cell": "One exchange session, all seven symbols except explicitly reused fixture symbols",
        "start": "Inclusive actual exchange open UTC", "end": "Inclusive actual exchange close minus one second UTC",
        "entity_mapping": "Explicit asof=each session date; vendor underlying-entity mapping, not independently verified issuer ID, dated membership or information vintage",
        "calendar": {"name":"XNYS", "path":"calendar.json", "sha256":digest(calendar_path), "sessions":len(sessions),
                     "symbol_sessions":len(sessions)*len(SYMBOLS), "expected_minute_slots":sum(x["minutes"] for x in sessions)*len(SYMBOLS),
                     "provenance":"Installed exchange_calendars US equity schedule with independently checked closure/early-close/DST anchors", 
                     "independent_anchors":["2018-12-05 closed", "2025-01-09 closed", "2024-11-29 closes13:00ET", "2016-03-11/14 UTC open moves14:30 to13:30"]},
        "reused": [{"session":"2024-11-29", "symbols":["AAPL","MSFT"], "metadata":fixture.relative_to(REPO).as_posix(),
                    "metadata_sha256":digest(fixture), "raw":raw.relative_to(REPO).as_posix(), "raw_sha256":digest(raw),
                    "currency":"USD default in original request", "captured_at":meta["retrieved_at"]}],
        "transport": {"minimum_request_interval_seconds":0.6, "timeout_seconds":30, "maximum_attempts_per_page":3,
                      "maximum_pages_per_session":10, "maximum_total_new_requests":8000,
                      "retry_http_status":[429,500,502,503,504], "retry_wait_seconds":[5,15], "stop_all_http_status":[401,403],
                      "resume":"Verify cached successful page bytes/parameters and continue next token; retain every failed/interrupted attempt; never refetch a successful page",
                      "redirects":False, "pagination":"Continue until null token, independent of page row count; repeated token fails cell"},
        "coverage": {"timestamp_tolerance_seconds":0, "ohlc_order_tolerance":0, "missing_minute_tolerance_for_complete_opening_hour":0,
                     "opening_range":"[session open, session open+60min)", "entry_offset_minutes":76, "exit_offset_minutes":196,
                     "required_signal_delay_minutes":15, "processing_latency_minutes":1,
                     "all_minutes":"Retain [open,close); exact closing-auction minute excluded; no claim equal to official daily OHLCV",
                     "checks":["All seven symbol/session cells retained, including empty/error cells", "Unique UTC minute starts and increasing per-symbol source order", "Finite positive OHLC; low<=open,close<=high; nonnegative finite volume and integer trade count", "Separate missing/invalid/duplicate/unaligned/out-of-window records; no fill, interpolation or invented bars", "Report full-session and opening-hour coverage independently, plus exact10:46/12:46 source-bar presence", "Every missing interval retained; absence can reflect no eligible trade, a halt or source failure, never automatically a vendor outage", "Raw hashes, page tokens, request bounds/asof, response dates, captured times and all failures retained"],
                     "qualification":"Transport completion alone is not usable coverage. Later strategy must abstain on incomplete observed opening hours; entry/exit missingness must not screen earlier signals. No strategy PnL is computed here."},
        "vintage_limits":["Today-retrieved provider revisions, not historical publication timestamps", "15-minute restriction plus processing latency implies opening hour cannot act before10:46ET; no real-time SIP entitlement assumed", "Raw same-session units avoid overnight action returns; cross-session volume comparisons still require action-aware research declaration", "Seven surviving names are purposive pilot, not broad historical membership"],
        "dependencies": {name:importlib.metadata.version(name) for name in ["exchange-calendars","pandas","numpy","httpx","tzdata"]},
        "primary_source_urls":["https://docs.alpaca.markets/us/reference/stockbars", "https://docs.alpaca.markets/us/docs/market-data-faq", "https://docs.alpaca.markets/us/docs/about-market-data-api", "https://www.nasdaqtrader.com/TraderNews.aspx?id=UTP2024-16", "https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-closure-its-us-markets-honor-national-day", "https://ir.nasdaq.com/node/108411/pdf"]
    }
    (ROOT/"request.json").write_text(json.dumps(request,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"sessions":len(sessions), "symbol_sessions":request["calendar"]["symbol_sessions"], "minute_slots":request["calendar"]["expected_minute_slots"], "calendar_sha256":digest(calendar_path), "request_sha256":digest(ROOT/"request.json")}))


if __name__ == "__main__":
    declare()
