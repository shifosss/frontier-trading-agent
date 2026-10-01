import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

workspace = Path.cwd()
command = "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*frontier.cli*' } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json -Depth 3"
workers = json.loads(subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", command], encoding="utf-8"))
if isinstance(workers, dict):
    workers = [workers]
venv = str(workspace / ".venv" / "Scripts" / "python.exe")
owned = [p for p in workers if p["ExecutablePath"] == venv]
assert len([p for p in owned if "paper-watch" in p["CommandLine"]]) == 1
assert len([p for p in owned if " serve " in p["CommandLine"]]) == 1
for role, selector in [("service", " serve "), ("paper-operator", "paper-watch")]:
    saved_pid = int((workspace / "artifacts" / role / "pid.txt").read_text().strip())
    assert any(p["ProcessId"] == saved_pid and selector in p["CommandLine"] for p in owned)
with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=5) as response:
    web = json.load(response)
with urllib.request.urlopen("http://127.0.0.1:8765/api/operator/status", timeout=5) as response:
    paper = json.load(response)
assert web["service"] == "frontier-research" and web["workspace"] == str(workspace)
assert paper["initialized"] and paper["status"] == "ready"
logs = workspace / "artifacts" / "paper-operator"
cycles = [json.loads(line) for line in (logs / "stdout.log").read_text().splitlines() if line.startswith("{")]
recent = [row for row in cycles if row["at"] > "2026-09-18T19:21:58"]
assert recent and all(row["status"] == "ready" for row in recent)
assert not (logs / "stderr.log").read_text().strip()
report = {"at": datetime.now(timezone.utc).isoformat(), "owned_workers": owned, "recent_paper_cycles": recent, "paper_status": paper["status"], "orders": len(paper["orders"]), "launch_commands_exited": True}
(workspace / ".qualification" / "launch-lifetime" / "actual-workers.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
