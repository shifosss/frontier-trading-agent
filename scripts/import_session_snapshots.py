"""Import exact retained daily snapshots; no network or invented history."""

import argparse
import hashlib
import json
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from frontier.data import ACTIONS_COLUMNS, import_dataset

FILES = {
    "SPY": "alpha_vantage_spy_daily_compact_2026-09-17.json",
    "XIU": "alpha_vantage_xiu_trt_daily_compact_2026-09-17.json",
    "dividends": "alpha_vantage_spy_dividends_2026-09-18.json",
    "fx": "boc_fxusdcad_2026-04-27_2026-09-17.json",
}


def import_snapshots(workspace: Path):
    workspace = Path(workspace)
    raw = workspace / "data/raw"
    snapshots = {
        key: json.loads((raw / filename).read_text(encoding="utf-8-sig"))
        for key, filename in FILES.items()
    }
    bars = []
    instruments = [
        {
            "id": "SPY.ARCX",
            "symbol": "SPY",
            "venue": "ARCX",
            "currency": "USD",
            "asset_type": "etf",
            "exposure_group": "us-large-cap",
        },
        {
            "id": "XIU.XTSE",
            "symbol": "XIU",
            "venue": "XTSE",
            "currency": "CAD",
            "asset_type": "etf",
            "exposure_group": "canada-large-cap",
        },
    ]
    provenance = {}
    for spec in instruments:
        snapshot = snapshots[spec["symbol"]]
        calendar = xcals.get_calendar("XNYS" if spec["venue"] == "ARCX" else "XTSE")
        dates = sorted(snapshot["Time Series (Daily)"])
        provenance[spec["symbol"]] = {
            "provider_metadata": snapshot["Meta Data"],
            "original_start": dates[0],
            "original_end": dates[-1],
            "count": len(dates),
        }
        for date, observation in snapshot["Time Series (Daily)"].items():
            close_time = calendar.session_close(date)
            bars.append(
                {
                    "instrument_id": spec["id"],
                    "event_time": close_time.isoformat(),
                    "available_at": (close_time + pd.Timedelta(minutes=1)).isoformat(),
                    **{
                        name: float(observation[f"{number}. {name}"])
                        for number, name in enumerate(("open", "high", "low", "close", "volume"), 1)
                    },
                }
            )
    bars = pd.DataFrame(bars).sort_values(["event_time", "instrument_id"])
    fx = []
    for observation in snapshots["fx"]["observations"]:
        if "v" not in observation.get("FXUSDCAD", {}):
            continue
        day = pd.Timestamp(observation["d"], tz="America/Toronto")
        publication = day + pd.Timedelta(hours=16, minutes=30)
        fx.append(
            {
                "event_time": (day + pd.Timedelta(hours=12)).tz_convert("UTC").isoformat(),
                "available_at": publication.tz_convert("UTC").isoformat(),
                "usd_cad": float(observation["FXUSDCAD"]["v"]),
                "source": (
                    "Bank of Canada Valet FXUSDCAD; publication inferred 16:30 America/Toronto"
                ),
            }
        )
    sources = {
        "SPY": "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=SPY",
        "XIU": "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=XIU.TRT",
        "dividends": "https://www.alphavantage.co/query?function=DIVIDENDS&symbol=SPY",
        "fx": "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=2026-04-27&end_date=2026-09-17",
    }
    provenance.update(
        source_urls=sources,
        raw_files={
            filename: hashlib.sha256((raw / filename).read_bytes()).hexdigest()
            for filename in FILES.values()
        },
        fx_series=snapshots["fx"]["seriesDetail"],
        fx_terms=snapshots["fx"].get("terms"),
    )
    manifests = []
    for label, start in (("full", None), ("2026-06-22_2026-09-17", "2026-06-22")):
        selected = bars if start is None else bars.loc[bars.event_time >= start].copy()
        minimum, maximum = selected.event_time.min()[:10], selected.event_time.max()[:10]
        actions = []
        for dividend in snapshots["dividends"]["data"]:
            ex_date = dividend["ex_dividend_date"]
            if minimum <= ex_date <= maximum:
                event = xcals.get_calendar("XNYS").session_open(ex_date)
                actions.append(
                    {
                        "instrument_id": "SPY.ARCX",
                        "event_time": event.isoformat(),
                        "available_at": event.isoformat(),
                        "type": "dividend",
                        "cash_amount": float(dividend["amount"]),
                        "currency": "USD",
                        "ratio": None,
                    }
                )
        destination = workspace / "data/imports" / f"session-snapshots-{label}"
        destination.mkdir(parents=True, exist_ok=True)
        selected.to_csv(destination / "bars.csv", index=False)
        pd.DataFrame(fx).to_csv(destination / "fx.csv", index=False)
        pd.DataFrame(actions, columns=ACTIONS_COLUMNS).to_csv(
            destination / "actions.csv", index=False
        )
        metadata = {
            "schema_version": 1,
            "name": f"SPY + XIU retained daily observations ({label})",
            "mode": "historical",
            "source": "Alpha Vantage daily snapshots + Bank of Canada Valet",
            "source_url": sources["SPY"],
            "retrieved_at": "2026-09-18T00:00:00Z",
            "usage_notes": "Local retained snapshots; retrieval date known, exact time unrecorded. "
            "Provider terms apply. Full source provenance: "
            + json.dumps(provenance, sort_keys=True),
            "availability_basis": "inferred",
            "corporate_actions_status": "unknown",
            "instruments": instruments,
            "interval": "1d",
            "adjustment_policy": "raw",
            "limitations": [
                "EXPLORATORY raw prices; Canadian corporate-action coverage unknown",
                (
                    "Historical close availability inferred at official close "
                    "plus one minute; not observed"
                ),
                "FX publication inferred at 16:30 America/Toronto with DST; no future rate use",
                "Known SPY dividends included by economic ex-date; known actions reject replay",
                (
                    "Separate June22 window starts flat after June18 ex-date; no "
                    "inherited July31 receivable"
                ),
                "Only retained compact daily snapshots; no fabricated history or hourly bars",
            ],
        }
        (destination / "dataset.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        manifests.append(import_dataset(destination, workspace / "data/datasets"))
    return manifests


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(
        json.dumps([m.model_dump(mode="json") for m in import_snapshots(args.workspace)], indent=2)
    )
