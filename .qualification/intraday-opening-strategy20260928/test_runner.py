"""Offline source gates and four-account retention; never reads strategy outcomes."""
import importlib.util
from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("opening_study_runner", ROOT / "run_study.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def isolated_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)


def fixture(tmp_path):
    attempt = tmp_path / "attempts" / "first"
    attempt.mkdir(parents=True)
    manifest = {"root": str(tmp_path / "capture"), "identities": {"request_sha256": "frozen"},
                "sessions": [{"session": "2024-01-02"}, {"session": "2024-01-03"}],
                "symbols": [*runner.strategy.STOCKS, "SPY"]}
    request = {"arms": ["continuation", "reversal"], "cost_profiles": ["proportional", "moomoo_ca_us"],
               "initial_cash": 2000, "first_signal": "2024-01-02", "last_session": "2024-01-03"}
    return attempt, manifest, request


def audit(session, complete=True, value=1):
    return {"session": session["session"], "transport_complete": complete, "source_errors": [], "value": value}


def test_every_source_is_audited_and_incomplete_source_never_reaches_simulation(tmp_path):
    attempt, manifest, request = fixture(tmp_path)
    visits = []
    def read_source(root, session, original):
        visits.append(session["session"])
        return {}, audit(session, complete=session["session"] != "2024-01-02")
    with patch.object(runner.adapter, "read_session", read_source), patch.object(runner.strategy, "simulate") as simulate:
        result = runner.run_qualified(request, "definition", attempt, manifest)
    assert not simulate.called
    assert visits == [s["session"] for s in manifest["sessions"]]
    assert result["status"] == "source_not_ready"
    assert len(list((attempt / "source-audits").glob("*.json"))) == 2
    inputs = runner.read(attempt / "source-inputs.json")
    assert not inputs["qualified"] and len(inputs["audit_sha256"]) == 2


def test_source_identity_failure_is_saved_without_cherry_picking_other_dates(tmp_path):
    attempt, manifest, request = fixture(tmp_path)
    def broken(root, session, original):
        raise ValueError("raw hash changed")
    with patch.object(runner.adapter, "read_session", broken), patch.object(runner.strategy, "simulate") as simulate:
        result = runner.run_qualified(request, "definition", attempt, manifest)
    assert result["status"] == "source_not_ready" and not simulate.called
    audits = [runner.read(p) for p in (attempt / "source-audits").glob("*.json")]
    assert len(audits) == 2 and all("raw hash changed" in str(row) for row in audits)


def test_changed_audit_is_rejected_before_yielding_bars(tmp_path):
    attempt, manifest, _ = fixture(tmp_path)
    with patch.object(runner.adapter, "read_session", lambda r, s, m: ({"AAPL": {}}, audit(s))):
        inputs = runner.qualify_source(manifest, attempt)
    with patch.object(runner.adapter, "read_session", lambda r, s, m: ({"AAPL": {}}, audit(s, value=2))):
        with pytest.raises(ValueError, match="Source audit changed"):
            next(runner.verified_daily_bars(manifest, inputs))


def test_all_four_complete_invalid_exception_accounts_stay_in_denominator(tmp_path):
    attempt, manifest, request = fixture(tmp_path)
    calls = []
    def fake_simulate(sessions, daily_bars, **kwargs):
        calls.append((kwargs["arm"], kwargs["cost_profile"], len(list(daily_bars))))
        if calls[-1][:2] == ("continuation", "proportional"):
            return {"status": "invalid", "failure": {"reason": "missing_required_exit"}, "trades": []}
        if calls[-1][:2] == ("continuation", "moomoo_ca_us"):
            raise ArithmeticError("synthetic account failure")
        return {"status": "complete", "ending_equity": 2000, "trades": []}
    with patch.object(runner.adapter, "read_session", lambda r, s, m: ({}, audit(s))), \
         patch.object(runner.strategy, "simulate", fake_simulate), \
         patch.object(runner, "historical_lock", return_value=nullcontext()):
        result = runner.run_qualified(request, "definition", attempt, manifest)
    assert len(calls) == 4 and all(row[2] == 2 for row in calls)
    assert result["planned_accounts"] == 4
    assert [r["status"] for r in result["accounts"]] == ["invalid", "failed", "complete", "complete"]
    assert len(list((attempt / "accounts").glob("*.json"))) == 4
    assert len(list((attempt / "account-manifests").glob("*.json"))) == 4


def test_completed_identity_prevents_rerun_and_rejects_changed_artifact(tmp_path):
    result = tmp_path / "attempts/a/summary.json"
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({"status": "complete", "accounts": []}), encoding="utf-8")
    completed = {"definition_sha256": "same", "summary": "attempts/a/summary.json",
                 "files": {"attempts/a/summary.json": runner.sha(result)}}
    (tmp_path / "completed.json").write_text(json.dumps(completed), encoding="utf-8")
    with patch.object(runner, "ROOT", tmp_path):
        assert runner.load_completed("same")["status"] == "complete"
        with pytest.raises(ValueError, match="definition"):
            runner.load_completed("different")
        result.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="artifact"):
            runner.load_completed("same")


def test_partial_resume_reuses_invalid_and_successful_accounts_under_exact_source_identity(tmp_path):
    attempt, manifest, request = fixture(tmp_path)
    def fake_simulate(sessions, daily_bars, **kwargs):
        list(daily_bars)
        return {"status": "invalid" if kwargs["arm"] == "continuation" else "complete", "trades": []}
    with patch.object(runner.adapter, "read_session", lambda r, s, m: ({}, audit(s))), \
         patch.object(runner.strategy, "simulate", fake_simulate), \
         patch.object(runner, "historical_lock", return_value=nullcontext()):
        first = runner.run_qualified(request, "definition", attempt, manifest)
    retry = tmp_path / "attempts" / "retry"
    retry.mkdir()
    with patch.object(runner.adapter, "read_session", lambda r, s, m: ({}, audit(s))), \
         patch.object(runner.strategy, "simulate") as simulate, \
         patch.object(runner, "historical_lock", return_value=nullcontext()):
        again = runner.run_qualified(request, "definition", retry, manifest)
    assert not simulate.called
    assert [r["status"] for r in again["accounts"]] == [r["status"] for r in first["accounts"]]
    assert all(r["reused_from"] for r in again["accounts"])
    with pytest.raises(ValueError, match="source inputs"):
        runner.prior_account("continuation-proportional", "definition", "changed", retry)


def test_byte_lock_blocks_duplicate_worker_and_releases_after_exit(tmp_path):
    path = tmp_path / "worker.lock"
    with runner.byte_lock(path):
        with pytest.raises(BlockingIOError):
            with runner.byte_lock(path):
                pytest.fail("Duplicate worker acquired lock")
    with runner.byte_lock(path):
        pass


def test_waiting_for_capture_uses_bounded_60_second_polls_without_reading_outcomes(tmp_path):
    with ExitStack() as stack, patch.object(runner, "byte_lock", side_effect=BlockingIOError), \
         patch.object(runner.time, "monotonic", side_effect=[0, 0, 21600]), \
         patch.object(runner.time, "sleep") as sleep, patch.object(runner.adapter, "read_session") as source:
        reason = runner.await_source(stack, True, tmp_path)
    assert "not ready" in reason and not source.called
    sleep.assert_called_once_with(60)
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "status.json").write_text('{"phase":"complete_with_failures"}', encoding="utf-8")
    with ExitStack() as stack, patch.object(runner, "CAPTURE", capture), \
         patch.object(runner, "byte_lock", return_value=nullcontext()), \
         patch.object(runner.adapter, "read_session") as source:
        reason = runner.await_source(stack, True, tmp_path)
    assert "complete_with_failures" in reason and not source.called
