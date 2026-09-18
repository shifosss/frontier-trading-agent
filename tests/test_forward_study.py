import json
from types import SimpleNamespace

import exchange_calendars as xcals
import pandas as pd
import pytest

from frontier import forward_study
from frontier.strategy_study import MODEL_SIGNATURE, cash_weighted_returns


@pytest.fixture
def prospective(monkeypatch):
    clock = [pd.Timestamp("2024-10-17T15:00:00Z")]
    monkeypatch.setattr(
        forward_study, "datetime", SimpleNamespace(now=lambda tz: clock[0].to_pydatetime())
    )
    calendar = xcals.get_calendar("XNYS", start="2024-01-01", end="2025-03-31")
    sessions = calendar.sessions_in_range("2024-10-16", "2024-12-02")
    records = []
    for symbol, price in (("AAA", 10), ("BBB", 12), ("SPY", 300)):
        for i, session in enumerate(sessions):
            records.append(
                {
                    "symbol": symbol,
                    "session": session.date().isoformat(),
                    "available_at": calendar.session_close(session) + pd.Timedelta(minutes=1),
                    "close": price + i * 0.1,
                    "adjusted_close": price + i * 0.1,
                }
            )
    result = {
        "as_of": "2024-10-17T14:55:00Z",
        "methodology": {"budgets": [500.0], "model_signature": MODEL_SIGNATURE},
        "coverage": {
            "markets": [{"currency": "USD", "latest_completed_session": "2024-10-16"}],
            "instruments": [
                {"symbol": symbol, "currency": "USD"} for symbol in ("AAA", "BBB", "SPY")
            ],
        },
        "latest_candidates": [
            {
                "currency": "USD",
                "strategy": "momentum",
                "symbol": "AAA",
                "session": "2024-10-16",
                "rank": 1,
                "price": 10,
                "quantities_by_budget": {"500": 5},
            }
        ],
    }
    return clock, result, pd.DataFrame(records)


def _outcomes(workspace, result):
    return json.loads((workspace / result["evaluation_path"]).read_text("utf-8"))["cohorts"]


def test_before_entry_no_fake_fills_and_snapshot_deduplicates(tmp_path, prospective):
    clock, result, frame = prospective
    first = forward_study.record_forward_study(tmp_path, result, frame)
    assert first["snapshot_created"]
    assert first["planned_cohorts"] == first["pending_count"] == 12
    outcomes = _outcomes(tmp_path, first)
    assert all(row["status"] == "pending" and row["stage"] == "awaiting_entry" for row in outcomes)
    assert all(not row["observations"] and not row["returns_by_cost"] for row in outcomes)
    assert all(pd.Timestamp(row["entry_close"]) > clock[0] for row in outcomes)
    path = next((tmp_path / "artifacts/forward-studies/snapshots").glob("*.json"))
    before = path.read_bytes()
    clock[0] += pd.Timedelta(minutes=30)
    second = forward_study.record_forward_study(tmp_path, result, frame)
    assert second["snapshot_id"] == first["snapshot_id"]
    assert not second["snapshot_created"]
    assert second["evaluation_path"] != first["evaluation_path"]
    assert path.read_bytes() == before


def test_old_selections_stay_frozen_and_shared_cost_math_matches(tmp_path, prospective):
    clock, result, frame = prospective
    initial = forward_study.record_forward_study(tmp_path, result, frame)
    old = next(
        row
        for row in _outcomes(tmp_path, initial)
        if row["strategy"] == "momentum" and row["horizon"] == 5
    )
    clock[0] = pd.Timestamp(old["exit_available_at"]) + pd.Timedelta(seconds=1)
    result["latest_candidates"][0]["symbol"] = "BBB"
    changed = frame.copy()
    changed.loc[changed.symbol == "BBB", ["close", "adjusted_close"]] *= 10
    later = forward_study.record_forward_study(tmp_path, result, changed)
    assert later["status"] == "skipped_stale_signal"
    actual = next(
        row
        for row in _outcomes(tmp_path, later)
        if row["strategy"] == "momentum" and row["horizon"] == 5
    )
    assert actual["selected"] == ["AAA"]
    assert actual["planned_quantities"] == [5]
    assert actual["status"] == "complete"
    observed = {(row["symbol"], row["session"]): row for row in actual["observations"]}
    entry = observed[("AAA", old["entry_session"])]
    exit_ = observed[("AAA", old["exit_session"])]
    bench_entry = observed[("SPY", old["entry_session"])]
    bench_exit = observed[("SPY", old["exit_session"])]
    expected = cash_weighted_returns(
        500,
        [5],
        [entry["close"]],
        [exit_["adjusted_close"] / entry["adjusted_close"] - 1],
        bench_entry["close"],
        bench_exit["adjusted_close"] / bench_entry["adjusted_close"] - 1,
    )
    assert actual["returns_by_cost"] == expected
    assert expected["20"]["return"] == pytest.approx(
        5 * entry["close"] / 500 * (exit_["adjusted_close"] / entry["adjusted_close"] - 1 - 0.002)
    )


def test_missing_mature_exit_is_incomplete_not_success(tmp_path, prospective):
    clock, result, frame = prospective
    initial = forward_study.record_forward_study(tmp_path, result, frame)
    old = next(
        row
        for row in _outcomes(tmp_path, initial)
        if row["strategy"] == "momentum" and row["horizon"] == 5
    )
    clock[0] = pd.Timestamp(old["exit_available_at"]) + pd.Timedelta(seconds=1)
    missing = frame.loc[~((frame.symbol == "AAA") & (frame.session == old["exit_session"]))]
    later = forward_study.record_forward_study(tmp_path, result, missing)
    actual = next(
        row
        for row in _outcomes(tmp_path, later)
        if row["strategy"] == "momentum" and row["horizon"] == 5
    )
    assert actual["status"] == "incomplete"
    assert actual["missing"] == ["AAA:exit"]
    assert not actual["returns_by_cost"]
    assert later["incomplete_count"] == 1


def test_stale_post_close_result_does_not_create_backdated_plan(tmp_path, prospective):
    clock, result, frame = prospective
    clock[0] = pd.Timestamp("2024-10-17T20:02:00Z")
    actual = forward_study.record_forward_study(tmp_path, result, frame)
    assert actual["status"] == "skipped_stale_signal"
    assert actual["snapshot_id"] is None
    assert actual["planned_cohorts"] == actual["tracked_cohorts"] == 0
    assert actual["stale_markets"] == [
        {"currency": "USD", "source_session": "2024-10-16", "expected_session": "2024-10-17"}
    ]
    assert not list((tmp_path / "artifacts/forward-studies/snapshots").glob("*.json"))


def test_recording_after_close_before_data_availability_uses_next_close(tmp_path, prospective):
    clock, result, frame = prospective
    clock[0] = pd.Timestamp("2024-10-17T20:00:30Z")
    actual = forward_study.record_forward_study(tmp_path, result, frame)
    assert actual["snapshot_created"]
    assert all(row["entry_session"] == "2024-10-18" for row in _outcomes(tmp_path, actual))


def test_saved_old_evaluator_version_is_not_reinterpreted(tmp_path, prospective):
    clock, result, frame = prospective
    initial = forward_study.record_forward_study(tmp_path, result, frame)
    path = next((tmp_path / "artifacts/forward-studies/snapshots").glob("*.json"))
    snapshot = json.loads(path.read_text("utf-8"))
    snapshot["identity"]["forward_code_identity"] = "sha256:old-evaluator-version"
    snapshot["snapshot_id"] = forward_study._digest(snapshot["identity"])
    snapshot.pop("payload_hash")
    snapshot["payload_hash"] = "sha256:" + forward_study._digest(snapshot)
    historical_path = path.with_name(snapshot["snapshot_id"] + ".json")
    historical_path.write_text(json.dumps(snapshot), encoding="utf-8")
    path.unlink()
    clock[0] = max(
        pd.Timestamp(row["exit_available_at"]) for row in _outcomes(tmp_path, initial)
    ) + pd.Timedelta(minutes=1)
    later = forward_study.record_forward_study(tmp_path, result, frame)
    assert later["version_mismatch_count"] == 12
    assert later["complete_count"] == later["incomplete_count"] == 0
    for row in _outcomes(tmp_path, later):
        assert row["status"] == "version_mismatch"
        assert row["code_mismatches"] == ["forward_code_identity"]
        assert not row["returns_by_cost"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("planned_quantities", [999]),
        ("entry_close", "2024-10-16T20:00:00+00:00"),
        ("exit_available_at", "2024-10-18T20:01:00+00:00"),
    ],
)
def test_tampered_frozen_snapshot_is_rejected(tmp_path, prospective, field, value):
    _, result, frame = prospective
    forward_study.record_forward_study(tmp_path, result, frame)
    path = next((tmp_path / "artifacts/forward-studies/snapshots").glob("*.json"))
    snapshot = json.loads(path.read_text("utf-8"))
    snapshot["plans"][0][field] = value
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValueError, match="payload integrity"):
        forward_study.record_forward_study(tmp_path, result, frame)


def test_snapshot_filename_and_dedup_identity_are_verified(tmp_path, prospective):
    _, result, frame = prospective
    forward_study.record_forward_study(tmp_path, result, frame)
    path = next((tmp_path / "artifacts/forward-studies/snapshots").glob("*.json"))
    renamed = path.with_name("wrong-id.json")
    renamed.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="identity check"):
        forward_study._read_snapshot(renamed)
    snapshot = json.loads(path.read_text("utf-8"))
    snapshot["identity"]["model_signature"] = "different-model"
    snapshot.pop("payload_hash")
    snapshot["payload_hash"] = "sha256:" + forward_study._digest(snapshot)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValueError, match="identity check"):
        forward_study._read_snapshot(path)


def test_atomic_publication_never_leaves_partial_final_or_overwrites(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    forward_study._write_new(path, {"complete": True})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        forward_study._write_new(path, {"replacement": True})
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]

    def failed_publish(source, target):
        assert json.loads(source.read_text("utf-8")) == {"complete": True}
        assert not target.exists()
        raise OSError("Simulated failure before atomic publication")

    monkeypatch.setattr(forward_study.os, "link", failed_publish)
    target = tmp_path / "interrupted.json"
    with pytest.raises(OSError, match="atomic publication"):
        forward_study._write_new(target, {"complete": True})
    assert not target.exists()
    assert list(tmp_path.iterdir()) == [path]
