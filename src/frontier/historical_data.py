"""Long daily research histories, isolated from the frozen paper data contract."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import exchange_calendars as xcals
import httpx
import numpy as np
import pandas as pd

from frontier.scan_data import COLUMNS

DEFAULT_START = "2000-01-01"


def _reported_split_factors(result, sessions, captured):
    """Undo Yahoo split adjustments using reported effective-session events."""
    factors = np.ones(len(sessions), dtype=float)
    split_sessions = []
    capture_session = captured.tz_convert("America/Toronto").date().isoformat()
    for event in result.get("events", {}).get("splits", {}).values():
        numerator, denominator = float(event["numerator"]), float(event["denominator"])
        if not np.isfinite([numerator, denominator]).all() or min(numerator, denominator) <= 0:
            raise ValueError("Invalid reported split ratio")
        session = (
            pd.Timestamp(event["date"], unit="s", tz="UTC")
            .tz_convert("America/Toronto")
            .date()
            .isoformat()
        )
        if session > capture_session:
            continue
        if session in split_sessions:
            raise ValueError("Multiple reported splits on one session")
        split_sessions.append(session)
        # A split-day bar already uses new shares, even if event and bar times differ.
        factors[sessions < session] *= numerator / denominator
    if not np.isfinite(factors).all() or (factors <= 0).any():
        raise ValueError("Invalid cumulative split factor")
    return factors, {
        "method": "nominal OHLC = provider OHLC * later reported split ratios; volume inverse",
        "reported_effective_events": len(split_sessions),
        "last_reported_split_session": max(split_sessions) if split_sessions else None,
        "minimum_factor": float(factors.min()),
        "maximum_factor": float(factors.max()),
        "event_completeness": "Provider-reported events; independently complete history unverified",
    }


def normalize_history(payload, spec, captured_at, *, as_of=None):
    """Reconstruct nominal shares and prices; keep adjusted close for total returns."""
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
    if not stamps or any(len(values) != len(stamps) for values in fields.values()):
        raise ValueError("Provider daily arrays are empty or have different lengths")
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError("Capture time must include timezone")
    cutoff = pd.Timestamp(as_of) if as_of is not None else captured
    if cutoff.tzinfo is None:
        raise ValueError("Historical cutoff must include timezone")
    cutoff = min(captured, cutoff)
    dates = pd.to_datetime(stamps, unit="s", utc=True).tz_convert("America/Toronto")
    sessions = dates.strftime("%Y-%m-%d")
    calendar = xcals.get_calendar(
        spec["calendar"],
        start=f"{min(dates.min().year, 2000)}-01-01",
        end=f"{max(dates.max().year, captured.year) + 1}-01-01",
    )
    closes = calendar.schedule["close"] + pd.Timedelta(minutes=1)
    closes.index = closes.index.strftime("%Y-%m-%d")
    frame = pd.DataFrame(fields)
    frame[list(fields)] = frame[list(fields)].apply(pd.to_numeric, errors="coerce")
    factors, split_audit = _reported_split_factors(result, sessions, captured)
    frame[["close", "high", "low"]] = frame[["close", "high", "low"]].mul(factors, axis=0)
    frame["volume"] = frame.volume / factors
    frame["symbol"] = spec["symbol"]
    frame["session"] = sessions
    frame["available_at"] = pd.to_datetime(frame.session.map(closes), utc=True)
    frame = frame.loc[frame.available_at.notna() & (frame.available_at <= cutoff)].copy()
    numeric = list(fields)
    frame = frame.loc[np.isfinite(frame[numeric].to_numpy()).all(axis=1)].copy()
    if (frame[["close", "adjusted_close", "high", "low"]] <= 0).any().any():
        raise ValueError("Non-positive price in daily history")
    if ((frame.volume < 0) | (frame.low > frame.close) | (frame.close > frame.high)).any():
        raise ValueError("Invalid OHLCV in daily history")
    if frame.empty or frame.session.duplicated().any():
        raise ValueError("Daily history is empty or contains duplicate sessions")
    frame = frame[COLUMNS].sort_values("session").reset_index(drop=True)
    frame.attrs["split_reconstruction"] = split_audit
    return frame


def capture_histories(workspace, universe, *, start=DEFAULT_START, as_of):
    """Four concurrent public requests; each returned record retains its raw source."""
    workspace = Path(workspace)
    first, end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(as_of)
    if end.tzinfo is None or first >= end:
        raise ValueError("Historical interval requires a start before timezone-aware as_of")
    root = workspace / "data/scanner/raw"
    root.mkdir(parents=True, exist_ok=True)
    params = {
        "period1": int(first.timestamp()),
        "interval": "1d",
        "events": "div,splits",
    }

    def fetch(spec):
        symbol = spec["symbol"]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        try:
            # Current adjusted prices require split events through the same vintage.
            # Fetch through now, then apply the experiment cutoff locally.
            requested_through = datetime.now(timezone.utc)
            response = httpx.get(
                url,
                params={**params, "period2": int(requested_through.timestamp())},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
            response.raise_for_status()
            captured = datetime.now(timezone.utc).isoformat()
            frame = normalize_history(response.json(), spec, captured, as_of=as_of)
            digest = hashlib.sha256(response.content).hexdigest()
            relative = f"data/scanner/raw/{symbol}.{digest}.json"
            path = workspace / relative
            if not path.exists():
                temporary = path.with_suffix(f".{uuid4().hex}.tmp")
                temporary.write_bytes(response.content)
                temporary.replace(path)
            return {
                "symbol": symbol,
                "path": relative,
                "sha256": digest,
                "captured_at": captured,
                "url": str(response.url),
                "rows": len(frame),
                "first_session": frame.session.iloc[0],
                "last_session": frame.session.iloc[-1],
                "requested_start": start,
                "requested_as_of": as_of,
                "split_events_requested_through": requested_through.isoformat(),
                "split_reconstruction": frame.attrs["split_reconstruction"],
            }
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            return {"symbol": symbol, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(fetch, universe))


def read_history(workspace, record):
    workspace = Path(workspace).resolve()
    path = (workspace / record["path"]).resolve()
    if not path.is_relative_to(workspace / "data/scanner/raw"):
        raise ValueError("Historical source is outside its capture directory")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise ValueError("Historical source bytes changed; recapture this instrument")
    payload = json.loads(content)
    result = payload["chart"]["result"][0]
    period2 = parse_qs(urlparse(record.get("url", "")).query).get("period2")
    market_time = result["meta"].get("regularMarketTime")
    if period2 and market_time:
        request_date = (
            pd.Timestamp(int(period2[0]), unit="s", tz="UTC").tz_convert("America/Toronto").date()
        )
        quote_date = (
            pd.Timestamp(market_time, unit="s", tz="UTC").tz_convert("America/Toronto").date()
        )
        if request_date < quote_date:
            raise ValueError(
                "Capture omits current-vintage split events; recapture this instrument"
            )
    return normalize_history(
        payload, record["spec"], record["captured_at"], as_of=record.get("requested_as_of")
    )
