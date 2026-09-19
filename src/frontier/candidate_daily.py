"""Local, unqualified daily model previews from immutable historical captures."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from frontier.daily_policy import POLICY, forecast_score, plan_entries
from frontier.ensemble_features import HORIZONS, build_features
from frontier.ensemble_models import fit_heads, predict_heads
from frontier.ensemble_study import CONFIG, LEARNED, _sample_rows
from frontier.historical_data import read_history
from frontier.historical_lab import _reuse_source_run
from frontier.historical_study import _build_market
from frontier.model_artifact import load_heads, save_heads
from frontier.short_horizon_study import _diversified
from frontier.strategy_study import BOOKS, _prepare

LIMITATIONS = [
    "UNQUALIFIED engineering preview; settings are predeclared, not profit-selected.",
    "Current-member survivorship and adjusted-price vintage are not point-in-time coverage.",
    "Historical evidence is negative or fragile; execution costs remain uncalibrated.",
    "TPX source issue remains unresolved; no guessed split repairs.",
    "Preview quantities use signal prices; next-close simulation must resize actual fills.",
    "Historical frozen-session preview, not current trade instructions.",
    "Isolated all-cash hypothetical account; no paper activation or broker submission.",
]


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def load_saved_history(workspace, capture_run_id, signal_session=None):
    """Verify original source bytes and retain only the needed USD history window."""
    definition, records, failures, evidence = _reuse_source_run(workspace, capture_run_id)
    reuse = definition.get("source_reuse")
    if reuse:
        source, source_records, _, source_evidence = _reuse_source_run(workspace, reuse["run_id"])
        for key in ("definition_sha256", "capture_index_sha256"):
            if reuse[key] != source_evidence[key]:
                raise ValueError("Frozen reused source identity changed")
        if records != source_records or definition["frozen_at"] != source["frozen_at"]:
            raise ValueError("Reused capture differs from original source")
        evidence["original_source"] = source_evidence
    frozen = pd.Timestamp(definition["frozen_at"])
    calendar = xcals.get_calendar(
        "XNYS", start=definition["requested_start"], end=str(frozen.date() + pd.Timedelta(days=30))
    )
    schedule = calendar.schedule
    completed = schedule.index[schedule["close"] + pd.Timedelta(minutes=1) <= frozen]
    dates = completed.strftime("%Y-%m-%d").tolist()
    signal = dates[-1] if signal_session is None else str(signal_session)
    if signal not in dates:
        raise ValueError("Signal must be a completed frozen capture session")
    index = dates.index(signal)
    if index < 1008:
        raise ValueError("Signal requires 252 warmup, 504 fit and 252 calibration sessions")
    first = dates[index - 1008]
    universe = [s for s in definition["instruments"] if s["currency"] == "USD"]
    selected = [r for r in records if r["spec"]["currency"] == "USD"]
    frames, source_hashes, normalization = [], [], []
    capture_workspace = Path(workspace) / "data/historical/capture-workspace"
    for record in selected:
        normalized = read_history(capture_workspace, record)
        normalization.append({"symbol": record["symbol"], **normalized.attrs})
        frames.append(normalized.loc[normalized.session.between(first, signal)].copy())
        source_hashes.append({"symbol": record["symbol"], "sha256": record["sha256"]})
    if not frames:
        raise ValueError("Frozen capture has no USD histories")
    evidence.update(
        source_hashes=source_hashes,
        source_failures=failures,
        normalization=normalization,
        window_start=first,
        signal_session=signal,
        requested_usd_instruments=len(universe),
        usable_usd_histories=len(selected),
    )
    # End at the actual calendar close plus completion latency, never later data.
    current = schedule.loc[pd.Timestamp(signal), "close"] + pd.Timedelta(minutes=1)
    return pd.concat(frames, ignore_index=True), universe, current, evidence


def _sample_audit(features, sessions, symbols, start, end, boundary, seed):
    rows, columns, audit = _sample_rows(features, start, end, boundary, seed)
    if not len(rows):
        raise ValueError("No usable training/calibration rows")
    if np.any(features["label_end"][rows].max(axis=1) >= boundary):
        raise ValueError("Target crosses its chronological cutoff")
    identities = [[sessions[int(r)], symbols[int(c)]] for r, c in zip(rows, columns)]
    audit.update(
        row_identities=identities,
        row_identities_sha256=_digest(identities),
        latest_target_session=sessions[int(features["label_end"][rows].max())],
        exclusive_boundary=sessions[boundary],
    )
    return rows, columns, audit


def _build_candidate(
    workspace,
    capture_run_id,
    signal_session=None,
    budget=2000,
    cost_bps=40,
    horizon=5,
    strategy="calibrated_ensemble",
    *,
    root,
):
    """Fit and reload all heads; persist an immutable, fully ranked decision preview."""
    if horizon not in HORIZONS or strategy not in LEARNED:
        raise ValueError("Unknown learned strategy or horizon")
    if (
        not np.isfinite(budget)
        or budget <= 0
        or not np.isfinite(cost_bps)
        or not 0 <= cost_bps < 20000
    ):
        raise ValueError("Budget must be positive and cost finite and nonnegative")
    workspace = Path(workspace).resolve()
    frame, universe, current, data = load_saved_history(workspace, capture_run_id, signal_session)
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
    sessions, symbols = market["sessions"], market["symbols"]
    signal = len(sessions) - 1
    cal_start, fit_start = signal - 252, signal - 756
    if fit_start < 252:
        raise ValueError("Insufficient chronological feature warmup")
    tr, tc, train = _sample_audit(
        features, sessions, symbols, fit_start, cal_start - 1, cal_start, CONFIG["seed"]
    )
    cr, cc, cal = _sample_audit(
        features, sessions, symbols, cal_start, signal - 1, signal, CONFIG["seed"] + 1
    )
    bundle = fit_heads(
        features["X"][tr, tc],
        features["labels"][tr, tc],
        features["X"][cr, cc],
        features["labels"][cr, cc],
        seed=CONFIG["seed"],
    )
    eligible = features["eligible"][signal] & features["benchmark_known"][signal]
    indices = np.flatnonzero(eligible)
    X = features["X"][signal, indices]
    direct = predict_heads(bundle, X)
    policy = dict(
        strategy=strategy,
        horizon=horizon,
        cost_bps=float(cost_bps),
        screening="every_completed_session",
        execution="next_session_close",
        shared_policy=POLICY,
        preset="predeclared engineering default; not economic selection",
    )
    account = dict(
        currency="USD",
        nav=float(budget),
        settled_cash=float(budget),
        holdings=[],
        reserved_orders=[],
        receivables=[],
        kind="hypothetical_isolated",
    )
    metadata = dict(
        feature_names=features["feature_names"],
        head_names=features["label_names"],
        data=data,
        data_id=_digest(data),
        policy=policy,
        policy_id=_digest(policy),
        account=account,
        account_id=_digest(account),
        fit_sample=train,
        calibration_sample=cal,
        fit_start=sessions[fit_start],
        fit_end=sessions[cal_start - 1],
        calibration_start=sessions[cal_start],
        calibration_end=sessions[signal - 1],
        signal_session=sessions[signal],
        implementation_sha256={
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in (
                "candidate_daily.py",
                "ensemble_study.py",
                "model_artifact.py",
                "historical_lab.py",
                "daily_policy.py",
                "ensemble_features.py",
                "ensemble_models.py",
                "historical_data.py",
                "historical_study.py",
                "strategy_study.py",
            )
        },
    )
    manifest = save_heads(bundle, root / "model", metadata)
    reloaded, _ = load_heads(root / "model")
    predictions = predict_heads(reloaded, X)
    parity = all(np.array_equal(direct[k], predictions[k]) for k in direct)
    if not parity:
        raise ValueError("In-memory and reloaded model predictions differ")
    model_id = manifest["payload_sha256"]
    predicted = predictions[
        "calibrated_ensemble" if strategy == "diversified_ensemble" else strategy
    ]
    scores = forecast_score(predicted, HORIZONS.index(horizon), cost_bps)
    order = np.argsort(-scores, kind="stable")
    ranked = indices[order[scores[order] > 0]]
    correlation = None
    if strategy == "diversified_ensemble":

        def correlation(index, peers):
            return _diversified(
                market["adjusted"],
                signal,
                index,
                peers,
                CONFIG["diversification_correlation_ceiling"],
            )

    plan = plan_entries(
        symbols=symbols,
        ranking=ranked,
        prices=market["close"][signal],
        atrs=market["atr"][signal],
        nav=budget,
        available_cash=budget,
        cost_bps=cost_bps,
        correlation_allowed=correlation,
    )
    identity = {k: metadata[k] for k in ("data_id", "policy_id", "account_id", "signal_session")}
    identity["model_id"] = model_id
    future_calendar = xcals.get_calendar(
        "XNYS",
        start=sessions[signal],
        end=str(pd.Timestamp(sessions[signal]).date() + pd.Timedelta(days=30)),
    )
    future = future_calendar.sessions.strftime("%Y-%m-%d").tolist()
    next_session = future[future.index(sessions[signal]) + 1]
    exit_session = future[future.index(sessions[signal]) + 1 + horizon]
    identity.update(planned_fill_session=next_session, planned_exit_session=exit_session)
    intents = [{**row, "intent_id": _digest({**identity, "order": row})} for row in plan["orders"]]
    decisions = {row["symbol"]: row for row in plan["decisions"]}
    ranking = []
    for rank, local in enumerate(order, 1):
        symbol = symbols[int(indices[local])]
        ranking.append(
            dict(
                symbol=symbol,
                rank=rank,
                score=float(scores[local]),
                forecasts=predicted[local].tolist(),
                reason=decisions.get(symbol, {}).get("reason", "nonpositive_score"),
            )
        )
    rejected = [
        dict(
            symbol=symbol,
            reason="not_stock"
            if specs[symbol]["asset_type"] != "stock"
            else "benchmark_unavailable"
            if not features["benchmark_known"][signal]
            else "ineligible_maturity_liquidity_atr_or_volatility",
        )
        for i, symbol in enumerate(symbols)
        if not eligible[i]
    ]
    report = dict(
        schema_version=1,
        status="unqualified",
        **identity,
        artifact_path=str(root),
        metadata=metadata,
        model_manifest=manifest,
        model_audit=bundle.audit,
        prediction_reload_exact=parity,
        rankings=ranking,
        rejections=rejected,
        intents=intents,
        planning_decisions=plan["decisions"],
        remaining_cash=plan["remaining_cash"],
        universe_count=len(symbols),
        eligible_count=len(indices),
        limitations=LIMITATIONS,
    )
    with (root / "report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    return report


def build_candidate(
    workspace,
    capture_run_id,
    signal_session=None,
    budget=2000,
    cost_bps=40,
    horizon=5,
    strategy="calibrated_ensemble",
):
    """Record every local attempt, including source, fit and reload failures."""
    workspace = Path(workspace).resolve()
    root = workspace / "artifacts/daily-candidates" / uuid4().hex
    root.mkdir(parents=True)
    attempt = {
        "attempt_id": root.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "request": {
            key: str(value)
            if isinstance(value, (float, np.floating)) and not np.isfinite(value)
            else value
            for key, value in {
                "workspace": str(workspace),
                "capture_run_id": capture_run_id,
                "signal_session": signal_session,
                "budget": budget,
                "cost_bps": cost_bps,
                "horizon": horizon,
                "strategy": strategy,
            }.items()
        },
    }
    attempt_path = root / "attempt.json"
    attempt_path.write_text(json.dumps(attempt, indent=2, allow_nan=False), encoding="utf-8")
    try:
        report = _build_candidate(
            workspace,
            capture_run_id,
            signal_session,
            budget,
            cost_bps,
            horizon,
            strategy,
            root=root,
        )
    except BaseException as exc:
        attempt.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    else:
        attempt.update(status="unqualified", model_id=report["model_id"])
        return report
    finally:
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        attempt_path.write_text(json.dumps(attempt, indent=2, allow_nan=False), encoding="utf-8")
