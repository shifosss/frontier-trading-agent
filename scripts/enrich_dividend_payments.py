"""Add retained, dated dividend payment facts without altering the old source or dataset."""

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from frontier.data import import_dataset
from frontier.sources import boc_rows, fetch_boc_fx


def enrich(workspace):
    workspace = Path(workspace)
    source = workspace / "data/imports/session-snapshots-full"
    target = workspace / "data/imports/session-snapshots-full-dividend-payments"
    target.mkdir(parents=True, exist_ok=True)
    dividends = json.loads(
        (workspace / "data/raw/alpha_vantage_spy_dividends_2026-09-18.json").read_text("utf-8-sig")
    )["data"]
    by_ex_date = {row["ex_dividend_date"]: row for row in dividends}
    actions = pd.read_csv(source / "actions.csv")
    payment_dates = []
    for row in actions.itertuples():
        if row.type != "dividend" or row.instrument_id != "SPY.ARCX":
            raise ValueError("This source enrichment only covers retained SPY cash dividends")
        ex_date = pd.Timestamp(row.event_time).tz_convert("America/New_York").date().isoformat()
        fact = by_ex_date[ex_date]
        if abs(float(fact["amount"]) - row.cash_amount) > 1e-9:
            raise ValueError("Dividend amount differs between retained sources")
        payment = pd.Timestamp(fact["payment_date"], tz="America/New_York")
        # Date-only payment facts do not establish intraday spendability.
        payment += pd.Timedelta(hours=23, minutes=59, seconds=59)
        payment_dates.append(payment.tz_convert("UTC").isoformat())
    actions["payable_at"] = payment_dates
    actions.to_csv(target / "actions.csv", index=False)
    shutil.copyfile(source / "bars.csv", target / "bars.csv")
    first_bar = pd.to_datetime(pd.read_csv(source / "bars.csv").event_time, utc=True).min()
    prior_fx = fetch_boc_fx(
        (first_bar - pd.Timedelta(days=7)).date().isoformat(),
        (first_bar - pd.Timedelta(days=1)).date().isoformat(),
        workspace / "artifacts/sources/cache",
    )
    earlier = boc_rows(prior_fx["payload"], prior_fx["retrieved_at"])
    earlier = earlier[pd.to_datetime(earlier.available_at, utc=True) < first_bar]
    if earlier.empty:
        raise ValueError("The source must supply a published FX observation before the first bar")
    retained_fx = pd.read_csv(source / "fx.csv")
    fx = pd.concat([earlier, retained_fx], ignore_index=True).sort_values("available_at")
    if fx.event_time.duplicated().any():
        raise ValueError("Prior FX capture overlaps the retained observations")
    fx.to_csv(target / "fx.csv", index=False)
    metadata = json.loads((source / "dataset.json").read_text("utf-8"))
    metadata["name"] = "SPY + XIU full daily history with known dividend payment dates"
    metadata["source"] += "; retained Alpha Vantage dividend payment dates"
    metadata["retrieved_at"] = prior_fx["retrieved_at"]
    metadata["usage_notes"] += "; Earlier published FX capture: " + json.dumps(
        {
            "request": prior_fx["request"],
            "retrieved_at": prior_fx["retrieved_at"],
            "raw_path": prior_fx["raw_path"],
            "sha256": hashlib.sha256(Path(prior_fx["raw_path"]).read_bytes()).hexdigest(),
            "added_observations": len(earlier),
        },
        sort_keys=True,
    )
    metadata["limitations"] = [
        value
        for value in metadata["limitations"]
        if "known actions reject replay" not in value.lower()
        and "Separate June22 window" not in value
    ] + [
        "Known SPY dividend entitlement uses economic ex-date; payment date from retained source.",
        "Date-only payment timestamp conservatively inferred at New York end of day; "
        "cash settles on next replay event.",
        "Gross cash dividends only; account taxes and withholding are not modeled.",
        "Canadian corporate-action coverage remains unknown; "
        "this is not a complete total-return study.",
    ]
    (target / "dataset.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    manifest = import_dataset(target, workspace / "data/datasets")
    print(json.dumps(manifest.model_dump(mode="json"), indent=2))
    return manifest


if __name__ == "__main__":
    enrich(Path.cwd())
