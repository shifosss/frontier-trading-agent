"""Declared operational continuation: change progress persistence only."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from uuid import uuid4

from frontier.historical_lab import _save

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def load_runner():
    spec = importlib.util.spec_from_file_location("frozen_conditional_runner", ROOT / "run_study.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_status_writer(runner):
    def status(phase, **details):
        item = dict(phase=phase, pid=os.getpid(), updated_at=datetime.now(timezone.utc).isoformat(), **details)
        _save(ROOT / "status.json", item)
        print(json.dumps(item), flush=True)

    runner.status = status


def main():
    runner = load_runner()
    amendment_path = ROOT / "operational-amendment.json"
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    assert runner.sha(ROOT / "definition.json") == amendment["base_definition_sha256"]
    for relative, expected in amendment["files"].items():
        assert runner.sha(REPO / relative) == expected, relative
    install_status_writer(runner)
    before = set((ROOT / "attempts").glob("*.json"))
    identity = runner.sha(amendment_path)
    record_path = ROOT / "continuations" / (uuid4().hex + ".json")
    record = {"base_definition_sha256": amendment["base_definition_sha256"], "operational_amendment_sha256": identity,
              "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}
    _save(record_path, record)
    try:
        runner.main()
        record["study_status"] = "complete"
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "economic_analysis.py")], cwd=REPO, check=False)
        record["analysis_returncode"] = result.returncode
        record["status"] = "complete" if result.returncode == 0 else "analysis_failed"
        return result.returncode
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        runner.status("failed", error=record["error"], traceback=record["traceback"])
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        record["study_attempts"] = [p.relative_to(ROOT).as_posix() for p in sorted(set((ROOT / "attempts").glob("*.json")) - before)]
        _save(record_path, record)
        with (ROOT / "pipeline.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"script": Path(__file__).name, "record": record_path.relative_to(ROOT).as_posix(),
                                     "status": record["status"], "operational_amendment_sha256": identity}) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
