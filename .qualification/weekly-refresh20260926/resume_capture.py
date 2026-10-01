"""Resume the September 26 bounded capture without replacing its frozen request."""
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from frontier.historical_data import capture_histories, normalize_history, read_history
from frontier.historical_lab import _save
from frontier.research_lab import completed_sessions
from frontier.research_universe import load_snapshot

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
WORKSPACE = ROOT / "capture-workspace"
CACHE = WORKSPACE / "data/historical"
CAPTURE = CACHE / "capture-workspace"
RUN_ID = "6af796bf858547b2839e09edac1d1fdf"
RUN = WORKSPACE / "artifacts/historical-lab/runs" / RUN_ID


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


def main():
    request = read(ROOT / "request.json")
    definition = read(RUN / "capture-definition.json")
    assert definition["run_id"] == RUN_ID and definition["capture_only"]
    assert definition["requested_start"] == request["requested_start"]
    expected = request["expected_last_completed_session"]
    assert set(completed_sessions(definition["frozen_at"]).values()) == {expected}
    for name, digest in request["code_sha256"].items():
        assert sha(REPO / "src/frontier" / name) == digest, name
    for name, digest in request["main_state_before"].items():
        assert sha(REPO / name) == digest, name
    manifest = load_snapshot(WORKSPACE)
    assert manifest["snapshot_id"] == definition["universe_snapshot"]
    assert hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest() == definition["universe_sha256"]
    for source in manifest["sources"]:
        assert sha(WORKSPACE / source["path"]) == source["sha256"]
    universe = definition["instruments"]
    specs = {spec["symbol"]: spec for spec in universe}
    assert len(specs) == len(universe)
    attempt_root = ROOT / "resume-attempts" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    attempt_root.mkdir(parents=True)
    locks = []
    original_get = httpx.get
    response_lock = threading.Lock()
    response_log = ROOT / "http-responses.jsonl"
    response_root = ROOT / "http-responses"
    state = read(RUN / "status.json")
    attempt = {"started_at": now(), "run_id": RUN_ID, "script_sha256": sha(Path(__file__)),
        "frozen_at": definition["frozen_at"], "requested_start": request["requested_start"],
        "expected_last_completed_session": expected, "reason": "Resume owner-paused capture from preserved responses and completed records.",
        "retry_policy": "Recover retained in-flight responses locally; request only never-completed instruments; preserve prior failures without retry.",
        "preserved_main_state": request["main_state_before"], "no_evaluation": True}

    def progress(**values):
        state.update(values, updated_at=now())
        _save(RUN / "status.json", state)
        _save(WORKSPACE / "artifacts/historical-lab/status.json", state)
        print(json.dumps({k: state.get(k) for k in ("run_id", "status", "phase", "pid", "attempted", "usable", "failed", "updated_at")}), flush=True)

    def retain_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        digest = hashlib.sha256(response.content).hexdigest()
        body = response_root / (digest + ".body")
        metadata = {"url": str(response.url), "status_code": response.status_code,
            "sha256": digest, "path": str(body.relative_to(ROOT)), "observed_at": now()}
        with response_lock:
            if not body.exists():
                body.write_bytes(response.content)
            with response_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(metadata, separators=(",", ":")) + "\n")
        return response

    try:
        for path in (REPO / "data/historical/worker.lock.sqlite", CACHE / "worker.lock.sqlite"):
            connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0)
            locks.append(connection)
            connection.execute("BEGIN EXCLUSIVE")
        for label, path in (("status", RUN / "status.json"), ("index", CACHE / "history-index.json"), ("failures", RUN / "capture-failures.json")):
            copied = attempt_root / (label + "-before.json")
            shutil.copyfile(path, copied)
            assert sha(path) == sha(copied)
        _save(attempt_root / "request.json", attempt)
        index = read(CACHE / "history-index.json")
        before_index = dict(index)
        failures = read(RUN / "capture-failures.json")
        prior_failures = list(failures)
        done = set(index) | {item["symbol"] for item in failures}
        assert set(index).isdisjoint({item["symbol"] for item in failures})
        assert done <= set(specs)
        recovered = []
        for line in response_log.read_text("utf-8").splitlines():
            response = json.loads(line)
            assert sha(ROOT / response["path"]) == response["sha256"]
            symbol = unquote(urlparse(response["url"]).path.rsplit("/", 1)[1])
            if symbol in done or symbol not in specs:
                continue
            body = (ROOT / response["path"]).read_bytes()
            try:
                if response["status_code"] != 200:
                    raise ValueError(f"Recovered HTTP response status {response['status_code']}")
                frame = normalize_history(json.loads(body), specs[symbol], response["observed_at"], as_of=definition["frozen_at"])
                relative = f"data/scanner/raw/{symbol}.{response['sha256']}.json"
                path = CAPTURE / relative
                if path.exists():
                    assert sha(path) == response["sha256"]
                else:
                    path.write_bytes(body)
                period2 = int(parse_qs(urlparse(response["url"]).query)["period2"][0])
                index[symbol] = {"symbol": symbol, "path": relative, "sha256": response["sha256"],
                    "captured_at": response["observed_at"], "url": response["url"], "rows": len(frame),
                    "first_session": frame.session.iloc[0], "last_session": frame.session.iloc[-1],
                    "requested_start": request["requested_start"], "requested_as_of": definition["frozen_at"],
                    "split_events_requested_through": datetime.fromtimestamp(period2, timezone.utc).isoformat(),
                    "split_reconstruction": frame.attrs["split_reconstruction"],
                    "recovery": "Record reconstructed from retained in-flight response; observation time and integer request bound retained."}
                recovered.append({"symbol": symbol, "status": "captured", "sha256": response["sha256"]})
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                failures.append({"symbol": symbol, "error": str(exc), "recovered_response_sha256": response["sha256"]})
                recovered.append({"symbol": symbol, "status": "failed", "error": str(exc), "sha256": response["sha256"]})
            done.add(symbol)
        _save(attempt_root / "recovered-responses.json", recovered)
        _save(CACHE / "history-index.json", index)
        _save(RUN / "capture-failures.json", failures)
        pending = [spec for spec in universe if spec["symbol"] not in done]
        attempt.update(preserved_histories=len(before_index), preserved_failures=len(prior_failures), recovered_responses=len(recovered), new_requests=len(pending))
        _save(attempt_root / "request.json", attempt)
        progress(status="running", phase="capture", pid=os.getpid(), resumed_at=now(), attempted=len(done), usable=len(index), failed=len(failures), cached=len(before_index))
        httpx.get = retain_get
        for offset in range(0, len(pending), 50):
            results = capture_histories(CAPTURE, pending[offset:offset + 50], start=request["requested_start"], as_of=definition["frozen_at"])
            for record in results:
                assert record["symbol"] not in done
                done.add(record["symbol"])
                if "error" in record:
                    failures.append(record)
                else:
                    index[record["symbol"]] = record
            _save(CACHE / "history-index.json", index)
            _save(RUN / "capture-failures.json", failures)
            progress(attempted=len(done), usable=len(index), failed=len(failures))
            if sum("429" in item.get("error", "") for item in results) >= max(2, len(results) // 2):
                raise RuntimeError("Public provider rate limited capture; completed data and failures preserved.")
        assert done == set(specs)
        assert {symbol: index[symbol] for symbol in before_index} == before_index
        assert failures[:len(prior_failures)] == prior_failures
        records = [{**index[spec["symbol"]], "spec": spec} for spec in universe if spec["symbol"] in index]
        _save(RUN / "capture-index.json", records)
        progress(phase="verification")
        rows = 0
        latest = Counter()
        by_currency = Counter()
        stale = []
        for record in records:
            frame = read_history(CAPTURE, record)
            assert record["requested_start"] == request["requested_start"]
            assert record["requested_as_of"] == definition["frozen_at"]
            assert frame.session.min() >= request["requested_start"] and frame.session.max() <= expected
            assert len(frame) == record["rows"] and frame.session.max() == record["last_session"]
            rows += len(frame)
            latest[record["last_session"]] += 1
            by_currency[f"{record['spec']['currency']}:{record['last_session']}"] += 1
            if record["last_session"] < expected:
                stale.append({"symbol": record["symbol"], "last_session": record["last_session"]})
        responses = [json.loads(line) for line in response_log.read_text("utf-8").splitlines()]
        for response in responses:
            assert sha(ROOT / response["path"]) == response["sha256"]
        after = {name: sha(REPO / name) for name in request["main_state_before"]}
        assert after == request["main_state_before"], "Main protected state changed"
        summary = {"run_id": RUN_ID, "status": "completed", "completed_at": now(),
            "requested_start": request["requested_start"], "last_completed_session": expected,
            "snapshot_id": manifest["snapshot_id"], "listing_eligible": manifest["eligible_count"],
            "listing_sources": len(manifest["sources"]), "listing_counts": manifest["counts"],
            "captured_histories": len(records), "failed_histories": len(failures), "normalized_rows": rows,
            "last_session_counts": dict(latest), "last_session_by_currency": dict(by_currency), "stale_histories": stale,
            "http_responses_preserved": len(responses), "raw_hashes_verified": True, "listing_hashes_verified": True,
            "main_state_unchanged": True, "main_state_after": after, "completed_records_unchanged": True,
            "recovered_responses": recovered, "capture_index_sha256": sha(RUN / "capture-index.json"),
            "limitations": request["limitations"] + ["Interrupted acquisition resumed September 28 with original September 25 session cutoff; source response vintages differ and are retained per instrument."]}
        _save(ROOT / "verification.json", summary)
        _save(attempt_root / "completed.json", {"completed_at": now(), "verification_sha256": sha(ROOT / "verification.json")})
        progress(status="completed", phase="captured", message="Bounded recent histories saved and verified; evaluation not started.")
        print(json.dumps({key: summary[key] for key in ("run_id", "status", "captured_histories", "failed_histories", "normalized_rows", "http_responses_preserved", "main_state_unchanged")}), flush=True)
    except Exception as exc:
        _save(attempt_root / "failure.json", {"failed_at": now(), "error": str(exc), "type": type(exc).__name__, "traceback": traceback.format_exc()})
        raise
    finally:
        httpx.get = original_get
        for connection in reversed(locks):
            connection.close()


if __name__ == "__main__":
    main()
