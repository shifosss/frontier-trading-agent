# Task 3: Executable research replay and campaigns

## Context and ownership
Read Task2 implementation report, domain/data/store interfaces and docs/engine-qualification.md. The user authorized build/testing; no new spending or broker orders. Own src/frontier/replay.py, src/frontier/metrics.py, src/frontier/campaign.py, src/frontier/reports.py, src/frontier/cli.py, tests/test_replay.py, tests/test_campaign.py, tests/test_cli.py, scripts/import_session_snapshots.py, docs/tasks/03-replay-report.md. May add the CLI entrypoint to pyproject.toml. Coordinate any foundation interface fix with root. No subagents.

## Outcome
One command produces a persisted, inspectable US+Canada research study with genuine Nautilus fills, separate USD/CAD balances, metrics, decisions, and an HTML report. Runs reference immutable datasets and configurations. Known split/dividend events must reject replay (actions not qualified). Incomplete action coverage requires explicit allow_incomplete_actions=true and large visible exploratory/raw-price limitation in summary/report. Never report total return or qualified equity execution for incomplete sources.

## Public interfaces
- run_research(config:RunConfig, data_root:Path, registry:Registry, artifact_root:Path)->dict: register RUNNING before execution; on failure persist FAILED/error and re-raise; successful returns registry record with summary/artifact path.
- replay_dataset(dataset:MarketDataset, config:RunConfig)->dict with summary, equity_curve, decisions, fills, positions, balances, engine_identity.
- run_campaign(dataset_id, data_root, registry, artifact_root, strategy_configs=None)->dict: fixed default cash/passive/trend/reversion suite and small declared lookback variants; full trial counts, per-trial failure state, fixed costs. Deterministic search only; do not call this autonomous LLM research or out-of-sample proof.
- write_report(result:dict,path:Path)->Path renders escaped local standalone HTML. UI and report consume same actual data.
- CLI typer: frontier doctor, demo, datasets, import PATH, run DATASET --strategy ... --lookback ... --allow-incomplete-actions, campaign DATASET, runs, show RUN_ID, serve (serve imported only when web exists). Global --workspace default cwd stores data/datasets, artifacts, data/frontier.sqlite.

## Timing and accounting requirements
Keep all execution/account/order state in Nautilus1.231.0. No custom trading simulator. A small independent oracle in tests is appropriate.
- Features use only as_of data whose event_time and available_at are <=decision time. A daily close-derived signal cannot fill at that close. Schedule orders on the next eligible bar opening event STRICTLY after signal availability, using exchange calendar session opens and hourly starts. End-of-sample pending decisions stay unfilled.
- Bar opens/closes may be converted into explicitly synthetic quote events for the simulator; document the approximation, fixed slippage and absence of actual bid/ask or volume impact. Do not call inferred quotes observed market data.
- Signal history per instrument, warmup explicit, no use of current future open in signal formation. Future data mutation cannot affect earlier signals/fills.
- A single consolidated simulated multi-currency cash account avoids duplicating initial capital across venues. Preserve original listing/venue IDs in outputs and official calendars in timestamps. A narrow mapping to engine simulated venue is acceptable, with rationale. Fees must be in each instrument's native currency; no invented FX trades.
- Whole shares, unlevered, nonnegative cash after fees, no more than20% combined NAV per exposure group when new targets are sized. Existing positions may drift past target; report drift. Aggregate interlisted instruments by exposure_group. Limit buy quantity using actually available quote-currency cash. No automatic FX conversion or cash duplication.
- Strategy passive targets equal capped allocations; cash produces no orders; trend close above trailing mean; reversion negative trailing return (explicit threshold parameter optional). No magical expected-profit percentages.
- Mark with most recent actually observed close, dated FX available as of valuation timestamp. Never use future BoC rate. If no rate before first combined observation, trim start with explicit limitation or fail actionably; never default1.0. FX dollars are reporting only.
- Fees/slippage appear separately; NAV sum independently reconstructible. Initial NAV is pre-trade so first fees and return count. Record final open positions and unfilled intents; no free terminal liquidation.
- Returns, maximum drawdown, volatility/Sharpe only when enough returns, turnover/exposure, fee totals per currency, FX-aware NAV, per-market contribution. Zero variance metrics null, not infinity. Block bootstrap confidence interval with declared seed/block length; descriptive short-sample output, no universal pass/fail. Include cost stress comparisons if campaign budget supports.

## Campaign/evidence
Initial campaign is a transparent exploratory tournament. Freeze the full candidate list, input identity and costs before any evaluation; register all attempts. A simple chronological train/validation split may rank choices only if same state continuity is demonstrated; do not pretend an in-sample tournament is validated walk-forward.
Implement explicit evaluation access recording globally. Display exposed evaluation intervals and raw trial count. Do not call a reused interval untouched. Freeze a candidate artifact (config/data/code identity+frozen_at) with no automatic promotion from a short backtest. Add inspection/replay command proving frozen inputs produce identical financial/decision content excluding UUIDs and runtime timestamps.
A later task can add richer nested walk-forward; report current boundary.

## Real source sample
scripts/import_session_snapshots.py reads the exact files in data/raw (SPY,XIU.TRT,BoC,SPYdividends), makes an import directory and calls import_dataset. Preserve observed provider metadata, inferred historical availability, original date ranges, unknown Canadian action coverage, and source URLs. Include SPY known dividend actions. If no-action replay is wanted create a separately identified June22-Sep17 window, never silently drop action rows within that window. BoC publish time16:30 America/Toronto including DST; include prior available FX by starting the price window after initial rate. Do not fabricate extra history/hourly bars.

## Verification
Run focused tests with actual engine: exact USD/CAD shares,cash,fee/NAV hand calculation; no capital duplication; next-open timing; zero cash negative forbidden;20% group allocation; holiday mismatch; future-mutation invariance including revisions/FX; split/dividend rejection and failed registry persistence; identical replay; all campaign trials retained. CLI demo generates valid report/registry; real snapshot import run visibly exploratory. Run Ruff. Report exact output artifacts/test evidence and remaining gaps.


## Frozen result schema for interface integration

Use these exact result keys (extend with additional evidence fields if needed; do not rename silently):
- schema_version:1, config:RunConfig JSON, dataset:manifest JSON.
- summary:{mode,evidence_label,start,end,base_currency,initial_nav,final_nav,total_return,max_drawdown,annualized_volatility,sharpe,trade_count,turnover,average_exposure,fees:{USD,CAD},limitations:list[str]}. Ratios are fractions, not already multiplied by100. Undefined metrics are null. Include bootstrap_ci as additional object when computed.
- equity_curve:list[{timestamp,nav,cash_usd,cash_cad,positions_value_usd,positions_value_cad,usd_cad,gross_exposure}]. UTC ISO timestamps. Gross exposure is a NAV fraction.
- decisions:list[{instrument_id,decision_time,input_event_time,available_at,signal,target_weight,reason,execution_time:null|string}]. Extra target_quantity/status fields okay.
- fills:list[{instrument_id,timestamp,side,quantity,price,commission,currency,decision_time}]. Native currency numeric price and commission, original listing ID.
- positions:list[{instrument_id,quantity,average_basis,mark,currency}], balances:{USD,CAD}, engine_identity:dict.
- run_research writes artifact_root/run_id/result.json and report.html, registers artifact_path as the run DIRECTORY, returns registry record. get_run returns that record; result data stays persisted in result.json.
- run_campaign returns {campaign_id,dataset_id,created_at,kind:"exploratory_tournament",trial_count,run_ids,ranking,limitations}. Ranking entries include run_id,strategy,status,total_return,sharpe; failed entries retained elsewhere/all runs shown. Save campaign.json under its artifact folder.
- API detail envelope is {record:<registry row>,result:<full result or null if failed>}. POST run returns the same envelope, list runs returns registry rows. Shared group/balance accounting matters more than cosmetics; root must be told immediately if exact contract needs a justified correction.

