"""Run the frozen study and its economic checks without another manual trigger."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    for script in ("run_study.py", "economic_analysis.py"):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / script)], cwd=ROOT.parents[1], check=False)
        record = {"script": script, "returncode": result.returncode, "at": datetime.now(timezone.utc).isoformat()}
        with (ROOT / "pipeline.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
