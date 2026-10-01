"""Known Windows progress race: bounded retries and permanent failure propagation."""
import importlib.util
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("operational_runner",ROOT/"operational_runner.py")
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("permanent",[False,True])
@pytest.mark.parametrize("filename",["status.json","page-001-attempt-001.json"])
def test_writer_error_retry_and_propagation(tmp_path,monkeypatch,permanent,filename):
    monkeypatch.setattr(runner,"ROOT",tmp_path)
    monkeypatch.setattr(runner.historical_lab.time,"sleep",lambda _:None)
    original=Path.replace
    calls=[]
    def replace(path,target):
        calls.append(path)
        if permanent or len(calls)<3:
            raise PermissionError("fixture sharing violation")
        return original(path,target)
    monkeypatch.setattr(Path,"replace",replace)
    if permanent:
        with pytest.raises(PermissionError):
            runner.amended_write(tmp_path/filename,{"phase":"running"})
        assert len(calls)==6 and not (tmp_path/filename).exists()
    else:
        runner.amended_write(tmp_path/filename,{"phase":"running"})
        assert len(calls)==3 and (tmp_path/filename).read_text()=='{"phase":"running"}'
    if filename=="status.json":
        assert len((tmp_path/"progress.jsonl").read_text().splitlines())==1
    else:
        assert not (tmp_path/"progress.jsonl").exists()
