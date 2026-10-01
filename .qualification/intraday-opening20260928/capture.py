"""Isolated raw SIP minute cache; data GET only, no strategy or broker operations."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import time

import httpx
from frontier.paper_broker import _paper_credentials

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
SAFE_HEADERS = ("date", "content-type", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "x-request-id", "retry-after")


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def session_params(request, session):
    reused = {s for r in request["reused"] if r["session"] == session["session"] for s in r["symbols"]}
    closing = datetime.fromisoformat(session["close"])
    return {**request["params"], "symbols": ",".join(s for s in request["symbols"] if s not in reused),
            "start": session["open"], "end": (closing-timedelta(seconds=1)).isoformat(), "asof": session["session"]}


def reused_bars(request, day, repo):
    bars, sources = {}, []
    for source in request["reused"]:
        if source["session"] != day:
            continue
        meta_path, raw_path = repo/source["metadata"], repo/source["raw"]
        if sha(meta_path) != source["metadata_sha256"] or sha(raw_path) != source["raw_sha256"]:
            raise ValueError("reused source hash mismatch")
        meta, body = read(meta_path), read(raw_path)
        assert not body.get("next_page_token") and meta["status_code"] == 200
        for symbol in source["symbols"]:
            bars[symbol] = body["bars"].get(symbol, [])
        sources.append({"origin":"existing_fixture", **source})
    return bars, sources


def get_page(root, day, page, params, fetch, settings, sleep):
    directory = root/"cells"/day
    directory.mkdir(parents=True, exist_ok=True)
    previous = sorted(directory.glob(f"page-{page:03d}-attempt-*.json"))
    for path in previous:
        meta = read(path)
        if meta["params"] != params or meta["url"] != ENDPOINT:
            raise ValueError("cached request identity mismatch")
        if meta["state"] == "success":
            raw = root/meta["raw_file"]
            if sha(raw) != meta["sha256"]:
                raise ValueError("cached raw hash mismatch")
            return json.loads(raw.read_bytes()), meta
    for attempt in range(len(previous)+1, settings["maximum_attempts_per_page"]+1):
        path = directory/f"page-{page:03d}-attempt-{attempt:03d}.json"
        meta = {"method":"GET", "url":ENDPOINT, "params":params.copy(), "started_at":now(),
                "session":day, "page":page, "attempt":attempt, "state":"request_started"}
        write(path, meta)
        try:
            status, raw, headers = fetch(params)
            digest = hashlib.sha256(raw).hexdigest()
            raw_path = root/"raw"/(digest+".json")
            raw_path.parent.mkdir(exist_ok=True)
            if raw_path.exists():
                if sha(raw_path) != digest:
                    raise ValueError("content-addressed raw hash mismatch")
            else:
                raw_temp = raw_path.with_suffix(f".{day}-{page}-{attempt}.tmp")
                raw_temp.write_bytes(raw)
                raw_temp.replace(raw_path)
            meta.update(status_code=status, raw_file=raw_path.relative_to(root).as_posix(), sha256=digest,
                        bytes=len(raw), captured_at=now(), headers={k:headers[k] for k in SAFE_HEADERS if k in headers})
            body = None
            if status == 200:
                try:
                    body = json.loads(raw)
                    assert isinstance(body, dict) and isinstance(body.get("bars", {}), dict)
                    assert body.get("next_page_token") is None or isinstance(body["next_page_token"], str)
                    assert set(body.get("bars", {})) <= set(params["symbols"].split(","))
                    assert all(isinstance(rows, list) for rows in body.get("bars", {}).values())
                    meta["state"] = "success"
                except (ValueError, TypeError, AssertionError):
                    meta.update(state="failed", error="invalid_response_schema")
            else:
                meta.update(state="failed", error=f"http_{status}")
            write(path, meta)
            if meta["state"] == "success":
                return body, meta
            if status not in settings["retry_http_status"]:
                return None, meta
        except httpx.HTTPError as exc:
            meta.update(state="failed", error=type(exc).__name__, completed_at=now())
            write(path, meta)
        if attempt < settings["maximum_attempts_per_page"]:
            delay = settings["retry_wait_seconds"][attempt-1]
            retry_after = meta.get("headers", {}).get("retry-after", "")
            if str(retry_after).isdigit():
                delay = max(delay, int(retry_after))
            if delay > 60:
                meta["retry_deferred"] = "provider backoff exceeds60seconds; retained for later resume"
                write(path, meta)
                return None, meta
            sleep(delay)
    return None, read(previous[-1]) if previous and len(previous) >= settings["maximum_attempts_per_page"] else meta


def capture_pages(root, day, params, fetch, settings, sleep=time.sleep):
    values, sources, seen = defaultdict(list), [], set()
    token, error, stop_all = None, None, False
    for page in range(1, settings["maximum_pages_per_session"]+1):
        page_params = {**params, **({"page_token":token} if token else {})}
        body, meta = get_page(root, day, page, page_params, fetch, settings, sleep)
        if body is None:
            error = meta.get("error", "attempt_budget_exhausted")
            stop_all = meta.get("status_code") in settings["stop_all_http_status"]
            break
        sources.append({"origin":"new_capture", **meta})
        for symbol, rows in body.get("bars", {}).items():
            values[symbol].extend(rows)
        token = body.get("next_page_token")
        if not token:
            return {"bars":dict(values), "sources":sources, "complete":True, "error":None, "stop_all":False}
        if token in seen:
            error = "repeated_page_token"
            break
        seen.add(token)
    else:
        error = "page_budget_exhausted"
    return {"bars":dict(values), "sources":sources, "complete":False, "error":error, "stop_all":stop_all}


def intervals(values):
    result=[]
    for value in sorted(values):
        if result and result[-1]["end_exclusive"] == value.isoformat():
            result[-1]["end_exclusive"] = (value+timedelta(minutes=1)).isoformat()
            result[-1]["minutes"] += 1
        else:
            result.append({"start":value.isoformat(), "end_exclusive":(value+timedelta(minutes=1)).isoformat(), "minutes":1})
    return result


def analyze_session(bars, session, symbols):
    opening, closing = (datetime.fromisoformat(session[k]) for k in ("open", "close"))
    expected = {opening+timedelta(minutes=i) for i in range(session["minutes"])}
    first_hour = {opening+timedelta(minutes=i) for i in range(60)}
    output=[]
    for symbol in symbols:
        values=bars.get(symbol, [])
        seen, valid, invalid_times = Counter(), set(), set()
        invalid, unaligned, outside, parse_failures, order_violations = 0, 0, 0, 0, 0
        previous=None
        for b in values:
            try:
                timestamp=datetime.fromisoformat(b["t"])
                if timestamp.tzinfo is None:
                    raise ValueError("timestamp without offset")
                timestamp=timestamp.astimezone(timezone.utc)
            except (ValueError, TypeError, KeyError):
                parse_failures += 1
                continue
            if previous is not None and timestamp < previous:
                order_violations += 1
            previous=timestamp
            if timestamp.second or timestamp.microsecond:
                unaligned += 1
                continue
            if timestamp not in expected:
                outside += 1
                continue
            seen[timestamp] += 1
            try:
                o,h,l,c,v = (float(b[k]) for k in ("o","h","l","c","v"))
                n = b["n"]
                good = all(math.isfinite(x) and x > 0 for x in (o,h,l,c)) and math.isfinite(v) and v >= 0
                good = good and l <= min(o,c) <= max(o,c) <= h and isinstance(n,int) and n >= 0
            except (KeyError, ValueError, TypeError):
                good=False
            if good:
                valid.add(timestamp)
            else:
                invalid += 1
                invalid_times.add(timestamp)
        duplicates={t for t,count in seen.items() if count != 1}
        valid -= duplicates | invalid_times
        missing=expected-set(seen)
        output.append({"symbol":symbol, "session":session["session"], "phase":session["phase"],
                       "expected_minutes":len(expected), "raw_records":len(values), "observed_unique_minutes":len(seen),
                       "valid_unique_minutes":len(valid), "missing_minutes":len(missing), "missing_intervals":intervals(missing),
                       "unusable_intervals":intervals(expected-valid), "invalid_records":invalid, "duplicate_timestamps":len(duplicates),
                       "timestamp_parse_failures":parse_failures, "unaligned_timestamps":unaligned, "out_of_window":outside,
                       "order_violations":order_violations, "opening_valid_minutes":len(first_hour & valid),
                       "opening_complete":first_hour <= valid, "entry_bar_valid":opening+timedelta(minutes=76) in valid,
                       "exit_bar_valid":opening+timedelta(minutes=196) in valid,
                       "full_session_complete":expected==valid and not (parse_failures or unaligned or outside or order_violations)})
    return output


@contextmanager
def worker_lock(root):
    import msvcrt
    with (root/"capture.lock").open("a+b") as stream:
        if stream.tell()==0:
            stream.write(b"1"); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("Existing intraday capture holds capture.lock") from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def summarize(request, calendar, results):
    counters=defaultdict(Counter)
    failures=[]
    for session, result in zip(calendar,results,strict=False):
        if not result["transport_complete"]:
            failures.append({"session":session["session"],"error":result["error"]})
        for row in result["coverage"]:
            counter=counters[(row["symbol"],row["session"][:4])]
            counter["sessions"] += 1
            for key in ("expected_minutes","raw_records","valid_unique_minutes","missing_minutes","invalid_records","duplicate_timestamps","opening_complete","entry_bar_valid","exit_bar_valid","full_session_complete"):
                counter[key] += row[key]
    return {"request_sha256":sha(ROOT/"request.json"),"updated_at":now(),"requested_sessions":len(calendar),
            "processed_sessions":len(results),"pending_sessions":len(calendar)-len(results),
            "transport_complete_sessions":sum(x["transport_complete"] for x in results),"failed_sessions":failures,
            "coverage_by_symbol_year":[{"symbol":s,"year":y,**dict(count)} for (s,y),count in sorted(counters.items())],
            "limitations":request["vintage_limits"]+["Coverage counts do not diagnose missing-bar cause or establish execution fills; no strategy outcomes computed"]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-new-sessions",type=int)
    args=parser.parse_args()
    request, implementation=read(ROOT/"request.json"),read(ROOT/"implementation.json")
    assert request["endpoint"]==ENDPOINT and request["method"]=="GET"
    assert sha(ROOT/"request.json")==implementation["request_sha256"]
    assert sha(ROOT/"calendar.json")==request["calendar"]["sha256"]
    for name,digest in implementation["files"].items():
        assert sha(ROOT/name)==digest, "Frozen capture code mismatch"
    for name,version in request["dependencies"].items():
        assert importlib.metadata.version(name)==version, "Frozen dependency mismatch"
    calendar=read(ROOT/"calendar.json")
    assert datetime.fromisoformat(calendar[-1]["close"]) < datetime.now(timezone.utc)-timedelta(minutes=16)
    with worker_lock(ROOT):
        status={"phase":"running","pid":os.getpid(),"started_at":now(),"request_sha256":implementation["request_sha256"],"processed_sessions":0,"new_sessions":0}
        write(ROOT/"status.json",status)
        try:
            key,secret=_paper_credentials()
        except RuntimeError:
            status.update(phase="configuration_unavailable",updated_at=now())
            write(ROOT/"status.json",status)
            raise
        # ponytail: one serial connection suffices for seven names; no async download framework.
        with httpx.Client(headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret},timeout=request["transport"]["timeout_seconds"],follow_redirects=False) as client:
            last_request=0.0
            new_requests=0
            previous_requests=sum(1 for _ in (ROOT/"cells").glob("*/page-*-attempt-*.json"))
            def fetch(params):
                nonlocal last_request,new_requests
                if previous_requests + new_requests >= request["transport"]["maximum_total_new_requests"]:
                    raise RuntimeError("Declared request budget exhausted")
                time.sleep(max(0.0,request["transport"]["minimum_request_interval_seconds"]-(time.monotonic()-last_request)))
                last_request=time.monotonic();new_requests+=1
                response=client.get(ENDPOINT,params=params)
                return response.status_code,response.content,response.headers
            results=[]
            try:
                for session in calendar:
                    path=ROOT/"cells"/session["session"]/"coverage.json"
                    if path.exists() and read(path)["transport_complete"]:
                        result=read(path)
                        assert result["request_sha256"]==implementation["request_sha256"]
                        for source in result["sources"]:
                            if source["origin"]=="new_capture":
                                assert sha(ROOT/source["raw_file"])==source["sha256"]
                            else:
                                assert sha(REPO/source["raw"])==source["raw_sha256"]
                    else:
                        if args.max_new_sessions is not None and status["new_sessions"]>=args.max_new_sessions:
                            break
                        params=session_params(request,session)
                        captured=capture_pages(ROOT,session["session"],params,fetch,request["transport"])
                        bars,sources=reused_bars(request,session["session"],REPO)
                        for symbol,values in captured["bars"].items():
                            bars.setdefault(symbol,[]).extend(values)
                        result={"session":session["session"],"params":params,"request_sha256":implementation["request_sha256"],
                                "transport_complete":captured["complete"],"error":captured["error"],"stop_all":captured["stop_all"],
                                "sources":sources+captured["sources"],"coverage":analyze_session(bars,session,request["symbols"])}
                        write(path,result)
                        status["new_sessions"]+=1
                    results.append(result)
                    status.update(updated_at=now(),processed_sessions=len(results),new_requests=new_requests,last_session=session["session"])
                    write(ROOT/"status.json",status)
                    if len(results)%50==0 or not result["transport_complete"]:
                        print(json.dumps({k:status[k] for k in ("processed_sessions","new_requests","last_session")}),flush=True)
                        write(ROOT/"coverage-summary.json",summarize(request,calendar,results))
                    if result.get("stop_all"):
                        status["phase"]="access_denied"
                        break
                else:
                    status["phase"]="complete" if all(x["transport_complete"] for x in results) else "complete_with_failures"
                if status["phase"]=="running":
                    status["phase"]="bounded_complete"
                summary=summarize(request,calendar,results)
                write(ROOT/"coverage-summary.json",summary)
                status.update(updated_at=now(),pending_sessions=summary["pending_sessions"],failed_sessions=len(summary["failed_sessions"]))
                write(ROOT/"status.json",status)
                print(json.dumps(status),flush=True)
            except BaseException as exc:
                status.update(phase="interrupted" if isinstance(exc,KeyboardInterrupt) else "failed",error_type=type(exc).__name__,updated_at=now())
                write(ROOT/"status.json",status)
                raise


if __name__=="__main__":
    main()
