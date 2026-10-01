"""Operational-only Windows progress writer amendment; frozen capture stays unchanged."""
import hashlib
import importlib.util
import json
from pathlib import Path

from frontier import historical_lab

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("frozen_intraday_capture",ROOT/"capture.py")
capture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def amended_write(path,value):
    if path.parent==ROOT and path.name=="status.json":
        with (ROOT/"progress.jsonl").open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(value,allow_nan=False)+"\n")
    historical_lab._save(path,value)


def main():
    amendment=json.loads((ROOT/"operational-amendment.json").read_text(encoding="utf-8"))
    for label,path in [("wrapper",Path(__file__)),("existing_helper",Path(historical_lab.__file__))]:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==amendment["sha256"][label]
    capture.write=amended_write
    capture.main()


if __name__=="__main__":
    main()
