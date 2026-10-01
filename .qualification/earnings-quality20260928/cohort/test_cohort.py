import copy
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


def module():
    spec = importlib.util.spec_from_file_location("earnings_cohort", Path(__file__).with_name("cohort.py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prices():
    days = ["2016-01-04", "2016-01-05", "2016-01-06", "2025-01-06"]
    times = [int(datetime.fromisoformat(d + "T15:00:00+00:00").timestamp()) for d in days]
    return {"chart": {"result": [{"meta": {"symbol": "AAA", "currency": "USD"}, "timestamp": times,
             "indicators": {"quote": [{"close": [10., 20., 30., 999.], "volume": [1e6, 1e6, 1e6, 1e12]}]}}]}}, days[:3]


def spec(symbol, title=None):
    return {"symbol": symbol, "source_symbol": symbol, "currency": "USD", "asset_type": "stock",
            "name": title or symbol + " Common Stock", "is_etf": False, "is_test": False, "next_shares": False}


def rules():
    return {"minimum_observations": 2, "minimum_median_dollar_activity": 5e6,
            "hash_seed": "frontier-cash-backed-earnings-v1:", "discovery_pool_limit": 3, "target_issuers": 2}


def test_liquidity_reads_only_2016_quote_units():
    m = module(); payload, calendar = prices()
    first = m.liquidity_2016(payload, "AAA", calendar)
    assert first["observations"] == 3 and first["median_dollar_activity"] == 20e6
    later = copy.deepcopy(payload); q = later["chart"]["result"][0]
    q["indicators"]["quote"][0]["close"][-1] = -1e50
    q["indicators"]["quote"][0]["volume"][-1] = None
    q["indicators"]["adjclose"] = [{"adjclose": [999999., 999999., 999999., 1]}]
    q["events"] = {"splits": {"future": {"numerator": 1000}}}
    assert m.liquidity_2016(later, "AAA", calendar) == first


def test_missing_and_duplicate_2016_observations_are_explicit():
    m = module(); p, days = prices(); q = p["chart"]["result"][0]
    q["indicators"]["quote"][0]["close"][1] = None
    out = m.liquidity_2016(p, "AAA", days)
    assert out["observations"] == 2 and out["unavailable_sessions"] == [days[1]]
    q["timestamp"].append(q["timestamp"][0])
    q["indicators"]["quote"][0]["close"].append(10.)
    q["indicators"]["quote"][0]["volume"].append(1e6)
    out = m.liquidity_2016(p, "AAA", days)
    assert out["status"] == "invalid_duplicate_session" and out["duplicate_sessions"] == [days[0]]


def test_zero_volume_is_observed_but_nonfinite_product_is_not():
    m = module(); p, days = prices(); q = p["chart"]["result"][0]["indicators"]["quote"][0]
    q["volume"][0] = 0; q["close"][1] = float("inf")
    out = m.liquidity_2016(p, "AAA", days)
    assert out["observations"] == 2 and out["median_dollar_activity"] == 15e6


def test_exact_mapping_and_qualifying_common_share_dedup():
    m = module(); instruments = [spec("A"), spec("A-A"), spec("A-P", "A Preferred Stock"), spec("B.B"), spec("C")]
    mapping = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1,"A","A","NYSE"], [1,"A","A-A","NYSE"], [1,"A","A-P","NYSE"], [2,"B","B-B","NYSE"], [3,"C","C","NYSE"], [4,"C","C","NYSE"]]}
    liq = {x["symbol"]: {"status": "usable", "observations": 200, "median_dollar_activity": 10e6} for x in instruments}
    liq["A-A"]["median_dollar_activity"] = 20e6; liq["A-P"]["median_dollar_activity"] = 100e6
    out = m.make_screening_pool(instruments, mapping, liq, rules())
    assert [(x["cik"],x["symbol"]) for x in out["members"]] == [("0000000001","A-A")]
    reasons = {x["symbol"]: x["reason"] for x in out["excluded"]}
    assert reasons["A"] == "another_qualifying_share_class_selected"
    assert reasons["A-P"] == "security_title_excluded" and reasons["B.B"] == "exact_cik_mapping_absent"
    assert reasons["C"] == "ambiguous_cik_mapping"


def profile(cik, symbol):
    return {"cik": int(cik), "tickers": [symbol], "entityType": "operating", "sic": "3571", "stateOfIncorporation": "CA"}


def test_current_profile_excludes_unknown_financial_foreign_and_nonoperating():
    m=module(); row={"cik":"0000000001","symbol":"A"}; base=profile(1,"A")
    assert m.profile_reasons(row,base) == []
    for key,value,reason in [("sic","6021","sic_outside_declared_operating_ranges"), ("sic","0000","sic_outside_declared_operating_ranges"), ("sic","9995","sic_outside_declared_operating_ranges"), ("sic","","sic_missing_or_invalid"), ("stateOfIncorporation","E9","incorporation_not_50_states_or_dc"), ("entityType","investment","entity_not_operating")]:
        changed={**base,key:value}; assert reason in m.profile_reasons(row,changed)
    assert "exact_ticker_missing_from_submissions" in m.profile_reasons(row,{**base,"tickers":["A-P"]})


def test_hash_order_is_reproducible_and_no_discovery_pool_refill():
    m=module(); ins=[spec(chr(65+i)) for i in range(5)]
    mp={"fields":["cik","ticker"],"data":[[i+1,x["symbol"]] for i,x in enumerate(ins)]}
    liq={x["symbol"]:{"status":"usable","observations":200,"median_dollar_activity":10e6} for x in ins}
    pool=m.make_screening_pool(ins,mp,liq,rules())
    reverse=m.make_screening_pool(list(reversed(ins)),mp,liq,rules())
    assert pool["members"] == reverse["members"] and len(pool["members"])==3
    ps={x["cik"]:profile(x["cik"],x["symbol"]) for x in pool["members"]}
    first=pool["members"][0]["cik"]; ps[first]["sic"]="6021"
    second=pool["members"][1]["cik"]; ps.pop(second)
    out=m.qualify_pool(pool,ps,rules())
    assert out["status"]=="insufficient_qualified_issuers" and len(out["selected"])==1
    assert len(out["classification"])==3 and out["discovery_pool_refilled"] is False


def test_exact_source_symbol_and_currency_are_required():
    m=module(); p,days=prices(); p["chart"]["result"][0]["meta"]["symbol"]="OTHER"
    with pytest.raises(ValueError,match="symbol/currency"):m.liquidity_2016(p,"AAA",days)
