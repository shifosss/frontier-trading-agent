"""Public daily captures for the scanner, separate from raw-price engine datasets."""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import exchange_calendars as xcals
import httpx
import numpy as np
import pandas as pd

COLUMNS = ["symbol", "session", "available_at", "close", "adjusted_close", "high", "low", "volume"]


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def load_universe(workspace):
    universe = json.loads((Path(workspace) / "config/scanner_universe.json").read_text("utf-8"))
    symbols = [spec["symbol"] for spec in universe]
    if not universe or len(symbols) != len(set(symbols)):
        raise ValueError("Scanner universe must contain distinct symbols")
    for spec in universe:
        if not re.fullmatch(r"[A-Z0-9.^-]{1,20}", spec["symbol"]):
            raise ValueError("Invalid scanner symbol")
        if (spec["currency"], spec["calendar"]) not in {("USD", "XNYS"), ("CAD", "XTSE")}:
            raise ValueError("Scanner supports USD/XNYS and CAD/XTSE daily instruments")
    return universe


def normalize_chart(payload, spec, captured_at):
    """Keep provider-adjusted feature prices; never label them raw execution prices."""
    chart = payload["chart"]
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"Provider returned no history: {chart.get('error')}")
    result = chart["result"][0]
    if result["meta"].get("symbol", "").upper() != spec["symbol"].upper():
        raise ValueError("Provider symbol differs from the declared universe")
    if result["meta"]["currency"] != spec["currency"]:
        raise ValueError("Provider currency differs from the declared universe")
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"].get("adjclose")
    if not adjusted:
        raise ValueError("Provider adjusted-close history is unavailable")
    stamps = result.get("timestamp", [])
    fields = {key: quote[key] for key in ("close", "high", "low", "volume")}
    fields["adjusted_close"] = adjusted[0]["adjclose"]
    if any(len(values) != len(stamps) for values in fields.values()):
        raise ValueError("Provider daily arrays have different lengths")
    calendar = xcals.get_calendar(spec["calendar"])
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError("Capture time must include timezone")
    records = []
    for index, stamp in enumerate(stamps):
        session = (
            pd.Timestamp(stamp, unit="s", tz="UTC").tz_convert("America/Toronto").date().isoformat()
        )
        if not calendar.is_session(session):
            continue
        available = calendar.session_close(session) + pd.Timedelta(minutes=1)
        if available > captured:
            continue
        values = {key: items[index] for key, items in fields.items()}
        if any(value is None or not np.isfinite(value) for value in values.values()):
            continue
        if any(values[key] <= 0 for key in ("close", "adjusted_close", "high", "low")):
            raise ValueError(f"Non-positive price at {session}")
        if values["volume"] < 0 or not values["low"] <= values["close"] <= values["high"]:
            raise ValueError(f"Invalid OHLCV at {session}")
        records.append(
            {"symbol": spec["symbol"], "session": session, "available_at": available, **values}
        )
    frame = pd.DataFrame(records, columns=COLUMNS)
    if frame.empty or frame.session.duplicated().any():
        raise ValueError("Daily history is empty or contains duplicate sessions")
    return frame.sort_values("session").reset_index(drop=True)


def capture_universe(workspace, universe, refresh=True):
    workspace = Path(workspace)
    root = workspace / "data/scanner"
    latest = root / "latest.json"
    if not refresh and latest.exists():
        manifest = json.loads(latest.read_text("utf-8"))
        if manifest["universe"] == universe:
            return manifest, True
    capture_id = uuid4().hex
    raw_root = root / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    def fetch(spec):
        symbol = spec["symbol"]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"range": "5y", "interval": "1d", "events": "div,splits"}
        try:
            response = httpx.get(
                url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=20
            )
            response.raise_for_status()
            content = response.content
            captured = datetime.now(timezone.utc).isoformat()
            frame = normalize_chart(response.json(), spec, captured)
            digest = hashlib.sha256(content).hexdigest()
            relative = f"data/scanner/raw/{symbol}.{digest}.json"
            path = workspace / relative
            if not path.exists():
                path.write_bytes(content)
            return {
                "symbol": symbol,
                "path": relative,
                "sha256": digest,
                "captured_at": captured,
                "url": str(response.url),
                "rows": len(frame),
                "first_session": frame.session.iloc[0],
                "last_session": frame.session.iloc[-1],
            }
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            return {"symbol": symbol, "error": str(exc)}

    # ponytail: four concurrent requests; add adapters only for demonstrated coverage gaps.
    with ThreadPoolExecutor(max_workers=4) as pool:
        captures = list(pool.map(fetch, universe))
    manifest = {
        "capture_id": capture_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "universe": universe,
        "captures": captures,
        "source": "Yahoo Finance daily chart",
        "price_basis": "provider adjusted close; OHLC may already reflect splits",
        "availability_basis": "historical close plus one minute inferred; current-vintage data",
    }
    _write(root / "captures" / f"{capture_id}.json", manifest)
    _write(latest, manifest)
    return manifest, False


def read_capture(workspace, manifest):
    workspace = Path(workspace).resolve()
    specs = {spec["symbol"]: spec for spec in manifest["universe"]}
    frames = []
    for record in manifest["captures"]:
        if "error" in record:
            continue
        path = (workspace / record["path"]).resolve()
        if not path.is_relative_to(workspace / "data/scanner/raw"):
            raise ValueError("Capture path is outside scanner raw data")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Scanner source bytes changed; fetch a new capture")
        frames.append(
            normalize_chart(json.loads(raw), specs[record["symbol"]], record["captured_at"])
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def run_scan(workspace, *, refresh=True, initial_cash_usd=0, initial_cash_cad=700):
    from frontier.scanner import build_scan, forward_diagnostics

    workspace = Path(workspace)
    cash = {"USD": initial_cash_usd, "CAD": initial_cash_cad}
    if (
        any(not np.isfinite(value) or value < 0 for value in cash.values())
        or sum(cash.values()) <= 0
    ):
        raise ValueError("Specify finite nonnegative simulated balances with some funding")
    universe = load_universe(workspace)
    manifest, cached = capture_universe(workspace, universe, refresh=refresh)
    frame = read_capture(workspace, manifest)
    as_of = datetime.now(timezone.utc).isoformat()
    scan = build_scan(frame, universe, as_of, cash)
    study = forward_diagnostics(frame, universe, as_of, cash)
    digest = hashlib.sha256()
    for name in ("scanner.py", "scan_data.py"):
        digest.update((Path(__file__).parent / name).read_text("utf-8").encode())
    envelope = {
        "scan_id": uuid4().hex,
        "created_at": as_of,
        "universe": universe,
        "code_identity": "sha256:" + digest.hexdigest(),
        "source": {
            "name": manifest["source"],
            "as_of": manifest["captured_at"],
            "capture_id": manifest["capture_id"],
            "cached": cached,
            "succeeded": sum("error" not in row for row in manifest["captures"]),
            "failed": [row for row in manifest["captures"] if "error" in row],
        },
        "scan": scan,
        "study": study,
        "readiness": {
            "status": "research_only",
            "reasons": [
                "Fixed daily ranking has not established prospective net profitability.",
                "Sizing uses simulated balances; existing holdings and account restrictions "
                "are not integrated.",
                "Daily reference prices are not executable quotes; "
                "broker paper reconciliation is unqualified.",
                "Provider-adjusted series and today's declared universe support retrospective "
                "diagnostics, not point-in-time certification.",
            ],
        },
    }
    _write(workspace / "artifacts/scans" / envelope["scan_id"] / "scan.json", envelope)
    return envelope


def list_scans(workspace):
    root = Path(workspace) / "artifacts/scans"
    return sorted(
        (json.loads(path.read_text("utf-8")) for path in root.glob("*/scan.json")),
        key=lambda value: value["created_at"],
        reverse=True,
    )
