"""Twelve frozen ETF residual-reversal accounts; no source acquisition or orders."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback
from uuid import uuid4
import zipfile

import numpy as np
from frontier.historical_lab import _save
from adapter import run_account

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def weekly_targets(rows):
    values = np.array([row["return"] for row in rows])
    streak = longest = 0
    for value in values:
        streak = streak+1 if value < 0 else 0
        longest = max(streak, longest)
    return {"weeks": len(rows), "includes_idle_and_losing_weeks": True,
            "thresholds": [{"return_at_least": threshold,
                            "count": int(np.sum(values >= threshold)),
                            "fraction": float(np.mean(values >= threshold)) if len(values) else None}
                           for threshold in (.05, .10, .15)],
            "median_return": float(np.median(values)) if len(values) else None,
            "worst_return": float(np.min(values)) if len(values) else None,
            "longest_losing_week_streak": longest}


def add_reporting(report, capital):
    if report["status"] != "complete":
        report["weekly_targets"] = None
        return
    weeks = report["period_returns"]["weekly"]
    for row in weeks:
        end = date.fromisoformat(row["last_session"])
        week_start = end-timedelta(days=end.weekday())
        row["scope"] = ("initialization" if row["last_session"] < "2017-01-01" else
                        "entry_period_with_liquidation_tail" if week_start <= date(2025, 12, 31) < end else
                        "liquidation_tail" if row["last_session"] > "2025-12-31" else "entry_period")
    report["weekly_targets"] = weekly_targets(weeks)
    report["entry_period_weekly_targets"] = weekly_targets([r for r in weeks if r["scope"].startswith("entry_period")])
    curve, previous, annual = report["equity_curve"], float(capital), []
    for i, row in enumerate(curve):
        if i+1 == len(curve) or curve[i+1]["session"][:4] != row["session"][:4]:
            annual.append({"year": row["session"][:4], "starting_equity": previous,
                           "ending_equity": row["equity"], "return": row["equity"]/previous-1})
            previous = row["equity"]
    report["annual_returns"] = annual


def freeze():
    if (ROOT/"definition.json").exists():
        raise ValueError("Preserve the existing frozen account definition")
    prepared = read(ROOT/"strategy/preparation-completed.json")
    attempt = REPO/prepared["attempt"]
    files = dict(read(attempt/"definition.json")["inputs"])
    for name, expected in prepared["files"].items():
        files[(attempt/name).relative_to(REPO).as_posix()] = expected
    costs = read(ROOT/"costs/cost-qualification.json")
    if costs["status"] != "qualified_quote_informed_sensitivity":
        raise ValueError("Cost source failed the predeclared all-cell coverage gate")
    verified = read(ROOT/"costs/independent-verification/verification.json")
    if (verified["status"] != "passed" or verified["qualification_sha256"] != sha(ROOT/"costs/cost-qualification.json")
        or verified["derived_round_trip_bps"] != costs["round_trip_bps"]):
        raise ValueError("Independent quote arithmetic verification required")
    paths = [ROOT/name for name in ("run_study.py", "adapter.py", "test_adapter.py", "test_reporting.py",
                                    "strategy/preparation-completed.json")]
    paths += sorted(path for path in (ROOT/"costs").rglob("*") if path.suffix in (".json", ".jsonl", ".py", ".zip"))
    paths += sorted((REPO/"src/frontier").glob("*.py"))
    paths += [REPO/"pyproject.toml"]
    files.update({path.relative_to(REPO).as_posix(): sha(path) for path in paths})
    for name, expected in files.items():
        if sha(REPO/name) != expected:
            raise ValueError("Input changed: "+name)
    definition = {"schema": "etf-residual-reversal-12-accounts-v1", "created_at": datetime.now(timezone.utc).isoformat(),
                  "files": files, "prepared": prepared["attempt"],
                  "dependencies": {name: importlib.metadata.version(name) for name in
                                   ("numpy", "pandas", "exchange-calendars")},
                  "round_trip_bps": costs["round_trip_bps"], "capital_usd": [10000, 2000],
                  "arms": ["residual_reversal", "residual_reversal_trend", "matched_count_control"],
                  "brokers": ["wealthsimple_usd", "moomoo_ca_us"], "account_count": 12,
                  "qualification": "Exploratory current-member revised-vintage study, not qualified fills or all-in profit",
                  "separate_omitted_costs": "USD account subscription, funding/conversion, personal income tax and unknown venue charges"}
    _save(ROOT/"definition.json", definition)
    with zipfile.ZipFile(ROOT/"implementation.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [*files, (ROOT/"definition.json").relative_to(REPO).as_posix()]:
            archive.write(REPO/name, name)
    _save(ROOT/"freeze.json", {"definition_sha256": sha(ROOT/"definition.json"),
                              "archive_sha256": sha(ROOT/"implementation.zip"), "files": len(files)})
    print(json.dumps(read(ROOT/"freeze.json")), flush=True)


def verify():
    definition = read(ROOT/"definition.json")
    if sha(ROOT/"definition.json") != read(ROOT/"freeze.json")["definition_sha256"]:
        raise ValueError("Frozen definition changed")
    for name, expected in definition["files"].items():
        if sha(REPO/name) != expected:
            raise ValueError("Frozen input changed: "+name)
    for name, expected in definition["dependencies"].items():
        if importlib.metadata.version(name) != expected:
            raise ValueError("Dependency changed: "+name)
    return definition


def main():
    lock = sqlite3.connect((REPO/"data/historical/worker.lock.sqlite").as_uri()+"?mode=rw", uri=True, timeout=0)
    try:
        lock.execute("BEGIN EXCLUSIVE")
        definition = verify()
        if list((ROOT/"attempts").glob("*/attempt.json")):
            raise ValueError("Prior declared attempt requires review; no automatic rerun")
        attempt = ROOT/"attempts"/uuid4().hex
        attempt.mkdir(parents=True)
        _save(attempt/"attempt.json", {"definition_sha256": sha(ROOT/"definition.json"),
                                      "started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
                                      "parameters": {k: v for k, v in definition.items() if k != "files"}})
        results = []
        try:
            prepared = REPO/definition["prepared"]
            market = read(prepared/"market-inputs.json")
            with np.load(prepared/"market-arrays.npz", allow_pickle=False) as data:
                market.update({key: data[key] for key in data.files})
            with np.load(prepared/"signals.npz", allow_pickle=False) as data:
                signals = {key: data[key] for key in data.files}
            for arm in definition["arms"]:
                for capital in definition["capital_usd"]:
                    for broker in definition["brokers"]:
                        name = f"{arm}-{capital}-{broker}"
                        try:
                            report = run_account(market, signals[arm+"_ranking"], signals[arm+"_counts"],
                                arm=arm, capital=capital, cost_profile=broker, cost_bps=definition["round_trip_bps"],
                                first=market["first"], last=market["last"])
                            add_reporting(report, capital)
                        except Exception as error:
                            report = {"status": "failed", "error": str(error), "traceback": traceback.format_exc()}
                        report.update(arm=arm, capital=capital, cost_profile=broker)
                        path = attempt/"accounts"/(name+".json")
                        _save(path, plain(report))
                        result = {key: report.get(key) for key in ("status", "arm", "capital", "cost_profile", "ending_equity",
                                  "total_return", "max_drawdown", "trade_metrics", "weekly_targets", "entry_period_weekly_targets",
                                  "annual_returns", "drawdown_halt", "error", "missing", "activity")}
                        result.update(artifact=path.relative_to(attempt).as_posix(), sha256=sha(path))
                        results.append(result)
                        status = {"completed": len(results), "planned": 12, "account": name, "status": report["status"]}
                        _save(attempt/"progress.json", status)
                        print(json.dumps(status), flush=True)
            verify()
            summary = {"status": "complete", "accounts": results, "planned_accounts": 12,
                       "complete_accounts": sum(r["status"] == "complete" for r in results),
                       "definition_sha256": sha(ROOT/"definition.json"),
                       "cash_references": [{"initial_capital": x, "ending_equity": x, "return": 0,
                                            "modeled_interest_and_fees": 0} for x in definition["capital_usd"]],
                       "promotion": False}
            _save(attempt/"summary.json", plain(summary))
            _save(ROOT/"completed.json", {"attempt": attempt.relative_to(REPO).as_posix(),
                "definition_sha256": summary["definition_sha256"],
                "files": {p.relative_to(attempt).as_posix(): sha(p) for p in attempt.rglob("*.json")}})
        except Exception as error:
            _save(attempt/"failure.json", {"error": str(error), "traceback": traceback.format_exc()})
            raise
    finally:
        lock.rollback()
        lock.close()


if __name__ == "__main__":
    freeze() if sys.argv[1:] == ["freeze"] else main()
