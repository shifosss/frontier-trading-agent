from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pytest
import prepare_market as module


def payload():
    return {"chart": {"result": [{"meta": {"symbol": "AAA", "currency": "USD"},
            "timestamp": [int(datetime.fromisoformat(s).timestamp()) for s in
                ("2020-01-02T21:00:00+00:00", "2020-01-03T21:00:00+00:00")],
            "indicators": {"quote": [{"close": [5, 6], "volume": [100, 200]}]}}]}}


def test_original_quote_units_and_missing_sessions():
    p = payload(); original = deepcopy(p)
    close, volume, audit = module.vendor_arrays(p, "AAA", ["2020-01-02", "2020-01-03", "2020-01-06"])
    np.testing.assert_array_equal(close, [5, 6, np.nan])
    np.testing.assert_array_equal(volume, [100, 200, np.nan])
    assert audit["missing_sessions"] == ["2020-01-06"] and p == original


@pytest.mark.parametrize("kind", ["symbol", "currency", "length", "duplicate"])
def test_ambiguous_quote_structure_is_rejected(kind):
    p = payload();r = p["chart"]["result"][0]
    if kind == "symbol":r["meta"]["symbol"] = "OTHER"
    if kind == "currency":r["meta"]["currency"] = "CAD"
    if kind == "length":r["indicators"]["quote"][0]["close"].pop()
    if kind == "duplicate":r["timestamp"][1] = r["timestamp"][0]
    with pytest.raises(ValueError):module.vendor_arrays(p, "AAA", ["2020-01-02", "2020-01-03"])


def test_invalid_original_row_remains_missing_without_filling():
    p=payload();p["chart"]["result"][0]["indicators"]["quote"][0]["volume"][0]=-1
    _,v,a=module.vendor_arrays(p,"AAA",["2020-01-02","2020-01-03"])
    assert np.isnan(v[0]) and v[1]==200 and a["invalid_sessions"]==["2020-01-02"]


def test_offline_fixed_cohort_preparation_preserves_missing_symbol(tmp_path, monkeypatch):
    repo=tmp_path;root=repo/"inputs";root.mkdir();capture=repo/"capture";capture.mkdir()
    code=repo/"prepare_market.py";code.write_bytes(Path(module.__file__).read_bytes())
    monkeypatch.setattr(module,"REPO",repo);monkeypatch.setattr(module,"ROOT",root);monkeypatch.setattr(module,"__file__",str(code))
    selected=[{"symbol":f"S{i:03}","cik":str(i+1).zfill(10)} for i in range(100)]
    symbols=sorted([r["symbol"] for r in selected]+["SPY"])
    days=["2020-01-02","2020-01-03"]
    old={"symbols":symbols[:-1],"sessions":days,"settlement_index":np.array([1,2])}
    for key in ("close","adjusted","atr"):old[key]=np.arange(200,dtype=float).reshape(2,100)+1
    joblib.dump((old,None),repo/"cache.joblib")
    def save(name,value):(repo/name).write_text(json.dumps(value))
    records=[];hashes=[]
    for symbol in symbols[:-1]:
        p=payload();p["chart"]["result"][0]["meta"]["symbol"]=symbol
        path=capture/(symbol+".json");path.write_text(json.dumps(p));digest=module.sha(path)
        records.append({"symbol":symbol,"path":path.name,"sha256":digest,"captured_at":"2026-09-18T21:00:00+00:00","url":"saved-fixture"})
        hashes.append({"symbol":symbol,"sha256":digest})
    save("cohort.json",{"selected":selected});save("calendar.json",{"sessions":[{"session":d} for d in days]})
    save("manifest.json",{"sha256":module.sha(repo/"cache.joblib")});save("evidence.json",{"source_hashes":hashes});save("index.json",records)
    paths={"cohort":"cohort.json","calendar":"calendar.json","cache":"cache.joblib","cache_manifest":"manifest.json",
           "cache_source_evidence":"evidence.json","capture_index":"index.json","capture_workspace":"capture"}
    names={v for k,v in paths.items() if k!="capture_workspace"}|{"prepare_market.py"}
    definition={"paths":paths,"inputs":{n:module.sha(repo/n) for n in names},"dependencies":{}}
    save("definition.json",definition)
    output=module.prepare(repo/"definition.json")
    market=module.read(output/"market-inputs.json");complete=module.read(output/"completion.json")
    assert len(market["cohort_order"])==100 and len(market["symbols"])==101
    assert complete["copied_histories"]==100 and complete["mapped_quotes"]==100
    assert market["source_by_symbol"][-1]["symbol"]=="SPY" and market["source_by_symbol"][-1]["cache_status"]=="unavailable"
    with np.load(output/"market-arrays.npz") as arrays:
        np.testing.assert_array_equal(arrays["close"][:,:-1],old["close"])
        assert np.isnan(arrays["close"][:,-1]).all()
        assert (arrays["vendor_quote_close"][:,0]==[5,6]).all()
    assert not market["features_or_returns_computed"]
