# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

AGENTS.md (imported above) holds the owner mandate, authority limits and current priority. `docs/project-handbook.md` is the full handover: decisions, every experiment and failure, architecture, recovery. `docs/handover/study-catalogue.md` maps each study to its run/attempt IDs, inputs and safe verification. Newer completed results override older dated plans (`docs/superpowers/plans`, `docs/tasks`). No strategy is qualified for promotion and there is no live trading.

## Commands

Python 3.13 only (`>=3.13,<3.14`), uv, Node/npm. The repo is Windows-first: docs use `.venv/Scripts/python.exe`. On Linux/macOS use `.venv/bin/python`.

```bash
uv sync --frozen
npm --prefix frontend ci --cache .cache/npm
npm --prefix frontend run build          # tsc -b && vite build (typecheck alone: run typecheck)

.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m pytest -q            # default suite = tests/ only
.venv/bin/python -m pytest tests/test_replay.py -q
.venv/bin/python -m pytest "tests/test_operator.py::test_name" -q

.venv/bin/python -m frontier.cli --help                       # global --workspace PATH goes before the subcommand
.venv/bin/python -m frontier.cli serve                        # http://127.0.0.1:8765, imports a fictional demo dataset if none exist
npm --prefix frontend run dev                                 # Vite on loopback, proxies /api to :8765
```

`scripts/verify.ps1` (ruff + pytest + frontend build) is the repository's required check. It is PowerShell-only and hardcodes `.venv\Scripts\python.exe` and `npm.cmd`. `Launch Frontier.cmd` → `scripts/start.ps1` starts or reuses the local server.

Baseline in a Linux container (2026-10-01): ruff passes. `pyproject.toml` exempts `short_horizon_study.py` from E501 because completed studies and saved replay journals record its exact bytes, so don't reformat it. pytest: 525 pass, 2 fail. The failures are `tests/test_providers.py::test_timeout_terminates_owned_child[*]`; the Windows path uses job objects, and here the timed-out child PID still answers `os.kill(pid, 0)`. The frontend builds cleanly.

Tests in `tests/` are synthetic and offline: the broker uses `httpx.MockTransport`, `winreg` is monkeypatched, and workspaces live in `tmp_path`. Keep it that way. Verification must never trigger source capture, model refits or a paper order cycle.

Research tests under `.qualification/` are **not** a suite. Never run `pytest .qualification` (preserved older snapshots cause duplicate-module collection errors). Never run `run_*` scripts there either; they need retained raw inputs that a clone does not have. Each study records its focused command in a `verification.json`, e.g. `pytest .qualification/earnings-quality20260928/economic/test_run_study.py -q -p no:cacheprovider`.

Ruff config: py313, line length 100, rules E/F/I.

Open pull requests as ready for review, not as drafts (owner preference).

## Architecture

One package, `src/frontier`. `cli.py` (Typer) and `web.py` (FastAPI) compose it, and `frontend/src` is the React dashboard. `frontend/src/types.ts` mirrors API payloads, so a backend payload change also needs updates to `types.ts`, the relevant panel and `tests/test_web*.py`. `web.py` serves on loopback only: it checks host, origin and fetch-site and has no API docs routes. A non-blocking in-process `_ENGINE_LOCK` returns HTTP 409 when busy.

### Five execution lanes, each with its own timing contract

Don't carry one lane's fill timing into another, and don't treat a horizon constant or polling interval as a cadence change.

| Lane | Modules | Convention |
|---|---|---|
| Strict dataset replay | `domain.py`, `data.py`, `replay.py` (NautilusTrader 1.231.0), `campaign.py`, `store.py` | Signal at the available close, fill at a strictly later eligible open. Native USD/CAD cash. Known splits are rejected. |
| Daily historical cash study | `historical_data.py`, `historical_lab.py`, `short_horizon_study.py` (`daily-short-hold-v1`), `historical_settlement.py` | Screens every session, fills at the next close, independent 1/3/5-session holds, date-specific T+3/T+2/T+1 settlement |
| Saved-model rehearsal | `ensemble_features.py` → `ensemble_models.py` → `model_artifact.py` → `candidate_daily.py` → `candidate_replay.py` | Fitted heads are frozen. The chained SQLite chunk journal is authoritative and restartable; never rebuild state from a report. |
| Actual-minute intraday pilot | `.qualification/intraday-opening-strategy20260928` (not in `src`) | 10:46 ET entry, 12:46 ET exit on real SIP minutes. Completed, all accounts lost. |
| Alpaca PAPER baseline | `operator.py`, `operator_store.py`, `paper_broker.py`, `paper_risk.py`, `swing_policy.py` (+ `scan_data.py`, `sources.py`) | Weekly entry, close-confirmed daily exits, max 20 sessions, frozen 11-stock universe |

Reuse these shared pieces instead of writing parallel engines:
- `daily_policy.py`: forecast score and whole-share cash planner.
- `conditional_policy.py`: fee-aware utility with immutable reservations.
- `execution_costs.py`: cost profiles (proportional, `wealthsimple_usd`, `moomoo_ca_us`).
- `ensemble_models.fit_heads`: Ridge, ExtraTrees, HistGB and MLP, with fit-only preprocessing.
- `historical_settlement.py` and `metrics.py`.

The completed earnings study wraps them through adapters in `.qualification/earnings-quality20260928/{model-inputs,models,accounts,economic}`.

### Data contract

`domain.py` uses strict Pydantic: extra fields are refused and NaN/inf are disallowed. Currencies are USD/CAD, venues are XNAS/XNYS/ARCX/XTSE, and instrument IDs are `SYMBOL.VENUE`. Bars, actions and FX keep separate `event_time` and `available_at` (plus `revision_id`). `data.as_of` filters on both clocks. Session endpoints come from exchange-calendars (XNYS for US, XTSE for Canada). Datasets are content-addressed by SHA under `data/datasets/<sha>/` and rehashed on load. Missing bars are reported, never filled. Hourly bars are never built from daily bars.

### Identities and immutability

- The paper operator's journal binds a normalized-text hash of exactly seven files: `operator.py`, `operator_store.py`, `paper_risk.py`, `paper_broker.py`, `swing_policy.py`, `scan_data.py`, `sources.py`. Editing any of them makes the operator refuse its existing journal until a reviewed migration. Treat those files as frozen.
- `replay.code_identity()` hashes the declared engine modules plus `uv.lock`. Saved models (`model_artifact.py`) check exact bytes, so newline changes can block reload. `.gitattributes` marks `.qualification/**` and `docs/handover/**` as `-text` for that reason.
- The registry's `evaluation_access` table (`store.Registry.record_evaluation_access`) blocks re-evaluating a dataset window globally. A new campaign name does not reset it.
- Runs and attempts are append-only. A failed attempt is kept and a new attempt gets a new ID.

### Runtime state (gitignored, absent from a clone)

`data/frontier.sqlite` (run registry), `data/datasets/`, `artifacts/<run-id>/`, `data/historical` + `artifacts/historical-lab`, `data/research` + `artifacts/research-lab`, `artifacts/daily-candidates/`, `artifacts/candidate-replays/`, `data/operator.sqlite` + `data/operator.lock` (paper journal), `artifacts/paper-operator` and `artifacts/service` (logs/PIDs). The 31.8 GB raw/model corpus is catalogued in `docs/handover/artifact-inventory.csv` but not committed.

### Workers, broker and providers

- The broad (`research_lab.py`) and historical (`historical_lab.py`) labs start detached processes through `processes.py`, each with its own SQLite lock. A saved status JSON is not a process handle: a RUNNING status with a free lock means the run was interrupted.
- `paper_broker.py` hardcodes `https://paper-api.alpaca.markets`. Credentials are `FRONTIER_ALPACA_PAPER_KEY`/`_SECRET`, read from the environment, else the Windows `HKCU\Environment`. Submit transport failures raise `SubmissionUncertain` and are never retried. A fresh clone has no paper journal. Don't run `paper-init`, `paper-cycle` or `paper-watch` as part of development.
- `providers.py` runs an optional sandboxed Codex CLI subprocess that returns typed strategy proposals (never code). It strips `OPENAI_API_KEY`/`CODEX_API_KEY`/`AZURE_OPENAI_API_KEY`.

## Research workflow conventions

- A new study lives in its own `.qualification/<study><YYYYMMDD>/` directory. Declare the definition (hypothesis, sample, costs, pass/fail) and hash it before reading outcomes. Save forecasts before labels, use purged chronological folds, and report every account, variant, failure and idle week.
- When a milestone completes, add its results under `docs/` (`*-results.md`) and update the handbook and README status. Leave older dated plans unchanged.
