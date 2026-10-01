"""Verify the operational amendment without changing or refitting a strategy."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("persistence_continuation", Path(__file__).with_name("resume_with_persistence.py"))
continuation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(continuation)


def test_only_status_function_changes_and_windows_collision_retries(tmp_path, monkeypatch, capsys):
    runner = continuation.load_runner()
    before = {name: getattr(runner, name) for name in ("save", "run_block", "forecast_candidates", "evaluate_account", "fit_conditional_block", "_simulate_daily", "validate_definition")}
    monkeypatch.setattr(continuation, "ROOT", tmp_path)
    replace = Path.replace
    denied = []

    def transient(self, target):
        if Path(target).name == "status.json" and not denied:
            denied.append(str(self))
            raise PermissionError("simulated Windows reader/scanner collision")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", transient)
    continuation.install_status_writer(runner)
    runner.status("predicting_block", block=5, completed=32768, total=100000)
    actual = json.loads((tmp_path / "status.json").read_text())
    assert actual == json.loads(capsys.readouterr().out)
    assert actual["phase"] == "predicting_block" and actual["block"] == 5
    assert len(denied) == 1
    assert all(getattr(runner, name) is value for name, value in before.items())


@pytest.mark.parametrize("error,expected_calls", [(PermissionError("persistent denial"), 6), (OSError("disk failure"), 1)])
def test_unresolved_persistence_failures_propagate(tmp_path, monkeypatch, error, expected_calls):
    runner = continuation.load_runner()
    monkeypatch.setattr(continuation, "ROOT", tmp_path)
    calls = []

    def denied(self, target):
        calls.append(str(target))
        raise error

    monkeypatch.setattr(Path, "replace", denied)
    continuation.install_status_writer(runner)
    with pytest.raises(type(error), match=str(error)):
        runner.status("predicting_block", block=5)
    assert len(calls) == expected_calls
