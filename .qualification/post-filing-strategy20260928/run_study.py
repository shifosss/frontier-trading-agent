"""Four predeclared original-filing accounts over frozen, qualified source inputs."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import traceback
from uuid import uuid4

import numpy as np
from frontier.execution_costs import get_cost_profile
from frontier.historical_lab import _save
from adapter import event_rankings, run_account
from event_reference import build_event_reference

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def read(path):
    return Path(path).read_text(encoding="utf-8")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def verify_definition():
    definition = json.loads(read(ROOT / "definition.json"))
    assert definition["schema"] == "original-filing-four-accounts-v1"
    for name, expected in definition["files"].items():
        path = REPO / name
        actual = sha(path) if path.is_file() else None
        if actual != expected:
            raise ValueError("Frozen input changed: " + name)
    for package, expected in definition["dependencies"].items():
        if importlib.metadata.version(package) != expected:
            raise ValueError("Dependency changed: " + package)
    request = json.loads(read(ROOT / "request.json"))
    assert request["arms"] == ["income_surprise", "filing_control"]
    assert request["cost_profiles"] == ["proportional", "moomoo_ca_us"]
    assert request["planned_accounts"] == 4 and request["capital"] == 2000
    assert request["round_trip_bps"] == 40 and request["holding_sessions"] == 5
    assert request["first_session"] == "2016-12-30" and request["last_session"] == "2026-01-16"
    return request, sha(ROOT / "definition.json")


def status(phase, attempt, **details):
    value = {"phase": phase, "attempt": attempt.name, "pid": os.getpid(),
             "updated_at": datetime.now(timezone.utc).isoformat(), **details}
    _save(ROOT / "status.json", value)
    print(json.dumps(value), flush=True)


def load_inputs(request):
    market = json.loads(read(ROOT / "market-inputs.json"))
    with np.load(ROOT / "market-arrays.npz", allow_pickle=False) as arrays:
        market.update({key: arrays[key] for key in arrays.files})
    market["dates"] = np.array(market["sessions"], dtype="datetime64[D]")
    market["n"] = len(market["sessions"])
    events = json.loads(read(REPO / request["events"]))
    first = market["sessions"].index(request["first_session"])
    last = market["sessions"].index(request["last_session"])
    _, _, lookup = event_rankings(market, events, "filing_control")
    for (row, _), event in lookup.items():
        if row < first or market["sessions"].index(event["exit_session"]) > last:
            raise ValueError("Declared account interval would omit an eligible event")
    return market, events, first, last


def run(attempt, request, definition_sha):
    market, events, first, last = load_inputs(request)
    reference = build_event_reference(market, events)
    _save(attempt / "event-reference.json", plain(reference))
    results = []
    for arm in request["arms"]:
        for profile in request["cost_profiles"]:
            name = arm + "-" + profile
            status("evaluating", attempt, account=name, completed=len(results), total=4)
            try:
                report = run_account(market, events, arm=arm, cost_profile=profile,
                                     first=first, last=last, capital=request["capital"],
                                     cost_bps=request["round_trip_bps"])
            except Exception as error:
                report = {"status": "failed", "error": type(error).__name__ + ": " + str(error),
                          "traceback": traceback.format_exc()}
            report.update(arm=arm, cost_profile=profile, definition_sha256=definition_sha,
                          costs=get_cost_profile(profile, request["round_trip_bps"]).specification)
            path = attempt / "accounts" / (name + ".json")
            _save(path, plain(report))
            metrics = report.get("trade_metrics", {})
            result = {key: report.get(key) for key in ("status", "ending_equity", "total_return", "max_drawdown", "error", "missing")}
            result.update(arm=arm, cost_profile=profile, artifact=path.relative_to(attempt).as_posix(),
                          sha256=sha(path), **{key: metrics.get(key) for key in
                          ("completed_trades", "fees", "net_expectancy_native", "mean_exposure_fraction")})
            _save(attempt / "account-manifests" / (name + ".json"), result)
            results.append(result)
    return {"status": "complete", "definition_sha256": definition_sha, "accounts": results,
            "planned_accounts": 4, "complete_accounts": sum(row["status"] == "complete" for row in results),
            "invalid_or_failed_accounts": sum(row["status"] != "complete" for row in results),
            "cash_reference_return": 0, "promotion": False,
            "event_reference": "event-reference.json", "first_session": request["first_session"],
            "last_session": request["last_session"], "initialization_year": 2016, "liquidation_tail_year": 2026}


def main():
    lock = sqlite3.connect((REPO / "data/historical/worker.lock.sqlite").as_uri() + "?mode=rw", uri=True, timeout=0)
    try:
        lock.execute("BEGIN EXCLUSIVE")
        request, definition_sha = verify_definition()
        pointer = ROOT / "completed.json"
        if pointer.exists():
            completed = json.loads(read(pointer))
            assert completed["definition_sha256"] == definition_sha
            for name, expected in completed["files"].items():
                assert sha(ROOT / name) == expected, "Completed artifact changed: " + name
            print(json.dumps({"status": "reused_completed", "summary": completed["summary"]}), flush=True)
            return
        # Never silently repeat a failed/interrupted declared experiment.
        if list((ROOT / "attempts").glob("*/attempt.json")):
            raise ValueError("A previous attempt requires explicit reconciliation before continuation")
        attempt = ROOT / "attempts" / uuid4().hex
        started = {"started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
                   "definition_sha256": definition_sha, "request": request}
        _save(attempt / "attempt.json", dict(started, status="running"))
        try:
            summary = run(attempt, request, definition_sha)
            assert verify_definition()[1] == definition_sha
            _save(attempt / "summary.json", summary)
            _save(attempt / "attempt.json", dict(started, status="complete", completed_at=datetime.now(timezone.utc).isoformat()))
            _save(pointer, {"definition_sha256": definition_sha,
                           "summary": (attempt / "summary.json").relative_to(ROOT).as_posix(),
                           "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(attempt.rglob("*.json"))}})
            status("complete", attempt, complete_accounts=summary["complete_accounts"],
                   invalid_or_failed_accounts=summary["invalid_or_failed_accounts"])
        except BaseException as error:
            _save(attempt / "attempt.json", dict(started, status="failed", error=type(error).__name__ + ": " + str(error),
                                                traceback=traceback.format_exc()))
            status("failed", attempt, error=type(error).__name__ + ": " + str(error))
            raise
    finally:
        lock.rollback()
        lock.close()


if __name__ == "__main__":
    main()
