import json
import subprocess
import sys
import time
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "start_background.py"


def test_worker_survives_launcher_and_keeps_writing_to_existing_logs(tmp_path):
    workspace = tmp_path / "Owner's workspace with spaces"
    workspace.mkdir()
    logs = workspace / "logs"
    logs.mkdir()
    (logs / "stdout.log").write_text("previous run\n", encoding="utf-8")
    release = workspace / "release"
    done = workspace / "done"
    worker = workspace / "worker.py"
    worker.write_text(
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "print(json.dumps({'cwd': os.getcwd(), 'arg': sys.argv[1]}), flush=True)\n"
        "deadline = time.monotonic() + 15\n"
        "while not Path('release').exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.05)\n"
        "print('after launcher exit', flush=True)\n"
        "print('worker error stream', file=sys.stderr, flush=True)\n"
        "Path('done').write_text('finished')\n",
        encoding="utf-8",
    )
    try:
        parent = subprocess.run(
            [
                sys.executable, "-X", "utf8", str(LAUNCHER),
                "--working-directory", str(workspace), "--log-directory", str(logs),
                "--", sys.executable, "-u", str(worker), "Owner's argument with spaces",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=5,
            check=True,
        )
        assert int(parent.stdout.strip()) > 0
        assert not done.exists(), "launcher waited for its long-running child"
    finally:
        release.touch()
    deadline = time.monotonic() + 5
    while not done.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert done.exists(), "worker did not survive launcher exit"
    lines = (logs / "stdout.log").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "previous run"
    assert json.loads(lines[1]) == {
        "cwd": str(workspace), "arg": "Owner's argument with spaces"
    }
    assert lines[2] == "after launcher exit"
    assert (logs / "stderr.log").read_text(encoding="utf-8") == "worker error stream\n"


def test_failed_launch_does_not_report_a_worker_pid(tmp_path):
    parent = subprocess.run(
        [
            sys.executable, "-X", "utf8", str(LAUNCHER),
            "--working-directory", str(tmp_path), "--log-directory", str(tmp_path / "logs"),
            "--", str(tmp_path / "missing-worker.exe"),
        ],
        capture_output=True,
        encoding="utf-8",
        timeout=5,
    )
    assert parent.returncode != 0
    assert not parent.stdout.strip()
    assert "FileNotFoundError" in parent.stderr
