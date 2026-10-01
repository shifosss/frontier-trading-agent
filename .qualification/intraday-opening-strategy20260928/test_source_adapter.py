"""Bounded read-only adapter checks; no strategy outcomes or network."""
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parent
CAPTURE=ROOT.parent/"intraday-opening20260928"
spec=importlib.util.spec_from_file_location("source_adapter",ROOT/"source_adapter.py")
adapter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
HASH=hashlib.sha256((CAPTURE/"request.json").read_bytes()).hexdigest()
MANIFEST=adapter.load_manifest(CAPTURE,HASH)


def bar(session,offset,**fields):
    return {"t":(datetime.fromisoformat(session["open"])+timedelta(minutes=offset)).isoformat(),"o":10,"h":11,"l":9,"c":10.5,"v":100,"n":2,**fields}


def fixture(tmp_path,rows,token=None,complete=True,session=None):
    root=tmp_path/"project/.qualification/capture"
    root.mkdir(parents=True)
    request=json.loads(json.dumps(MANIFEST["request"]))
    request["reused"]=[]
    manifest={**MANIFEST,"root":str(root.resolve()),"request":request}
    session=session or manifest["sessions"][0]
    params={**request["params"],"symbols":",".join(manifest["symbols"]),"start":session["open"],"end":(datetime.fromisoformat(session["close"])-timedelta(seconds=1)).isoformat(),"asof":session["session"]}
    raw=json.dumps({"bars":{"AAPL":rows},"next_page_token":token}).encode()
    digest=hashlib.sha256(raw).hexdigest()
    (root/"raw").mkdir();(root/"raw"/(digest+".json")).write_bytes(raw)
    source={"origin":"new_capture","state":"success","status_code":200,"raw_file":"raw/"+digest+".json","sha256":digest,"params":params,"page":1}
    cell={"request_sha256":HASH,"session":session["session"],"params":params,"sources":[source],"transport_complete":complete,"error":None if complete else "http_503"}
    path=root/"cells"/session["session"]/"coverage.json";path.parent.mkdir(parents=True)
    path.write_text(json.dumps(cell),encoding="utf-8")
    return root,manifest,session,cell


def test_real_valid_and_sparse_capture_retains_exact_rows():
    row=MANIFEST["sessions"][0]
    bars,audit=adapter.read_session(CAPTURE,row,MANIFEST)
    assert audit["transport_complete"] and not audit["source_errors"] and not audit["anomalies"]
    assert len(bars["AAPL"])==390 and len(bars["BANF"])==59
    assert len(audit["request_attempts"])==1 and audit["request_attempts"][0]["state"]=="success"
    assert 76 in bars["AAPL"] and 76 not in bars["BANF"]
    source=audit["sources"][0]
    payload=json.loads((CAPTURE/source["raw_file"]).read_bytes())
    assert bars["AAPL"][76]==payload["bars"]["AAPL"][76]


def test_missing_request_is_explicit(tmp_path):
    manifest={**MANIFEST,"root":str(tmp_path.resolve())}
    bars,audit=adapter.read_session(tmp_path,manifest["sessions"][0],manifest)
    assert set(bars)==set(MANIFEST["symbols"]) and not any(bars.values())
    assert not audit["transport_complete"] and audit["source_errors"]==[{"reason":"session_not_captured"}]


def test_missing_page_preserves_partial_bars(tmp_path):
    row=MANIFEST["sessions"][0]
    root,manifest,session,_=fixture(tmp_path,[bar(row,0)],token="still-more",complete=False)
    failed=root/"cells"/session["session"]/"page-002-attempt-001.json"
    failed.write_text(json.dumps({"state":"failed","page":2,"attempt":1,"status_code":503,"error":"http_503"}),encoding="utf-8")
    bars,audit=adapter.read_session(root,session,manifest)
    assert audit["request_attempts"][0]["error"]=="http_503"
    assert audit["request_attempts"][0]["metadata_sha256"]==hashlib.sha256(failed.read_bytes()).hexdigest()
    assert list(bars["AAPL"])==[0] and not audit["transport_complete"]
    assert {x["reason"] for x in audit["source_errors"]}=={"incomplete_transport","missing_request_or_remaining_page"}


def test_duplicates_invalid_unaligned_and_boundary_retained(tmp_path):
    row=MANIFEST["sessions"][0]
    rows=[bar(row,0),bar(row,1,h=8),bar(row,2),bar(row,2),bar(row,2.5),bar(row,row["minutes"])]
    root,manifest,session,_=fixture(tmp_path,rows)
    bars,audit=adapter.read_session(root,session,manifest)
    assert list(bars["AAPL"])==[0]
    assert {x["reason"] for x in audit["anomalies"]}=={"invalid_bar","duplicate_timestamp","unaligned_timestamp","out_of_session"}
    duplicate=next(x for x in audit["anomalies"] if x["reason"]=="duplicate_timestamp")
    assert len(duplicate["rows"])==2 and all("bar" in x and "sha256" in x for x in duplicate["rows"])


def test_raw_hash_corruption_refuses_input(tmp_path):
    root,manifest,session,cell=fixture(tmp_path,[])
    (root/cell["sources"][0]["raw_file"]).write_bytes(b"changed")
    with pytest.raises(ValueError,match="hash mismatch"):
        adapter.read_session(root,session,manifest)


def test_wrong_entity_asof_refuses_input(tmp_path):
    root,manifest,session,cell=fixture(tmp_path,[])
    cell["params"]["asof"]="2025-12-31"
    cell["sources"][0]["params"]["asof"]="2025-12-31"
    (root/"cells"/session["session"]/"coverage.json").write_text(json.dumps(cell),encoding="utf-8")
    with pytest.raises(ValueError,match="parameters differ"):
        adapter.read_session(root,session,manifest)


def test_existing_early_close_reuse(tmp_path):
    row=next(x for x in MANIFEST["sessions"] if x["session"]=="2024-11-29")
    root,manifest,session,cell=fixture(tmp_path,[],session=row)
    request=json.loads(json.dumps(MANIFEST["request"]))
    manifest["request"]=request
    source={"origin":"existing_fixture",**request["reused"][0]}
    repo=root.parents[1]
    for key in ("raw","metadata"):
        destination=repo/source[key];destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(CAPTURE.parents[1]/source[key],destination)
    cell["params"]["symbols"]="F,T,HRL,BANF,SPY"
    cell["sources"][0]["params"]=cell["params"].copy()
    raw=json.dumps({"bars":{},"next_page_token":None}).encode();digest=hashlib.sha256(raw).hexdigest()
    (root/"raw"/(digest+".json")).write_bytes(raw)
    cell["sources"][0].update(raw_file="raw/"+digest+".json",sha256=digest)
    cell["sources"].insert(0,source)
    (root/"cells"/session["session"]/"coverage.json").write_text(json.dumps(cell),encoding="utf-8")
    bars,audit=adapter.read_session(root,session,manifest)
    assert audit["transport_complete"] and len(bars["AAPL"])==len(bars["MSFT"])==210
    assert 76 in bars["AAPL"] and 196 in bars["MSFT"] and 210 not in bars["AAPL"]


def test_generator_order_and_audit_sink():
    rows=MANIFEST["sessions"][:2];audits=[]
    values=list(adapter.iter_daily_bars(MANIFEST,audits.append,rows))
    assert len(values)==2 and [a["session"] for a in audits]==[r["session"] for r in rows]
    assert [len(x["BANF"]) for x in values]==[59,162]
