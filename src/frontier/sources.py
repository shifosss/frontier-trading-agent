"""Narrow read-only source capture and explicit retained-hourly conversion."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import exchange_calendars as xcals
import httpx
import pandas as pd

from frontier.data import ACTIONS_COLUMNS, BARS_COLUMNS, FX_COLUMNS, import_dataset

LONG_BRIDGE = Path(
    shutil.which("longbridge")
    or Path.home() / "AppData" / "Local" / "Programs" / "longbridge" / "longbridge.exe"
)
LONG_BRIDGE_DOCS = "https://open.longbridge.com/docs/quote/pull/history-candlestick"
BOC_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"
RAW_FILES = {
    "hourly": "longbridge_spy_hourly_2026-06-22_2026-09-17.json",
    "daily": "alpha_vantage_spy_daily_compact_2026-09-17.json",
    "actions": "alpaca_spy_actions_2026-06-22_2026-09-17.json",
    "fx": "boc_fxusdcad_2026-04-27_2026-09-17.json",
}


def _dates(start: str, end: str):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("start must not follow end")
    return first, last


def _utc(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("capture and observation timestamps require an explicit timezone")
    return timestamp.tz_convert("UTC")


def _cached(directory: Path, key: str):
    index = directory / f"{key}.capture.json"
    if not index.exists():
        return None
    metadata = json.loads(index.read_text(encoding="utf-8"))
    raw = (directory / metadata["raw_file"]).resolve()
    if raw.parent != directory.resolve():
        raise ValueError("cached raw file must remain in capture directory")
    content = raw.read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
        raise ValueError("cached source digest differs; refresh explicitly")
    return {
        "payload": json.loads(content),
        "raw_path": str(raw),
        "retrieved_at": metadata["retrieved_at"],
        "cache_hit": True,
        "request": metadata["request"],
    }


def _capture(directory: Path, key: str, content: bytes, request: dict):
    payload = json.loads(content)
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    raw = directory / f"{key}.{digest}.json"
    if not raw.exists():
        raw.write_bytes(content)
    retrieved = datetime.now(timezone.utc).isoformat()
    metadata = {
        "raw_file": raw.name,
        "sha256": digest,
        "retrieved_at": retrieved,
        "request": request,
    }
    (directory / f"{key}.capture.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "payload": payload,
        "raw_path": str(raw.resolve()),
        "retrieved_at": retrieved,
        "cache_hit": False,
        "request": request,
    }


def fetch_boc_fx(
    start: str,
    end: str,
    capture_dir: Path,
    *,
    refresh: bool = False,
    timeout: float = 15,
    client: httpx.Client | None = None,
):
    """Fetch only public FXUSDCAD; explicitly reuse a dated, digest-checked capture."""
    _dates(start, end)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    directory = Path(capture_dir)
    key = f"boc_fxusdcad_{start}_{end}"
    if not refresh and (cached := _cached(directory, key)):
        return cached
    params = {"start_date": start, "end_date": end}
    owns_client = client is None
    client = client or httpx.Client()
    try:
        response = client.get(BOC_URL, params=params, timeout=timeout)
        response.raise_for_status()
        if not isinstance(response.json().get("observations"), list):
            raise ValueError("BoC response is missing observations")
        return _capture(directory, key, response.content, {"url": BOC_URL, "params": params})
    finally:
        if owns_client:
            client.close()


def _cli(executable: Path, args: list[str], timeout: float):
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    return subprocess.run(
        [str(executable), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def longbridge_status(executable: Path = LONG_BRIDGE, *, timeout: float = 10):
    """Read documented CLI auth status; never inspect credential files or authenticate."""
    response = _cli(executable, ["auth", "status", "--format", "json"], timeout)
    if response.returncode != 0:
        raise RuntimeError("Longbridge status failed; inspect the installed CLI manually")
    payload = json.loads(response.stdout)
    status = str(payload.get("token", {}).get("status", "unknown")).lower()
    return {
        "provider": "longbridge_standalone_cli",
        "status": status,
        "authenticated": status in {"valid", "active"},
        "hint": "Run longbridge auth login manually to re-authenticate"
        if status not in {"valid", "active"}
        else None,
        "scope": "Standalone CLI authentication; separate from the app connector",
    }


def fetch_longbridge_history(
    symbol: str,
    start: str,
    end: str,
    capture_dir: Path,
    *,
    executable: Path = LONG_BRIDGE,
    refresh: bool = False,
    timeout: float = 30,
):
    """US regular-session raw hourly quotes only. No login, update or trade command."""
    first, last = _dates(start, end)
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}\.US", symbol):
        raise ValueError("This adapter only accepts explicit US symbols such as SPY.US")
    calendar = xcals.get_calendar(
        "XNYS", start=str(first - pd.Timedelta(days=7)), end=str(last + pd.Timedelta(days=7))
    )
    sessions = calendar.sessions_in_range(str(first), str(last))
    maximum_rows = sum(
        len(
            pd.date_range(
                calendar.session_open(s), calendar.session_close(s), freq="h", inclusive="left"
            )
        )
        for s in sessions
    )
    if maximum_rows >= 1000:
        raise ValueError("Requested window may hit the 1000-row cap; split it into smaller windows")
    directory = Path(capture_dir)
    key = f"longbridge_{symbol}_{start}_{end}_1h"
    if not refresh and (cached := _cached(directory, key)):
        return cached
    status = longbridge_status(executable, timeout=min(timeout, 10))
    if not status["authenticated"]:
        raise RuntimeError(f"Longbridge CLI auth is {status['status']}. {status['hint']}")
    args = [
        "kline",
        "history",
        symbol,
        "--period",
        "1h",
        "--start",
        start,
        "--end",
        end,
        "--adjust",
        "none",
        "--session",
        "intraday",
        "--format",
        "json",
    ]
    response = _cli(executable, args, timeout)
    if response.returncode != 0:
        raise RuntimeError("Longbridge history failed; check quote entitlement and CLI status")
    payload = json.loads(response.stdout)
    if not isinstance(payload, list) or len(payload) >= 1000:
        raise ValueError("Unexpected/capped Longbridge response; request a smaller window")
    return _capture(
        directory, key, response.stdout.encode("utf-8"), {"provider": "longbridge", "args": args}
    )


def hourly_rows(snapshot: list[dict], captured_at) -> pd.DataFrame:
    """Convert period starts to official endpoints; refuse partial/future observations."""
    if not snapshot:
        raise ValueError("Hourly snapshot is empty")
    captured = _utc(captured_at)
    starts = [_utc(row.get("timestamp", row.get("time"))) for row in snapshot]
    calendar = xcals.get_calendar(
        "XNYS",
        start=str(min(starts).date() - pd.Timedelta(days=7)),
        end=str(max(starts).date() + pd.Timedelta(days=7)),
    )
    rows = []
    for record, opening in zip(snapshot, starts, strict=True):
        session = opening.tz_convert("America/New_York").date().isoformat()
        if not calendar.is_session(session):
            raise ValueError(f"{opening}: not a US exchange session")
        market_open, market_close = calendar.session_open(session), calendar.session_close(session)
        allowed = pd.date_range(market_open, market_close, freq="h", inclusive="left")
        if opening not in allowed or record.get("trade_session", "Intraday") != "Intraday":
            raise ValueError(f"{opening}: not a regular hourly bar start")
        ending = min(opening + pd.Timedelta(hours=1), market_close)
        available = ending + pd.Timedelta(minutes=1)
        if ending > captured or available > captured:
            raise ValueError(f"{opening}: unfinished or not yet available at captured time")
        rows.append(
            {
                "instrument_id": "SPY.ARCX",
                "event_time": ending.isoformat(),
                "available_at": available.isoformat(),
                **{key: float(record[key]) for key in ("open", "high", "low", "close", "volume")},
            }
        )
    frame = (
        pd.DataFrame(rows, columns=BARS_COLUMNS).sort_values("event_time").reset_index(drop=True)
    )
    if frame.event_time.duplicated().any():
        raise ValueError("Duplicate hourly endpoint in source snapshot")
    return frame


def boc_rows(snapshot: dict, captured_at) -> pd.DataFrame:
    captured = _utc(captured_at)
    rows = []
    for observation in snapshot["observations"]:
        if "v" not in observation.get("FXUSDCAD", {}):
            continue
        day = pd.Timestamp(observation["d"], tz="America/Toronto")
        available = day + pd.Timedelta(hours=16, minutes=30)
        if available.tz_convert("UTC") > captured:
            continue
        rows.append(
            {
                "event_time": (day + pd.Timedelta(hours=12)).tz_convert("UTC").isoformat(),
                "available_at": available.tz_convert("UTC").isoformat(),
                "usd_cad": float(observation["FXUSDCAD"]["v"]),
                "source": "Bank of Canada FXUSDCAD; publication inferred 16:30 Toronto",
            }
        )
    return pd.DataFrame(rows, columns=FX_COLUMNS)


def alpaca_action_rows(snapshot: dict, start: str, end: str):
    first, last = _dates(start, end)
    rows, excluded = [], []
    announcements = snapshot.get("announcements", {})
    unsupported = [key for key, value in announcements.items() if value and key != "cash_dividends"]
    if unsupported:
        raise ValueError(
            f"Unsupported Alpaca action categories require explicit mapping: {unsupported}"
        )
    for record in announcements.get("cash_dividends", []):
        if record.get("symbol") != "SPY":
            raise ValueError("Action source must contain only SPY")
        ex_date = date.fromisoformat(record["ex_date"])
        if not first <= ex_date <= last:
            excluded.append(
                {
                    "ex_date": record["ex_date"],
                    "payable_date": record.get("payable_date"),
                    "process_date": record.get("process_date"),
                    "reason": "Economic ex-date outside flat-start study window",
                }
            )
            continue
        event = xcals.get_calendar("XNYS").session_open(record["ex_date"])
        rows.append(
            {
                "instrument_id": "SPY.ARCX",
                "event_time": event.isoformat(),
                "available_at": event.isoformat(),
                "type": "dividend",
                "cash_amount": float(record["rate"]),
                "currency": "USD",
                "ratio": None,
            }
        )
    return pd.DataFrame(rows, columns=ACTIONS_COLUMNS), excluded


def compare_daily(hourly: pd.DataFrame, daily_snapshot: dict):
    work = hourly.assign(
        day=pd.to_datetime(hourly.event_time)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d")
    )
    aggregated = work.groupby("day", sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    differences = []
    daily = daily_snapshot["Time Series (Daily)"]
    for day, observed in aggregated.iterrows():
        if day not in daily:
            continue
        differences.append(
            {
                "date": day,
                **{
                    field: {
                        "longbridge": float(observed[field]),
                        "alpha_vantage": float(daily[day][f"{i}. {field}"]),
                        "difference": float(observed[field]) - float(daily[day][f"{i}. {field}"]),
                    }
                    for i, field in enumerate(("open", "high", "low", "close", "volume"), 1)
                },
            }
        )
    return {
        "matched_days": len(differences),
        "hourly_days": len(aggregated),
        "max_absolute_difference": {
            field: max((abs(row[field]["difference"]) for row in differences), default=None)
            for field in ("open", "high", "low", "close", "volume")
        },
        "daily_comparison": differences,
        "interpretation": "Cross-source comparison only; discrepancies retained, not reconciled",
    }


def import_longbridge_snapshot(workspace: Path, *, captured_at=None):
    workspace = Path(workspace).resolve()
    raw = workspace / "data" / "raw"
    capture_basis = "explicit caller-provided capture boundary"
    if captured_at is None:
        captured_at = datetime.fromtimestamp(
            (raw / RAW_FILES["hourly"]).stat().st_mtime, timezone.utc
        )
        capture_basis = "observed local snapshot file mtime; not provider response timestamp"
    snapshots = {
        key: json.loads((raw / name).read_text(encoding="utf-8-sig"))
        for key, name in RAW_FILES.items()
    }
    bars = hourly_rows(snapshots["hourly"], captured_at)
    start, end = bars.event_time.iloc[0][:10], bars.event_time.iloc[-1][:10]
    actions, excluded = alpaca_action_rows(snapshots["actions"], start, end)
    comparison = compare_daily(bars, snapshots["daily"])
    hashes = {
        name: hashlib.sha256((raw / name).read_bytes()).hexdigest() for name in RAW_FILES.values()
    }
    source = workspace / "data" / "imports" / f"longbridge-spy-hourly-{start}_{end}"
    source.mkdir(parents=True, exist_ok=True)
    bars.to_csv(source / "bars.csv", index=False)
    actions.to_csv(source / "actions.csv", index=False)
    boc_rows(snapshots["fx"], captured_at).to_csv(source / "fx.csv", index=False)
    provenance = {
        "raw_files": hashes,
        "excluded_actions": excluded,
        "comparison": {
            key: value for key, value in comparison.items() if key != "daily_comparison"
        },
    }
    metadata = {
        "name": "SPY retained Longbridge hourly snapshot (exploratory)",
        "mode": "historical",
        "source": "Longbridge app connector + Alpaca + Bank of Canada",
        "source_url": LONG_BRIDGE_DOCS,
        "retrieved_at": _utc(captured_at).isoformat(),
        "usage_notes": "Retained app-connector response; provider terms apply. Capture date "
        "basis: " + capture_basis + ". "
        "Provenance: " + json.dumps(provenance, sort_keys=True),
        "availability_basis": "inferred",
        "corporate_actions_status": "unknown",
        "interval": "1h",
        "adjustment_policy": "raw",
        "instruments": [
            {
                "id": "SPY.ARCX",
                "symbol": "SPY",
                "venue": "ARCX",
                "currency": "USD",
                "asset_type": "etf",
                "exposure_group": "us-large-cap",
            }
        ],
        "limitations": [
            "EXPLORATORY RAW-PRICE ONLY; action coverage unknown; not total return",
            "Provider timestamps interpreted as period starts; last session bar is partial",
            "Availability inferred at bar endpoint plus one minute; not observed publication",
            "FX publication inferred at 16:30 America/Toronto with DST; reporting only",
            "Window starts flat after June18 ex-date; July31 payment creates no entitlement",
            "Alpaca process_date is not economic ex-date; action coverage remains unknown",
            "US hourly observations only; no Canadian hourly qualification",
            "Historical quote snapshot from app connector does not prove standalone CLI auth",
            "Cross-source daily differences preserved; no forced agreement",
        ],
    }
    (source / "dataset.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    manifest = import_dataset(source, workspace / "data" / "datasets")
    evidence = {
        "dataset_id": manifest.dataset_id,
        "row_count": len(bars),
        "start": start,
        "end": end,
        "actions_in_window": len(actions),
        "excluded_actions": excluded,
        "comparison": comparison,
        "source_files": hashes,
        "capture_basis": capture_basis,
    }
    report = workspace / "artifacts" / "sources" / "longbridge-hourly-import.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return {
        "manifest": manifest.model_dump(mode="json"),
        "evidence_path": str(report),
        "comparison": comparison,
        "excluded_actions": excluded,
    }
