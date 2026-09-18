# Data source examples

These examples are engineering inputs. No generated price or FX value is a market observation.

## Deterministic offline fixture

From the repository root after `uv sync --locked`:

```powershell
.venv\Scripts\python.exe examples/generate_fixture.py data/fixture-source
```

Installed API: `frontier.fixtures.generate_fixture(destination: Path, seed: int = 1729) -> Path`.
The fixed default produces 332 daily bars across fictional FICTUS.XNYS and
FICTCA.XTSE (January 2-August 29, 2025), each with 100+ actual calendar sessions,
and 174 fictional FX rows. Regimes include rising, oscillating and falling prices.
Daily US/Canada holidays differ; prices are never filled across closed sessions.
Bars become available one minute after session close. FX event times are noon,
with publication at 16:30 America/Toronto (including DST), and a prior FX row.
No corporate actions exist in this fictional world; that is why its declared
coverage is complete. This declaration does not qualify engine action handling.

Import and read:

```python
from pathlib import Path
from frontier.data import import_dataset, load_dataset, as_of, fx_as_of

manifest = import_dataset(Path("data/fixture-source"), Path("data/datasets"))
dataset = load_dataset(Path("data/datasets"), manifest.dataset_id)
known_bars = as_of(dataset.bars, "2025-07-02T20:01:00Z")
known_fx = fx_as_of(dataset.fx, "2025-07-02T20:01:00Z")
```

## User historical data template

Copy `real_data_template/` into a new source folder. It intentionally has empty
CSV tables and refuses import until you supply real rows. Replace metadata
placeholders and retrieved_at with actual provenance. Use historical mode only
for real observations, and leave unknown action coverage/availability labeled.
A raw bar dataset must never be built from adjusted-close prices.

`dataset.json` fields:

- schema_version: 1.
- name: human readable source label.
- mode: historical or synthetic_fixture.
- source: provider and dataset/vintage description.
- source_url: original provider URL (multiple sources can be documented in notes).
- retrieved_at: actual timezone-aware retrieval timestamp, normalized to UTC.
- usage_notes: source license, access conditions and intended usage.
- availability_basis: observed/documented/inferred/unknown. Inferred or unknown
  always adds a limitation; an invented timestamp cannot certify point-in-time data.
- adjustment_policy: raw. Corporate actions are stored separately.
- corporate_actions_status: complete/unknown; empty actions do not prove completeness.
- instruments: id=SYMBOL.VENUE, symbol, venue=XNAS/XNYS/ARCX/XTSE,
  currency=USD/CAD, asset_type=stock/etf, exposure_group. Listing venue and
  quote currency are independent (TSX can contain USD listings).
- interval: 1d or 1h. XNAS/XNYS/ARCX use XNYS calendar; XTSE uses XTSE.
- limitations: visible source-quality, timing and universe caveats.

Bars columns: instrument_id,event_time,available_at,open,high,low,close,volume.
Daily event_time must equal actual session close; hourly endpoints begin an hour
after opening and include the final partial hour (and early closes).
Timestamp values require explicit timezone, e.g. 2025-07-02T20:00:00Z.
Prices are finite positive native-currency numbers; volumes finite nonnegative.
Optional revision_id defaults to original. Revisions require different revision_id
and available_at for each instrument/event; original observations remain preserved.

Actions columns: instrument_id,event_time,available_at,type,cash_amount,currency,ratio.
For dividend, cash_amount is positive cash per share and ratio is blank.
For split, ratio is positive new shares per old share and cash_amount is blank.
Currency must match the explicit listing quote currency. Example structure only:
`SYMBOL.XNYS,2025-07-02T13:30:00Z,2025-07-02T13:30:00Z,dividend,1.25,USD,`.
Action storage is supported; action execution remains unqualified.

FX columns: event_time,available_at,usd_cad,source. usd_cad is positive CAD per USD.
Never assign an FX observation to a decision before source publication.
actions.csv and fx.csv are optional; missing FX does not license a 1.0 fallback.

Computed manifest fields are not accepted in source metadata: dataset_id, start,
end, row_count, files, source_files, ingested_at. The importer keeps original
source bytes, digests, canonical metadata, and Parquet records under the SHA-256 ID.
Reimporting unchanged bytes returns the same record and original ingestion time.
Any source byte change gets a different immutable ID. No implicit global data path.

