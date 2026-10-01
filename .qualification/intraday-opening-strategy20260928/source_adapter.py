"""Read frozen minute captures without modifying sources or filling observations."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(capture_root, expected_request_sha256):
    root=Path(capture_root).resolve()
    if _sha(root/"request.json") != expected_request_sha256:
        raise ValueError("Source request identity mismatch")
    request=_read(root/"request.json")
    if request["endpoint"] != "https://data.alpaca.markets/v2/stocks/bars" or request["params"]["feed"] != "sip" or request["params"]["adjustment"] != "raw" or request["params"]["timeframe"] != "1Min":
        raise ValueError("Unexpected source representation")
    if _sha(root/"calendar.json") != request["calendar"]["sha256"]:
        raise ValueError("Calendar identity mismatch")
    implementation=_read(root/"implementation.json")
    if implementation["request_sha256"] != expected_request_sha256:
        raise ValueError("Capture implementation/request mismatch")
    for name,digest in implementation["files"].items():
        if _sha(root/name) != digest:
            raise ValueError("Frozen capture implementation mismatch")
    identities={"request_sha256":expected_request_sha256,"calendar_sha256":request["calendar"]["sha256"],
                "implementation_sha256":_sha(root/"implementation.json")}
    if (root/"operational-amendment.json").exists():
        identities["operational_amendment_sha256"]=_sha(root/"operational-amendment.json")
    return {"root":str(root),"request":request,"sessions":_read(root/"calendar.json"),
            "symbols":request["symbols"],"identities":identities}


def _minute_intervals(offsets):
    result=[]
    for offset in sorted(offsets):
        if result and result[-1][1]==offset:
            result[-1][1]=offset+1
        else:
            result.append([offset,offset+1])
    return result


def _canonicalize(records, session, symbols):
    opening=datetime.fromisoformat(session["open"])
    values={symbol:{} for symbol in symbols}
    counts={symbol:Counter() for symbol in symbols}
    seen={symbol:defaultdict(list) for symbol in symbols}
    anomalies=[]
    previous={}
    for symbol,bar,location in records:
        counts[symbol]["raw_records"]+=1
        try:
            stamp=datetime.fromisoformat(bar["t"])
            if stamp.tzinfo is None:
                raise ValueError("missing offset")
            stamp=stamp.astimezone(timezone.utc)
            seconds=(stamp-opening).total_seconds()
        except (KeyError,TypeError,ValueError):
            anomalies.append({**location,"symbol":symbol,"reason":"invalid_timestamp","bar":bar})
            counts[symbol]["invalid_timestamp"]+=1
            continue
        if symbol in previous and stamp < previous[symbol]:
            anomalies.append({**location,"symbol":symbol,"reason":"source_order_violation","bar":bar})
            counts[symbol]["source_order_violation"]+=1
        previous[symbol]=stamp
        if seconds % 60:
            anomalies.append({**location,"symbol":symbol,"reason":"unaligned_timestamp","bar":bar})
            counts[symbol]["unaligned_timestamp"]+=1
            continue
        offset=int(seconds/60)
        if not 0 <= offset < session["minutes"]:
            anomalies.append({**location,"symbol":symbol,"reason":"out_of_session","bar":bar})
            counts[symbol]["out_of_session"]+=1
            continue
        seen[symbol][offset].append({**location,"bar":bar})
        try:
            o,h,l,c,v=(float(bar[k]) for k in ("o","h","l","c","v"))
            good=all(math.isfinite(x) and x>0 for x in (o,h,l,c)) and math.isfinite(v) and v>=0
            good=good and l<=min(o,c)<=max(o,c)<=h and type(bar["n"]) is int and bar["n"]>=0
        except (KeyError,TypeError,ValueError):
            good=False
        if not good:
            anomalies.append({**location,"symbol":symbol,"minute_offset":offset,"reason":"invalid_bar","bar":bar})
            counts[symbol]["invalid_bar"]+=1
        elif len(seen[symbol][offset])==1:
            values[symbol][offset]=bar
    for symbol in symbols:
        for offset,rows in seen[symbol].items():
            if len(rows)>1:
                values[symbol].pop(offset,None)
                counts[symbol]["duplicate_timestamps"]+=1
                anomalies.append({"symbol":symbol,"minute_offset":offset,"reason":"duplicate_timestamp","rows":rows})
    expected=set(range(session["minutes"]))
    coverage={symbol:{**dict(counts[symbol]),"valid_minutes":len(values[symbol]),
                      "unobserved_minute_intervals":_minute_intervals(expected-set(seen[symbol])),
                      "unusable_minute_intervals":_minute_intervals(expected-set(values[symbol]))}
              for symbol in symbols}
    return values,coverage,anomalies


def read_session(capture_root, session, manifest):
    root=Path(capture_root).resolve()
    if str(root)!=manifest["root"]:
        raise ValueError("Adapter root/manifest mismatch")
    request=manifest["request"]
    path=root/"cells"/session["session"]/"coverage.json"
    audit={"session":session["session"],"source_identities":manifest["identities"],"transport_complete":False,
           "source_errors":[],"sources":[],"anomalies":[]}
    audit["request_attempts"]=[]
    for attempt_path in sorted(path.parent.glob("page-*-attempt-*.json")):
        attempt=_read(attempt_path)
        audit["request_attempts"].append({"metadata":attempt_path.relative_to(root).as_posix(),
            "metadata_sha256":_sha(attempt_path),**{k:attempt.get(k) for k in
            ("state","page","attempt","status_code","error","raw_file","sha256","started_at","captured_at")}})
    records=[]
    if not path.exists():
        audit["source_errors"].append({"reason":"session_not_captured"})
        values,audit["coverage"],audit["anomalies"]=_canonicalize(records,session,manifest["symbols"])
        return values,audit
    cell=_read(path)
    audit["coverage_file_sha256"]=_sha(path)
    if cell["request_sha256"]!=manifest["identities"]["request_sha256"] or cell["session"]!=session["session"]:
        raise ValueError("Session capture identity mismatch")
    audit["transport_complete"]=bool(cell["transport_complete"])
    if not cell["transport_complete"]:
        audit["source_errors"].append({"reason":"incomplete_transport","detail":cell.get("error")})
    reused={r["session"]:r for r in request["reused"]}
    new_sources=[]
    observed_reuse=set()
    for source in cell["sources"]:
        if source["origin"]=="existing_fixture":
            expected=reused.get(session["session"])
            if expected is None or any(source.get(k)!=v for k,v in expected.items()):
                raise ValueError("Reused fixture identity mismatch")
            repo=root.parents[1]
            if _sha(repo/source["metadata"])!=source["metadata_sha256"] or _sha(repo/source["raw"])!=source["raw_sha256"]:
                raise ValueError("Reused raw/metadata hash mismatch")
            payload=_read(repo/source["raw"])
            included=source["symbols"]
            observed_reuse.update(included)
            location={"raw":source["raw"],"sha256":source["raw_sha256"],"origin":"existing_fixture"}
            if payload.get("next_page_token"):
                raise ValueError("Reused fixture pagination incomplete")
        else:
            new_sources.append(source)
            raw=root/source["raw_file"]
            if _sha(raw)!=source["sha256"]:
                raise ValueError("Captured raw hash mismatch")
            if source["origin"]!="new_capture" or source["state"]!="success" or source["status_code"]!=200:
                raise ValueError("Unexpected successful source metadata")
            payload=_read(raw)
            included=source["params"]["symbols"].split(",")
            location={"raw":source["raw_file"],"sha256":source["sha256"],"origin":"new_capture","page":source["page"]}
        if set(payload.get("bars",{}))-set(included):
            raise ValueError("Unexpected source response symbol")
        for symbol in included:
            if symbol not in manifest["symbols"]:
                raise ValueError("Unexpected requested symbol")
            records.extend((symbol,bar,{**location,"row":i}) for i,bar in enumerate(payload.get("bars",{}).get(symbol,[])))
        audit["sources"].append(source)
    expected_reuse=set(reused.get(session["session"],{}).get("symbols",[]))
    if observed_reuse!=expected_reuse:
        audit["source_errors"].append({"reason":"missing_reused_source"})
    expected_symbols=",".join(s for s in manifest["symbols"] if s not in expected_reuse)
    expected_params={**request["params"],"symbols":expected_symbols,"start":session["open"],
                     "end":(datetime.fromisoformat(session["close"])-timedelta(seconds=1)).isoformat(),"asof":session["session"]}
    if cell["params"]!=expected_params:
        raise ValueError("Session parameters differ from frozen source request")
    previous_token=None
    for page,source in enumerate(new_sources,start=1):
        expected={**expected_params,**({"page_token":previous_token} if previous_token else {})}
        if source["params"]!=expected or source["page"]!=page or source["params"]["symbols"]!=expected_symbols:
            raise ValueError("Captured page chain/request mismatch")
        previous_token=_read(root/source["raw_file"]).get("next_page_token")
        if previous_token is None and page<len(new_sources):
            raise ValueError("Extra page after completed source chain")
    if not new_sources or previous_token:
        audit["source_errors"].append({"reason":"missing_request_or_remaining_page"})
    if audit["source_errors"]:
        audit["transport_complete"]=False
    values,audit["coverage"],audit["anomalies"]=_canonicalize(records,session,manifest["symbols"])
    return values,audit


def iter_daily_bars(manifest, audit_sink=None, sessions=None):
    """The simulator consumes mappings; caller retains every audit alongside results."""
    for session in manifest["sessions"] if sessions is None else sessions:
        values,audit=read_session(manifest["root"],session,manifest)
        if audit_sink is not None:
            audit_sink(audit)
        yield values
