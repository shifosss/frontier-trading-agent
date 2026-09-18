# Task 2: Data and experiment foundation

## Authority and context

The user approved the design and delegated implementation/testing. US and Canadian stocks/ETFs, hours-to-weeks, existing/free only. Read the approved design for financial semantics. Implement direct contracts, with no speculative extension framework. Nautilus 1.231.0 has passed native USD/CAD trade/fee probes but corporate actions are NOT qualified. This task is engine-independent.

## Ownership

Own `pyproject.toml`, `uv.lock`, `src/frontier/domain.py`, `src/frontier/data.py`, `src/frontier/store.py`, `src/frontier/__init__.py`, `tests/test_data.py`, `tests/test_store.py`, `examples/`, `docs/tasks/02-data-evidence-report.md`. Do not edit qualification files or other docs. No subagents. Root handles commit/review. Normal shell startup currently fails; require_escalated works. RTK unavailable in elevated PATH; use explicit C:\Python313\python.exe and C:\Users\user\.local\bin\uv.exe. All packages/cache/env local.

## Package and contracts

- Python >=3.13,<3.14; uv project environment. Pin qualified Nautilus 1.231.0. Dependencies: pydantic2, pyarrow, duckdb, numpy, pandas, exchange-calendars, fastapi, uvicorn, typer, httpx; dev pytest/ruff. Resolve and lock actual available versions. No entry point until CLI exists.
- Pydantic models with strict unknown-field rejection for user configs. `Instrument`: id in SYMBOL.VENUE notation, symbol, venue (XNAS/XNYS/ARCX/XTSE), currency USD/CAD, asset_type stock/etf, exposure_group. Venue maps explicitly to XNYS or XTSE calendars.
- `DatasetManifest`: schema_version, dataset_id (content-derived), name, mode synthetic_fixture/historical, source, source_url, retrieved_at UTC, usage_notes, availability_basis observed/documented/inferred/unknown, adjustment_policy raw only for engine dataset, corporate_actions_status complete/unknown, instruments, interval 1d/1h, start/end, row_count, files and digests, limitations list.
- `StrategyConfig`: family cash/passive/trend/reversion, lookback integer >=2, rebalance_every>=1, max_weight in(0,.2], name. Shared defaults long-only whole shares and separate currency funding.
- `RunConfig`: dataset_id, strategy, initial_cash_usd/cad positive, base_currency CAD/USD, commission_per_order>=0, slippage_bps>=0, seed, allow_incomplete_actions false by default. Cost/default timing explicitly visible. Run mode inherited from dataset.
- `MarketDataset` simple dataclass owns manifest and pandas frames bars/actions/fx. No implicit process-global paths.

## Dataset import and storage

Public `import_dataset(source_dir:Path, data_root:Path)->DatasetManifest`, `load_dataset(data_root:Path,dataset_id:str)->MarketDataset`, `list_datasets(data_root)->list[DatasetManifest]`.

Source directory has `dataset.json` (all metadata except computed manifest fields), `bars.csv`, optional `actions.csv`, `fx.csv`. Keep examples concise with all fields documented. Bars columns: instrument_id,event_time,available_at,open,high,low,close,volume; timestamps UTC-aware. Optional revision_id defaults immutable original. Ingestion timestamp captured once per import. Revisions for same instrument/event allowed only distinct revision_id and available_at; reject duplicate logical revisions. `as_of(bars,decision_time)` returns latest available revision per instrument/event where event_time AND available_at <=decision_time, never future data. Unknown/inferred timestamps keep limitation labels.

Validate finite positive prices, OHLC bounds, nonnegative finite volume, required known instrument, source availability >=event_time, explicit timezone. Validate daily dates and hourly endpoints against real US/Canada calendars; daily bars use session close timestamps, hourly bars may include final partial session bar. Missing sessions are warnings in manifest, holidays must not become synthetic trades. No fill-forward bars. Duplicate content imports return same dataset identity; source byte changes produce new immutable identity; no overwrite. Hash semantic canonical metadata+frames excluding ingestion timestamp so reimport deterministic. Persist Parquet with pyarrow; use DuckDB for analytical reads through file paths (parameterized), demonstrate actual read. Preserve input provenance in manifest; IDs must not allow directory traversal.

Actions columns: instrument_id,event_time,available_at,type(dividend/split),cash_amount,currency,ratio. FX columns: event_time,available_at,usd_cad (CAD per USD),source. Positive dated FX; no same-day future publication leakage. Store actions even though engine qualification isn't complete. Use explicit calendar and invalid row error messages usable by CLI/UI.

## Registry

`Registry(path:Path)` uses SQLite. API `start_run(config:RunConfig,mode:str,code_identity:str)->str`, `finish_run(run_id,summary:dict,artifact_path:str)`, `fail_run(run_id,error:str)`, `list_runs()->list[dict]`, `get_run(id)->dict`, `record_evaluation_access(dataset_id,start,end,campaign_id,purpose)->list[dict]`. Persist RUNNING before work; FAILED retains config/error. Immutable completed records; no silently replacing results. Global overlapping dataset/time accesses returned even if campaign renamed. Serialize public records as ordinary JSON dictionaries. Basic UTC creation/completion times, input config, code/runtime identity. SQLite is single coordinator; no distributed lease framework yet.

## Fixtures and tests

Provide deterministic offline example source for both markets with XNYS vs XTSE calendar differences, USD/CAD FX published16:30 Eastern, and 100+ daily sessions with nontrivial trend/reversion regimes. Clearly named fictional engineering instruments and synthetic_fixture mode; never label synthetic data market observations. Fixture generator produces data with fixed seed and source identity. Also small import template for real user data and actions.

Tests must independently check future revisions cannot affect earlier as_of, timezone and currency errors, calendar holiday discrepancy, immutable import/reimport, changed content new ID, separate actions/FX, DuckDB reads, failed run retained, globally overlapping test access detected. Run actual pytest and Ruff. Report commands/results and interfaces. Do not use fabricated success for any missing integration.
