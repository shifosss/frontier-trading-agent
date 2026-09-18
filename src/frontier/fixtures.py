"""Fictional offline data for engineering tests; no market observations."""

import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd


def generate_fixture(destination: Path, seed: int = 1729) -> Path:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    instruments = [
        {
            "id": "FICTUS.XNYS",
            "symbol": "FICTUS",
            "venue": "XNYS",
            "currency": "USD",
            "asset_type": "stock",
            "exposure_group": "fictional-us",
        },
        {
            "id": "FICTCA.XTSE",
            "symbol": "FICTCA",
            "venue": "XTSE",
            "currency": "CAD",
            "asset_type": "etf",
            "exposure_group": "fictional-canada",
        },
    ]
    bars = []
    for market, instrument in enumerate(instruments):
        calendar = xcals.get_calendar(instrument["venue"])
        sessions = calendar.sessions_in_range("2025-01-02", "2025-08-29")
        previous = 80.0 + market * 20
        for index, session in enumerate(sessions):
            drift = 0.003 if index < 50 else (-0.002 if index >= 110 else 0.001)
            cycle = 0.009 * np.sin(index / 3) if index >= 50 else 0
            opening = previous * (1 + rng.normal(0, 0.001))
            close = opening * (1 + drift + cycle + rng.normal(0, 0.002))
            event = calendar.session_close(session)
            bars.append(
                {
                    "instrument_id": instrument["id"],
                    "event_time": event.isoformat(),
                    "available_at": (event + pd.Timedelta(minutes=1)).isoformat(),
                    "open": round(opening, 4),
                    "high": round(max(opening, close) * 1.004, 4),
                    "low": round(min(opening, close) * 0.996, 4),
                    "close": round(close, 4),
                    "volume": int(rng.integers(100_000, 500_000)),
                }
            )
            previous = close
    pd.DataFrame(bars).to_csv(destination / "bars.csv", index=False)
    fx = []
    for index, day in enumerate(pd.date_range("2024-12-31", "2025-08-29", freq="B")):
        event = day.tz_localize("America/Toronto") + pd.Timedelta(hours=12)
        publication = day.tz_localize("America/Toronto") + pd.Timedelta(hours=16, minutes=30)
        fx.append(
            {
                "event_time": event.tz_convert("UTC").isoformat(),
                "available_at": publication.tz_convert("UTC").isoformat(),
                "usd_cad": round(1.35 + 0.025 * np.sin(index / 15), 6),
                "source": "fictional-fixed-seed-FX; not Bank of Canada observations",
            }
        )
    pd.DataFrame(fx).to_csv(destination / "fx.csv", index=False)
    metadata = {
        "schema_version": 1,
        "name": "Fictional US and Canada engineering fixture",
        "mode": "synthetic_fixture",
        "source": f"frontier-fixture-v1-seed-{seed}",
        "source_url": "local:examples/generate_fixture.py",
        "retrieved_at": "2025-09-01T00:00:00Z",
        "usage_notes": "Generated offline for software tests only; no market observations.",
        "availability_basis": "documented",
        "adjustment_policy": "raw",
        "corporate_actions_status": "complete",
        "instruments": instruments,
        "interval": "1d",
        "limitations": [
            "Synthetic fictional prices and FX; engineering evidence only",
            "No corporate actions are defined in this fictional fixture",
            "FX publication modeled at 16:30 America/Toronto; not an executable quote",
        ],
    }
    (destination / "dataset.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return destination
