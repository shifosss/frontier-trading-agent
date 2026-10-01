import ctypes, json, os, time
from ctypes import wintypes as w
from datetime import datetime, timezone
from pathlib import Path
k=ctypes.WinDLL("kernel32",use_last_error=True)
k.GetCurrentProcess.restype=w.HANDLE
k.IsProcessInJob.argtypes=[w.HANDLE,w.HANDLE,ctypes.POINTER(w.BOOL)]
x=w.BOOL()
k.IsProcessInJob(k.GetCurrentProcess(),None,ctypes.byref(x))
log=Path(__file__).with_name("events-"+str(os.getpid())+".jsonl")
for i in range(12):
    value={"pid":os.getpid(),"parent":os.getppid(),"in_job":bool(x.value),"step":i,"at":datetime.now(timezone.utc).isoformat()}
    with log.open("a",encoding="utf-8") as f: f.write(json.dumps(value)+"\n")
    print(json.dumps(value),flush=True)
    time.sleep(2)
