"""Frozen offline four-account runner; source qualification precedes outcomes."""
import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import time
import traceback
from uuid import uuid4

from frontier.historical_lab import _save
import source_adapter as adapter
import strategy

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
CAPTURE = ROOT.parent / "intraday-opening20260928"
SOURCE_REQUEST_SHA = "092e82a1bfcb7e5fc0990e72c4bed590d295a2f2e619c4d2c0e8aaef03c43447"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def progress(phase, attempt, **details):
    value = {"phase": phase, "attempt": attempt.name, "pid": os.getpid(),
             "updated_at": datetime.now(timezone.utc).isoformat(), **details}
    _save(ROOT / "status.json", value)
    print(json.dumps(value), flush=True)


def validate_definition():
    request, definition = read(ROOT / "request.json"), read(ROOT / "definition.json")
    assert definition["schema"] == "intraday-opening-definition-v1"
    assert definition["request_sha256"] == sha(ROOT / "request.json")
    assert definition["source_request_sha256"] == SOURCE_REQUEST_SHA
    for path, expected in definition["files"].items():
        assert sha(REPO / path) == expected, f"Frozen implementation changed: {path}"
    for package, version in definition["dependencies"].items():
        assert importlib.metadata.version(package) == version, f"Dependency changed: {package}"
    assert request["arms"] == ["continuation", "reversal"]
    assert request["cost_profiles"] == ["proportional", "moomoo_ca_us"]
    assert request["planned_accounts"] == 4 and request["initial_cash"] == 2000 and request["round_trip_bps"] == 40
    assert request["stocks"] == list(strategy.STOCKS) and request["reference"] == "SPY"
    assert request["first_signal"] == "2017-01-03" and request["last_session"] == "2025-12-31"
    return request, sha(ROOT / "definition.json")


@contextmanager
def byte_lock(path):
    import msvcrt
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"1"); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise BlockingIOError(f"Worker owns {path.name}") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def historical_lock():
    connection = sqlite3.connect((REPO / "data/historical/worker.lock.sqlite").as_uri()+"?mode=rw", uri=True, timeout=0)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        yield
    finally:
        connection.rollback()
        connection.close()


def load_completed(definition_sha):
    path = ROOT / "completed.json"
    if not path.exists():
        return None
    completed = read(path)
    if completed["definition_sha256"] != definition_sha:
        raise ValueError("Existing completed study has another definition")
    for relative, expected in completed["files"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError(f"Completed artifact changed: {relative}")
    return read(ROOT / completed["summary"])


def qualify_source(manifest, attempt):
    identities, failures = {}, []
    for index, session in enumerate(manifest["sessions"]):
        try:
            _, audit = adapter.read_session(manifest["root"], session, manifest)
        except Exception as error:
            audit = {"session": session["session"], "transport_complete": False,
                     "source_errors": [{"error": f"{type(error).__name__}: {error}"}]}
        _save(attempt / "source-audits" / (session["session"]+".json"), audit)
        identities[session["session"]] = digest(audit)
        if not audit["transport_complete"] or audit.get("source_errors"):
            failures.append({"session": session["session"], "source_errors": audit.get("source_errors", [])})
        if (index+1) % 100 == 0:
            progress("qualifying_source", attempt, completed=index+1, total=len(manifest["sessions"]))
    result = {"qualified": not failures, "source_identities": manifest["identities"],
              "sessions": manifest["sessions"], "symbols": manifest["symbols"],
              "audit_sha256": identities, "failures": failures}
    _save(attempt / "source-inputs.json", result)
    return result


def verified_daily_bars(manifest, inputs):
    for session in manifest["sessions"]:
        values, audit = adapter.read_session(manifest["root"], session, manifest)
        if digest(audit) != inputs["audit_sha256"][session["session"]]:
            raise ValueError(f"Source audit changed: {session['session']}")
        yield values


def prior_account(name, definition_sha, source_sha, attempt):
    retained, origin = None, None
    for pointer in sorted((ROOT / "attempts").glob(f"*/account-manifests/{name}.json")):
        if pointer.parent.parent == attempt:
            continue
        saved = read(pointer)
        if saved["definition_sha256"] != definition_sha:
            continue
        path = pointer.parent.parent / saved["artifact"]
        if sha(path) != saved["sha256"]:
            raise ValueError("Retained account artifact changed")
        report = read(path)
        if report["definition_sha256"] != definition_sha or report["source_inputs_sha256"] != source_sha:
            raise ValueError("Retained account source inputs changed under same definition")
        if retained is not None and report != retained:
            raise ValueError("Conflicting retained account outcomes under same definition")
        retained, origin = report, pointer.relative_to(ROOT).as_posix()
    return retained, origin


def run_qualified(request, definition_sha, attempt, manifest):
    inputs = qualify_source(manifest, attempt)
    if not inputs["qualified"]:
        return {"status": "source_not_ready", "reason": "Source qualification contains failed sessions", "failures": inputs["failures"]}
    source_sha = sha(attempt / "source-inputs.json")
    results = []
    with historical_lock():
        for arm in request["arms"]:
            for profile in request["cost_profiles"]:
                name = f"{arm}-{profile}"
                progress("evaluating_accounts", attempt, account=name, completed=len(results), total=4)
                report, reused_from = prior_account(name, definition_sha, source_sha, attempt)
                if report is None:
                    try:
                        report = strategy.simulate(manifest["sessions"], verified_daily_bars(manifest, inputs),
                                                   arm=arm, cost_profile=profile, initial_cash=request["initial_cash"],
                                                   first_signal=request["first_signal"], last_session=request["last_session"])
                    except Exception as error:
                        report = {"status": "failed", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()}
                report.update(arm=arm, cost_profile=profile, definition_sha256=definition_sha,
                              source_inputs_sha256=source_sha)
                path = attempt / "accounts" / (name+".json")
                _save(path, report)
                result = {"arm": arm, "cost_profile": profile, "status": report["status"],
                          "artifact": path.relative_to(attempt).as_posix(), "sha256": sha(path),
                          "ending_equity": report.get("ending_equity"), "total_return": report.get("total_return"),
                          "failure": report.get("failure"), "error": report.get("error"), "reused_from": reused_from}
                for metric in ("completed_trades", "fees_completed_trades", "sampled_mark_max_drawdown", "net_expectancy_usd", "time_weighted_session_exposure"):
                    result[metric] = report.get(metric) if report["status"] == "complete" else None
                _save(attempt / "account-manifests" / (name+".json"), {"definition_sha256": definition_sha, **result})
                results.append(result)
    return {"status": "complete", "definition_sha256": definition_sha, "planned_accounts": 4,
            "accounts": results, "source_inputs_sha256": sha(attempt / "source-inputs.json"),
            "complete_accounts": sum(r["status"] == "complete" for r in results),
            "invalid_or_failed_accounts": sum(r["status"] != "complete" for r in results), "cash_reference_return": 0}


def await_source(stack, wait, attempt):
    deadline = time.monotonic()+6*60*60
    while True:
        try:
            stack.enter_context(byte_lock(CAPTURE / "capture.lock"))
            break
        except BlockingIOError:
            if not wait or time.monotonic() >= deadline:
                return "Capture worker still owns source lock; source is not ready"
            progress("waiting_for_source", attempt, next_check_seconds=60)
            time.sleep(60)
    phase = read(CAPTURE / "status.json").get("phase") if (CAPTURE / "status.json").exists() else "missing"
    return None if phase == "complete" else f"Capture lock released with incomplete source phase: {phase}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-for-source", action="store_true")
    args = parser.parse_args()
    with ExitStack() as locks:
        locks.enter_context(byte_lock(ROOT / "worker.lock"))
        attempt = ROOT / "attempts" / uuid4().hex
        attempt.mkdir(parents=True)
        started = {"started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}
        _save(attempt / "attempt.json", {**started, "status": "started"})
        try:
            request, definition_sha = validate_definition()
            old = load_completed(definition_sha)
            if old is not None:
                _save(attempt / "attempt.json", {**started, "status": "reused_completed", "definition_sha256": definition_sha})
                progress("reused_completed", attempt, definition_sha256=definition_sha)
                return
            reason = await_source(locks, args.wait_for_source, attempt)
            if reason:
                result = {"status": "source_not_ready", "reason": reason}
            else:
                manifest = adapter.load_manifest(CAPTURE, SOURCE_REQUEST_SHA)
                assert len(manifest["sessions"]) == 2514 and manifest["symbols"] == [*strategy.STOCKS, "SPY"]
                assert manifest["sessions"][0]["session"] == "2016-01-04" and manifest["sessions"][-1]["session"] == "2025-12-31"
                result = run_qualified(request, definition_sha, attempt, manifest)
            assert validate_definition()[1] == definition_sha
            _save(attempt / "summary.json", result)
            _save(attempt / "attempt.json", {**started, "status": result["status"], "definition_sha256": definition_sha})
            if result["status"] == "complete":
                _save(ROOT / "completed.json", {"definition_sha256": definition_sha,
                      "summary": (attempt / "summary.json").relative_to(ROOT).as_posix(),
                      "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(attempt.rglob("*.json"))}})
            progress(result["status"], attempt, definition_sha256=definition_sha, reason=result.get("reason"))
        except BaseException as error:
            _save(attempt / "attempt.json", {**started, "status": "failed", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
            progress("failed", attempt, error=f"{type(error).__name__}: {error}")
            raise


if __name__ == "__main__":
    main()
