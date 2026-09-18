# Broad market research

The Strategy lab is the broad research workflow. The Starter scanner retains its original 41-name sample; the existing paper account remains pinned to its 11 eligible US stocks. Research coverage and an execution mandate are separate: new research must not silently change accepted trading decisions.

## Current scope

Discovery on September 18, 2026 saved **5,640 candidates: 4,996 US stocks, 624 Canadian equity candidates, and 20 reference ETFs**. US membership comes from Nasdaq Trader's official Nasdaq and other-listed directories. Canadian candidates come from TMX's August 2026 TSX issuer workbook. Canadian issuer roots can omit share classes, so price-provider symbol/currency validation determines usable histories. TSXV, CSE and Cboe Canada are not covered. Unknown leveraged/inverse ETF classifications are excluded; the existing reference ETF list is explicitly retained.

Sources: [Nasdaq listings](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt), [other US listings](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt), [TMX issuer workbook](https://www.tsx.com/en/resource/571).

Each discovery retains raw source bytes, hashes, dates, membership and exclusions under `data/research/universe/`. This is current listing discovery, not historical membership or delisting-complete data. A broad surviving-stock sample is useful for finding hypotheses but cannot establish unbiased historical investment performance.

The capture worker requests five-year daily histories for every discovered candidate by default, four requests concurrently in batches of 50. It checkpoints verified source records between batches and stops if the provider substantially rate limits requests. The next run resumes stored histories and fetches stale/missing symbols. No paid source or broker order route is used. Data is kept separate from the paper journal and the starter scanner cache.

## Experiments and reasons

| Family | Hypothesis |
| --- | --- |
| Momentum | Persistent 20/60-session relative strength may continue; normalize by volatility. |
| Trend pullback | A short decline within a positive 200-session trend may offer a better entry. |
| Mean reversion | An unusually low 20-session price deviation within a positive long trend may reverse. |
| Breakout | A new high above the prior 55-session close range may persist. |

All four families are tested at 5-, 10- and 20-session horizons: **12 declared hypotheses**, with no search for flattering hidden variants. Each is compared in separate USD and CAD books with simulated native-currency budgets of 500, 2,000, 10,000 and 100,000. Costs are 20, 40 and 100 basis points round trip on entry notional. Fixed commission is zero in this sensitivity model; these are not a verified real broker fee schedule.

Signals require each stock's own 201 consecutive valid sessions and minimum trailing native dollar volume (USD5m/CAD1m). One new listing or missing history does not block the entire market. Names are ranked deterministically. Each cohort uses the first five affordable names, whole shares, a 20% notional cap per name and a 0.5% budget at a two-ATR risk distance. At entry, prices/fees can reduce planned quantities; later prices cannot change signal-time selections. The UI's individual candidate sizes are alternatives, not instructions to buy every row.

Signals use completed daily data. Research entry is the next session close and exit is the declared number of sessions later. Chronological 60/20/20 development, validation and evaluation partitions use fixed exchange-session boundaries; signal-to-exit intervals crossing boundaries are excluded. All partitions become exposed when a run is published. They are not an untouched future holdout.

Results show the mean cash-weighted forward cohort return, matched SPY/XIU benchmark return, excess return, cost sensitivity, invested fraction, counts and exclusions. A missing selected entry/exit or benchmark invalidates that whole paired cohort. Unused cash earns zero. **Independent cohorts are signal research, not a continuous portfolio backtest**: they must not be compounded into CAGR or presented as the paper account's performance. Current-vintage adjusted prices also limit historical whole-share affordability around stock splits. The separate Nautilus engine remains the historical portfolio execution workflow.

## Prospective observations

Each completed fresh study freezes its current selections and quantities before the first future eligible exchange close. A repeated identical plan retains its original timestamp and schedule. Later refreshes evaluate those saved selections without reranking them. Stale signals are not backdated into prospective observations. Changed financial source versions block reinterpretation of old plans.

Snapshots and append-only evaluations live under `artifacts/forward-studies/`. Daily cohorts can overlap and are still research observations, not broker fills. The Strategy lab displays pending, complete and incomplete counts and offers the full observation download. Actual submitted orders and broker fills remain in the Trading desk.

## Operating the workflow

Open **Strategy lab** in the workstation. Its page reads saved progress; it does not launch work on page load. **Run / resume broad research** starts a separate hidden worker. The existing SQLite lock prevents concurrent research work. Progress and errors survive reloads, while the last completed study stays available during a new capture.

Local commands from the project folder:

```powershell
.venv/Scripts/python.exe -m frontier.cli research-status
.venv/Scripts/python.exe -m frontier.cli research-run
.venv/Scripts/python.exe -m frontier.cli research-run --rediscover
```

`--max-symbols N` is an optional reproducible sample for diagnosis; the normal workflow has no such cap. Source identity is frozen before discovery and checked before publication. If development changes research code during a capture, keep the data and resume under the final code; do not label results with a version that did not execute them.

The existing Codex follow-up runs weekdays at **09:35 and 17:35 Toronto time**. It checks paper operation, resumes interrupted research where appropriate, and launches stale research after the close. Listing discovery is refreshed weekly. The host must remain available, and the Codex follow-up needs available account usage. The paper worker runs separately every five minutes. Notifications are limited to meaningful changes or failures.

Research results do not automatically promote a strategy or expand the paper universe. Promotion requires qualified portfolio execution/accounting, dated forward evidence, realistic costs and a versioned migration of the active mandate. Options and live execution remain separate unfinished work.
