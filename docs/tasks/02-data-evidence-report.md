# Task 2 data and evidence foundation report

Completed 2026-09-18. All work is local, engine-independent data/registry work;
no broker orders, paid resources, or global Python installation changes.

## Implemented and verified

- Python 3.13 project, isolated root .venv and committed-input uv.lock.
  Nautilus remains pinned to qualified 1.231.0. Actual resolved versions include
  pydantic 2.13.5, pyarrow 25.0.1, duckdb 1.5.5, numpy 2.5.3, pandas 3.0.6,
  exchange-calendars 4.13.2, pytest 9.1.1 and Ruff 0.16.8.
- Explicit Pydantic source, manifest, instrument, strategy and run contracts;
  extra config fields rejected. Listing venue and quote currency are independent.
  XNAS/XNYS/ARCX map to XNYS sessions, XTSE maps to XTSE.
- Immutable source-byte and canonical-content identities, preserved original
  source files, three Parquet tables, per-file digests, one ingestion timestamp.
  Reimport returns the original identity and original ingestion time.
- Load/list validate source digests and recompute the dataset ID. Manifest source
  metadata, mode, limitations, date bounds and row count must match preserved
  source content. Relabeling synthetic data historical under the same ID fails.
- Prices, volume, OHLC bounds, instruments, explicit timezone, availability and
  revision identity validated. Daily actual-close and hourly endpoints enforced,
  including early closes and final partial hours; missing endpoints are warnings.
- Actual DuckDB reads use parameterized Parquet paths (including quoted path test).
- SQLite commits RUNNING before work, retains failed input/error, prevents terminal
  record overwrites, and tracks overlapping evaluation intervals across campaign names.
- Deterministic offline fictional fixture plus empty real-source import template.
  Fixture: 332 daily bars, 174 fictional FX rows, 100+ sessions per market,
  rising/oscillating/falling regimes, calendar differences and 16:30 Eastern FX.

## Exact public interfaces

In frontier.domain:
- Instrument, DatasetMetadata, DatasetManifest, StrategyConfig, RunConfig.
- MarketDataset(manifest, bars, actions, fx): simple dataclass with pandas frames.
- CALENDAR_BY_VENUE: explicit venue-to-exchange-calendars mapping.
- DatasetManifest.files maps bars.parquet/actions.parquet/fx.parquet to SHA-256;
  source_files maps original CSV/JSON filenames to SHA-256.
  row_count counts bar revisions, start/end describe bar event bounds.
- RunConfig defaults: initial_cash_usd=10000, initial_cash_cad=10000,
  base_currency=CAD, commission_per_order=1, slippage_bps=5, seed=1729,
  allow_incomplete_actions=False, decision_timing=available_close,
  fill_timing=next_eligible_open. Each funding balance is finite and >=0; their
  sum must be >0 (root-approved correction to initial brief).
- Strategy defaults: passive, lookback=20, rebalance_every=5, max_weight=.2,
  long_only=True, whole_shares=True, currency_funding=separate.
- Manifest corporate_actions_status is explicitly required; it is not inferred
  from an empty actions table. USD-denominated TSX listings are accepted.

In frontier.data:
- import_dataset(source_dir: Path, data_root: Path) -> DatasetManifest
- load_dataset(data_root: Path, dataset_id: str) -> MarketDataset
- list_datasets(data_root: Path) -> list[DatasetManifest]
- as_of(bars: DataFrame, decision_time) -> DataFrame: latest revision per
  instrument/event with both event_time and available_at <= decision_time.
- fx_as_of(fx: DataFrame, decision_time) -> Series | None: newest known dated
  FX rate, respecting publication and revised availability.
- session_endpoints(calendar, session, interval) -> DatetimeIndex.

In frontier.fixtures:
- generate_fixture(destination: Path, seed: int = 1729) -> Path.
  Installed-package API for CLI/UI; examples/generate_fixture.py is a thin wrapper.
  No actions.csv is generated because no actions exist in this fictional dataset.
  Source identity and retrieval metadata are fixed for deterministic regeneration.

In frontier.store:
- Registry(path: Path)
- start_run(config: RunConfig, mode: str, code_identity: str) -> str
- finish_run(run_id, summary: dict, artifact_path: str)
- fail_run(run_id, error: str)
- list_runs() -> list[dict]
- get_run(id: str) -> dict
- record_evaluation_access(dataset_id, start, end, campaign_id, purpose) -> list[dict].
  Returns PRIOR overlaps then records current access in the same transaction.
  Intervals are closed, dates mean UTC midnight, full timestamps require timezone.
- Run records: id/status/mode/created_at/completed_at/config/code_identity/
  runtime_identity/summary/artifact_path/error. Status: RUNNING, COMPLETED, FAILED.
  Public records are ordinary JSON-compatible dictionaries. Runtime includes
  Python/platform/package/engine versions. Each operation closes its connection.

## Actual validation

Commands from repository root (PowerShell):

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache/uv'
& 'C:\Users\user\.local\bin\uv.exe' sync --python 'C:\Python313\python.exe'
& '.venv\Scripts\python.exe' -m pytest -q tests/test_data.py tests/test_store.py
& '.venv\Scripts\ruff.exe' check src/frontier/domain.py src/frontier/data.py src/frontier/store.py src/frontier/fixtures.py src/frontier/__init__.py tests/test_data.py tests/test_store.py examples/generate_fixture.py
```

Results: 24 tests passed in 2.52s; Ruff all checks passed.
An actual generated source/import/load smoke run produced dataset
3a7650bbe4030072c81cce72588378f3ccf01f2c9a8f945373f2029bc35ee3d0,
332 bars and 174 FX rows under data/datasets. It is synthetic_fixture.

Tests independently check future revision mutation invariance; illegal timestamp,
currency, OHLC and volume inputs; duplicate revisions; Jul 1/Jul 4 US/Canada
holiday differences; Nov 28 US early close versus Canada's full session; hourly
final partial bars; old versus new FX publication; separate action records;
immutable reimport/new-content IDs; digest corruption; manifest/source provenance
mutation; failed run retention; terminal immutability; cross-campaign overlap.

Normal sandbox shell startup and subsequently apply_patch helper were unavailable
in this session. RTK was already confirmed unavailable by root qualification;
raw PowerShell with require_escalated and explicit local executable paths was
the working fallback. Dependencies/cache remain project-local.

## Boundaries carried forward

- Registry overlap is global across campaign names WITHIN THE SAME immutable
  dataset_id. It does not yet detect economic overlap across different dataset
  vintages, provider IDs or instrument aliases; do not claim cross-vintage secrecy.
- Source timestamps remain as strong or weak as declared provenance. Inferred/
  unknown labels cannot establish point-in-time certification.
- Missing data are warned, never filled; missing FX does not imply conversion1.0.
- Actions are stored and validated, not executed. Engine split/dividend accounting
  and actual hourly market-data/execution qualification remain outside this task.
- Synthetic fixtures establish software behavior only, never observed performance.
- No CLI entry point added by this task; downstream task owns CLI wiring.

