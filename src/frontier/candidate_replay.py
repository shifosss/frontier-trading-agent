"""Durable, isolated rehearsals of trusted saved models; never fit or activate."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np

from frontier.candidate_daily import _digest, load_saved_history
from frontier.daily_policy import forecast_score
from frontier.ensemble_features import HORIZONS, build_features
from frontier.ensemble_models import predict_heads
from frontier.ensemble_study import CONFIG, LEARNED
from frontier.execution_costs import get_cost_profile
from frontier.historical_settlement import build_settlement_indices
from frontier.historical_study import _build_market
from frontier.model_artifact import load_heads
from frontier.short_horizon_study import _simulate_daily
from frontier.strategy_study import BOOKS, _prepare

LIMITATIONS = [
    "Exploratory current-member, adjusted-vintage simulation; not point-in-time accounting.",
    "Trusted local saved model only; no refit, broker fills, paper activation or promotion.",
    "Current tariffs applied to historical sessions are counterfactual scenarios.",
    "Declared friction is not calibrated realized slippage; profitability is not established.",
    "Scores deduct proportional cost; fixed fees affect sizing and ledger, not ranking.",
    "Adjusted-vintage quantities are synthetic shares, not action-complete broker quantities.",
]


def _json(value):
    def convert(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=convert
    )


def _artifact(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Artifact id must be 32 lowercase hexadecimal characters")
    result = (root / identifier).resolve()
    if result.parent != root.resolve():
        raise ValueError("Artifact path escapes its root")
    return result


@contextmanager
def _writer_lock(root):
    """An OS-managed SQLite writer lock survives chunk commits, not process death."""
    lock = sqlite3.connect(root / "writer-lock.sqlite", timeout=0)
    try:
        try:
            lock.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise RuntimeError("Replay already has an active writer") from exc
        yield
    finally:
        lock.rollback()
        lock.close()


def _validate_metadata(metadata):
    signal = metadata["signal_session"]
    for name in ("fit_sample", "calibration_sample"):
        sample = metadata[name]
        if not sample["latest_target_session"] < signal:
            raise ValueError("All model training targets must precede first replay signal")
        if not sample["latest_target_session"] < sample["exclusive_boundary"]:
            raise ValueError("Model target crosses its chronological cutoff")
    for name, expected in metadata["implementation_sha256"].items():
        if Path(name).name != name:
            raise ValueError("Invalid implementation identity path")
        actual = hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Saved model code compatibility failed: {name}")
    for key in ("data", "policy", "account"):
        if _digest(metadata[key]) != metadata[key + "_id"]:
            raise ValueError(f"Saved model {key} identity differs")
    policy, account = metadata["policy"], metadata["account"]
    if policy["horizon"] not in HORIZONS or policy["strategy"] not in LEARNED:
        raise ValueError("Saved strategy or horizon is unsupported")
    if (
        account["currency"] != "USD"
        or account["holdings"]
        or account["reserved_orders"]
        or account["receivables"]
        or account["settled_cash"] != account["nav"]
        or not np.isfinite(account["nav"])
        or account["nav"] <= 0
    ):
        raise ValueError("Replay requires the saved isolated all-cash USD account")


def _prepare_replay(workspace, candidate_id, end_session, costs):
    candidate = _artifact(workspace / "artifacts/daily-candidates", candidate_id)
    bundle, manifest = load_heads(candidate / "model")
    metadata = manifest["metadata"]
    _validate_metadata(metadata)
    source_id, first_signal = metadata["data"]["run_id"], metadata["signal_session"]
    frame, universe, current, evidence = load_saved_history(
        workspace, source_id, end_session, window_start=metadata["data"]["window_start"]
    )
    end_session = evidence["signal_session"]
    original_evidence = {**evidence, "signal_session": first_signal}
    if original_evidence != metadata["data"]:
        raise ValueError("Saved model original source identity differs")
    if end_session < first_signal:
        raise ValueError("Replay end precedes first signal")
    budget = metadata["account"]["nav"]
    _, specs, current, _ = _prepare(frame.iloc[:0], universe, current, (budget,))
    market = _build_market(frame, universe, current, "USD", None, include_activity=True)
    del frame
    features = build_features(
        market,
        stock_mask=np.array([specs[s]["asset_type"] == "stock" for s in market["symbols"]]),
        liquidity_floor=BOOKS["USD"][2],
        turnover=market.pop("turnover"),
        dollar_volume=market.pop("dollar_volume"),
    )
    if features["feature_names"] != metadata["feature_names"]:
        raise ValueError("Replay feature order differs from saved model")
    sessions = market["sessions"]
    start, end = sessions.index(first_signal), sessions.index(end_session)
    market["settlement_index"] = build_settlement_indices(sessions, "USD")
    market["dates"] = np.array(sessions, dtype="datetime64[D]")
    ranking = np.zeros((len(sessions), len(market["symbols"])), dtype=np.int32)
    counts = np.zeros(len(sessions), dtype=np.int32)
    forecasts = {}
    policy = metadata["policy"]
    prediction_name = (
        "calibrated_ensemble"
        if policy["strategy"] == "diversified_ensemble"
        else policy["strategy"]
    )
    for i in range(start, end + 1):
        indices = np.flatnonzero(features["eligible"][i] & features["benchmark_known"][i])
        rows = []
        if len(indices):
            predicted = predict_heads(bundle, features["X"][i, indices])[prediction_name]
            scores = forecast_score(
                predicted, HORIZONS.index(policy["horizon"]), costs.round_trip_bps
            )
            order = np.argsort(-scores, kind="stable")
            selected = indices[order[scores[order] > 0]]
            ranking[i, : len(selected)] = selected
            counts[i] = len(selected)
            rows = [
                dict(
                    symbol=market["symbols"][int(indices[j])],
                    score=float(scores[j]),
                    forecasts=predicted[j].tolist(),
                )
                for j in order
            ]
        forecasts[i] = {"session": sessions[i], "rankings": rows}
    return dict(
        market=market,
        metadata=metadata,
        manifest=manifest,
        start=start,
        end=end,
        ranking=ranking,
        counts=counts,
        known=features["benchmark_known"],
        forecasts=forecasts,
    )


def _connect(root):
    connection = sqlite3.connect(root / "journal.sqlite", timeout=0)
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS identity (
            id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chunks (
            start_index INTEGER PRIMARY KEY, end_index INTEGER UNIQUE NOT NULL,
            prior_state_sha256 TEXT NOT NULL, payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL, error TEXT, request TEXT NOT NULL);
    """)
    return connection


def _read_chunks(connection, start):
    chunks, state, cursor = [], None, start
    for first, last, previous, payload, digest in connection.execute(
        "SELECT start_index,end_index,prior_state_sha256,payload,payload_sha256 "
        "FROM chunks ORDER BY start_index"
    ):
        if first != cursor or last < first or previous != _digest(state):
            raise ValueError("Replay journal duplicate or out-of-order cursor/state")
        if hashlib.sha256(payload.encode()).hexdigest() != digest:
            raise ValueError("Replay chunk integrity differs")
        chunk = json.loads(payload)
        state = chunk["simulation"]["state"]
        cursor = last + 1
        if state["next_session_index"] != cursor:
            raise ValueError("Replay journal state cursor differs")
        chunks.append(chunk)
    return chunks, state, cursor


def _commit_chunk(connection, first, last, previous, chunk):
    if chunk["simulation"]["state"]["next_session_index"] != last + 1:
        raise ValueError("Simulator did not complete requested chunk")
    payload = _json(chunk)
    with connection:
        latest = connection.execute(
            "SELECT end_index,payload FROM chunks ORDER BY start_index DESC LIMIT 1"
        ).fetchone()
        if latest and (
            latest[0] + 1 != first or json.loads(latest[1])["simulation"]["state"] != previous
        ):
            raise ValueError("Duplicate or out-of-order replay chunk")
        if not latest and previous is not None:
            raise ValueError("First replay chunk cannot have prior state")
        connection.execute(
            "INSERT INTO chunks VALUES(?,?,?,?,?)",
            (first, last, _digest(previous), payload, hashlib.sha256(payload.encode()).hexdigest()),
        )


def _report(root, identity, chunks, state, cursor):
    simulations = [chunk["simulation"] for chunk in chunks]
    activity = Counter()
    for simulation in simulations:
        activity.update(simulation["activity"])
    return dict(
        replay_id=root.name,
        artifact_path=str(root),
        status="complete" if cursor > identity["end_index"] else "paused",
        qualification="exploratory_unqualified",
        identity=identity,
        next_session_index=cursor,
        state=state,
        chunk_count=len(chunks),
        curves={
            key: [v for s in simulations for v in s[key]]
            for key in ("equity", "cash", "settled_cash", "unsettled_cash")
        },
        trade_records=[r for s in simulations for r in s["trade_records"]],
        fees=sum(s["fees"] for s in simulations),
        trades=sum(s["trades"] for s in simulations),
        activity=dict(activity),
        limitations=LIMITATIONS,
    )


def replay_candidate(
    workspace,
    candidate_id,
    *,
    end_session=None,
    cost_profile="proportional",
    round_trip_bps=40,
    chunk_sessions=21,
    replay_id=None,
    max_chunks=None,
):
    """Run or resume a named rehearsal, optionally pausing after max_chunks commits.

    Resume requires identical candidate/end/cost arguments; chunk size may change.
    A completed replay is idempotently returned after identity/integrity verification.
    The journal, not the regenerable report.json view, is authoritative.
    """
    workspace = Path(workspace).resolve()
    root = _artifact(workspace / "artifacts/candidate-replays", replay_id or uuid4().hex)
    if replay_id is None:
        root.mkdir(parents=True, exist_ok=False)
    elif not (root / "journal.sqlite").is_file():
        raise ValueError("Named replay does not exist")
    with _writer_lock(root):
        connection = _connect(root)
        attempt_id = uuid4().hex
        try:
            with connection:
                connection.execute(
                    "INSERT INTO attempts VALUES(?,?,NULL,'running',NULL,?)",
                    (
                        attempt_id,
                        datetime.now(timezone.utc).isoformat(),
                        _json(
                            {
                                key: str(value)
                                if isinstance(value, (float, np.floating))
                                and not np.isfinite(value)
                                else value
                                for key, value in dict(
                                    workspace=str(workspace),
                                    candidate_id=candidate_id,
                                    end_session=end_session,
                                    cost_profile=cost_profile,
                                    round_trip_bps=round_trip_bps,
                                    chunk_sessions=chunk_sessions,
                                    max_chunks=max_chunks,
                                    replay_id=replay_id,
                                ).items()
                            }
                        ),
                    ),
                )
            if type(chunk_sessions) is not int or chunk_sessions < 1:
                raise ValueError("chunk_sessions must be a positive integer")
            if max_chunks is not None and (type(max_chunks) is not int or max_chunks < 1):
                raise ValueError("max_chunks must be a positive integer or None")
            costs = get_cost_profile(cost_profile, round_trip_bps=round_trip_bps)
            prepared = _prepare_replay(workspace, candidate_id, end_session, costs)
            metadata, market = prepared["metadata"], prepared["market"]
            identity = dict(
                candidate_id=candidate_id,
                model_id=prepared["manifest"]["payload_sha256"],
                data_id=metadata["data_id"],
                account_id=metadata["account_id"],
                policy_id=metadata["policy_id"],
                start_index=prepared["start"],
                end_index=prepared["end"],
                first_signal=metadata["signal_session"],
                end_session=market["sessions"][prepared["end"]],
                cost_specification=costs.specification,
                runtime={
                    "python": platform.python_version(),
                    **{
                        name: version(name)
                        for name in (
                            "numpy",
                            "pandas",
                            "exchange-calendars",
                            "scipy",
                            "scikit-learn",
                            "joblib",
                            "threadpoolctl",
                        )
                    },
                },
                settlement_indices_sha256=_digest(market["settlement_index"].tolist()),
                code_sha256={
                    name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in (
                        "candidate_replay.py",
                        "short_horizon_study.py",
                        "execution_costs.py",
                        "historical_settlement.py",
                    )
                },
            )
            row = connection.execute("SELECT payload FROM identity WHERE id=1").fetchone()
            if row and json.loads(row[0]) != identity:
                raise ValueError(
                    "Replay identity changed; candidate, end, costs, runtime, "
                    "settlements and code must match"
                )
            if not row:
                with connection:
                    connection.execute("INSERT INTO identity VALUES(1,?)", (_json(identity),))
            chunks, state, cursor = _read_chunks(connection, prepared["start"])
            count = 0
            while cursor <= prepared["end"] and (max_chunks is None or count < max_chunks):
                last = min(prepared["end"], cursor + chunk_sessions - 1)
                policy = metadata["policy"]
                simulation = _simulate_daily(
                    market,
                    policy["strategy"],
                    policy["horizon"],
                    metadata["account"]["nav"],
                    round_trip_bps,
                    cursor,
                    prepared["end"],
                    state=state,
                    audit=True,
                    signal_ranking=prepared["ranking"],
                    signal_counts=prepared["counts"],
                    signal_known=prepared["known"],
                    cost_model=costs,
                    process_through=last,
                    correlation_limit=CONFIG["diversification_correlation_ceiling"]
                    if policy["strategy"] == "diversified_ensemble"
                    else None,
                )
                if simulation["missing"]:
                    raise ValueError(f"Incomplete replay market data: {simulation['missing']}")
                chunk = json.loads(
                    _json(
                        dict(
                            simulation=simulation,
                            forecasts=[prepared["forecasts"][i] for i in range(cursor, last + 1)],
                        )
                    )
                )
                _commit_chunk(connection, cursor, last, state, chunk)
                chunks.append(chunk)
                state, cursor = chunk["simulation"]["state"], last + 1
                count += 1
            report = _report(root, identity, chunks, state, cursor)
            temporary = root / "report.json.tmp"
            temporary.write_text(_json(report) + "\n", encoding="utf-8")
            temporary.replace(root / "report.json")
            with connection:
                connection.execute(
                    "UPDATE attempts SET status=?,finished_at=? WHERE attempt_id=?",
                    (report["status"], datetime.now(timezone.utc).isoformat(), attempt_id),
                )
            return report
        except BaseException as exc:
            with connection:
                connection.execute(
                    "UPDATE attempts SET status='failed',finished_at=?,error=? WHERE attempt_id=?",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        f"{type(exc).__name__}: {exc}",
                        attempt_id,
                    ),
                )
            raise
        finally:
            connection.close()
