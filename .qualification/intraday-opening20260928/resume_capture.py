"""Invoke from the root task to reuse the repository's existing hidden worker launcher."""
from datetime import datetime, timezone
import ctypes
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys

from frontier.processes import start_background

ROOT=Path(__file__).resolve().parent


def main():
    record_path=ROOT/"root-resume-launch.json"
    assert not record_path.exists(), "Inspect the prior launch/process/lock before another launch"
    with (ROOT/"capture.lock").open("r+b") as stream:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:
            raise RuntimeError("Existing capture owns capture.lock") from exc
        stream.seek(0)
        msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
    command=[sys.executable,"-u","-B","-X","utf8",str(ROOT/"operational_runner.py")]
    pid=start_background(command,ROOT.parents[1],ROOT/"worker")
    in_job=ctypes.c_int()
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    kernel.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
    inspected=bool(kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(in_job)))
    record={"pid":pid,"launcher_pid":os.getpid(),"launcher_parent_pid":os.getppid(),
            "launched_at":datetime.now(timezone.utc).isoformat(),"command":command,
            "creationflags":subprocess.CREATE_NO_WINDOW,"creationflags_name":"CREATE_NO_WINDOW",
            "close_fds":True,"stdin":"DEVNULL","stdout":"worker/stdout.log","stderr":"worker/stderr.log",
            "launcher_job_membership_known":inspected,"launcher_in_windows_job":bool(in_job.value) if inspected else None,
            "source_request_sha256":hashlib.sha256((ROOT/"request.json").read_bytes()).hexdigest(),
            "operational_amendment_sha256":hashlib.sha256((ROOT/"operational-amendment.json").read_bytes()).hexdigest(),
            "existing_launcher_sha256":hashlib.sha256((ROOT.parents[1]/"src/frontier/processes.py").read_bytes()).hexdigest(),
            "scope":"Resume same frozen DATA-only request and verified cache; not proof of activity after launcher exit"}
    record_path.write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(record),flush=True)


if __name__=="__main__":
    main()
