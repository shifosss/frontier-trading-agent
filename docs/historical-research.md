# Historical-first strategy development

The Strategy lab now prioritizes long historical tests before relying on new shadow observations. It requests daily history from **January 1, 2000**, subject to each security's actual listing and provider history. The universe has **8,434 current candidates** across major US exchanges, TSX, TSXV, CSE and Cboe Canada; see [coverage](universe-coverage.md). Coverage is broad, but current membership still omits delisted historical firms.

The [first completed job](historical-research-results.md) captured 8,234 usable histories and 28.6 million daily bars. Its negative US results and incomplete Canadian portfolios are retained. A separately audited three-session issuer-data repair recovered 10 Canadian rolling tests, with nine exceeding 30% drawdown; no candidate was promoted.

The [completed daily short-hold study](short-hold-research-results.md) now tests the same histories with daily screening and independent 1/3/5-session positions. It completed 509 fixed portfolios, retained 211 invalidated Canadian attempts, and found mostly cash selections in the rolling accounts. At 40-bps modeled round-trip cost, the only profitable completed fixed portfolio exceeded 30% drawdown. This is rejection evidence for the current rule set, not a profitable system.

## Updated active-trading target

The owner clarified hourly/daily decisions and intraday to roughly one-week holdings. New tests should follow [the trading-cadence design](trading-cadence.md): 1/3/5-session daily trades, a separately qualified hourly lane, continuous position/cash management and trade-level plus weekly/monthly evidence. The existing 5/10/20-session engine described below is a retained baseline; changing only its horizon constants would not implement the new cadence. Multi-year history measures repeated short trades, not a static multi-year stock holding.

## Daily short-hold engine

The default `short_horizon` mode implements daily screening with independent **1-, 3- and 5-session** positions. It reuses the ten existing rule families for a controlled comparison: 30 strategy/horizon combinations, four native-currency balances and three cost assumptions, or 720 fixed portfolios across both markets, plus 24 rolling accounts. Historical test dates span many repeated short trades; position ages begin at actual fills.

A completed close signal fills at the next session close. Each position exits independently after its declared holding interval. The cash ledger distinguishes available and unsettled proceeds using dated US/Canadian T+3, T+2 and T+1 rules. Its banking/exchange holiday intersection is conservative and can delay some settlements beyond real clearing calendars. Unused settled cash remains available while other sales settle. Whole shares, at most five positions, 20% entry allocations and 0.5% two-ATR signal sizing remain unchanged. Orders may shrink at the fill; no margin or same-close signal fills are assumed.

Reports show completed trades, actual holding duration, net expectancy, win/loss statistics, turnover, exposure, inactivity reasons, profit concentration and weekly/monthly returns. Missing required marks invalidate an account and suppress profitability aggregates. Fixed-grid reports retain daily equity and aggregate trade statistics; `evaluate_short_horizon_view` deterministically reconstructs a selected view's detailed trades. Rolling accounts retain every completed trade. Compact UI responses omit large trade/daily arrays while retaining all summary results.

The rolling selector still trains on the prior 756 sessions and holds its chosen rule fixed for the following 252-session block. **Positions continue to change daily within that block.** This version tests the trading-cadence change without also retuning selection frequency. No positions cross fold boundaries; unsettled cash does. This lane is overnight/daily research. Hourly individual-stock performance still needs qualified hourly data.

## Retained legacy baseline

Five fixed families are compared: 20/60-session momentum, trend pullback, short-term mean reversion, 55-session breakout, and intermediate momentum from 252 to 21 sessions ago. Each also has a version requiring the market ETF above its 200-session average. Three holding horizons (5, 10 and 20 sessions) produce **30 declared hypotheses**, with every attempt retained. The intermediate rule requires 253 consecutive observations; other rules require 201. Liquidity thresholds remain USD5m/CAD1m trailing daily turnover.

USD and CAD books stay separate. Starting cash is 500, 2,000, 10,000 or 100,000 in each native currency; modeled round-trip costs are 20, 40 and 100 basis points. All eligible names remain ranking candidates; no top-50 affordability shortcut is used. Fixed dollar commissions, tax, FX and monthly contributions are outside these comparisons.

Each continuous portfolio carries its wealth between nonoverlapping trades. Signal-time ranks and quantities are frozen; entry occurs at the following close, with quantities reduced for gaps and fees if necessary. Up to five whole-share positions use the existing 20% position and 0.5% two-ATR sizing limits. Daily marks include unrealized losses. Sale proceeds wait a conservative three exchange sessions before reuse, including across annual test boundaries. This deliberately uses slower settlement than modern accounts, rather than assuming modern T+1 throughout older history.

The study records total return, annualized return, daily maximum drawdown, yearly results, fees, trades, equity and cash paths, and trade batches. SPY/XIU and cash references use the same starting capital and comparison interval. The UI chart samples month-end equity; drawdowns are calculated from daily values. Any missing required entry or held daily price makes that result incomplete, rather than removing a losing trade. Zero-filled names do not require future holding marks.

## How improvement is evaluated

At each rolling boundary, evaluate all hypotheses using only the previous **756 sessions** at the **100-bps stress cost**. Score each by its median three 252-session block returns minus half its maximum drawdown. Eligibility requires 12 completed position trades, two positive training blocks, maximum training drawdown no greater than 30%, and positive score. Otherwise choose cash. These are declared research criteria, not statistical proof of edge.

The selected rule is frozen for the following 252 sessions. Actual test wealth carries forward, with settlement constraints preserved. Every candidate training score and every test fold remains downloadable. Full-period fixed-rule comparisons are exploratory and must not be used to claim a winner selected without seeing those years. The rolling tests are retrospective designs made today; repeated iterations expose their test periods too.

The user's 30% loss tolerance is displayed against observed test drawdowns. The training filter does not guarantee future drawdowns stay below 30%. This research account model is separate from the paper operator's actual risk halt and execution policy. Its next-close fixed-horizon results do not measure the paper policy, which uses different order types and exits.

## Prices, evidence and limitations

Historical sizing reconstructs nominal OHLC from the provider's reported later splits, with inverse volume adjustment. AAPL January 3, 2000 reconstructs to 111.93750, consistent with Longbridge's 111.938, instead of the approximately 0.99944 split-adjusted quote. Adjusted-close ratios supply synthetic total-return marks. This is not a full share/dividend/payment ledger; reported actions can be incomplete and reinvestment assumptions may differ from a small cash account.

Raw source bytes, SHA256 hashes, URLs, request and capture cutoffs, dated universe membership, split audits, failed captures, source version and experiment definitions are retained. The acquisition stage and evaluation stage have separate definitions. Already-loaded capture code is checked before evaluation; financial source identity is checked before publication. Results cannot be relabeled with newly edited code. Current-vintage prices and inferred close-plus-one-minute availability are not historically observed data vintages.

Existing-access probes and academic/provider references are in [research sources](historical-research-sources.md). A historical delisted-security list was accessible, but complete free delisted daily prices were not established. No new subscription was purchased.

## Run and inspect

Open **Strategy lab → Historical strategy development**. Page loads read status only. **Run short-hold study** starts or reuses a hidden background worker with a SQLite ownership lock. The latest completed report remains visible while a new run works; downloads include full daily equity, rolling trade audits and fixed-grid trade statistics. Select legacy mode explicitly to reproduce the older 5/10/20-session semantics. The checked saved-history option reuses the displayed completed run's exact cutoff, membership and raw histories without acquiring new data.

```powershell
.venv/Scripts/python.exe -m frontier.cli historical-run
.venv/Scripts/python.exe -m frontier.cli historical-status
.venv/Scripts/python.exe -m frontier.cli historical-run --rediscover
.venv/Scripts/python.exe -m frontier.cli historical-run --source-run-id 577a24e71a844022b3ac86ca66e32c34
.venv/Scripts/python.exe -m frontier.cli historical-run --study-mode legacy
```

Research files live under `data/historical/` and `artifacts/historical-lab/`. `--start YYYY-MM-DD` changes the requested history boundary; `--capture-only` acquires data without evaluating or publishing a portfolio report. Source reuse cannot be combined with rediscovery. New evaluation definitions freeze the capture-index hash in addition to per-history raw hashes; older completed sources without that digest carry an explicit weaker-provenance label and are checked against saved membership, history count and raw hashes. Histories resume across restarts. The worker uses four concurrent public requests and stops on substantial rate limiting.

Historical refinement is the current development priority. No new future observation is required to run or improve these tests. Existing paper operations and prospective cohort observations remain a separate baseline; this research does not promote a strategy or place orders automatically. The later execution-validation stage still needs qualified broker costs, corporate actions, security identity and forward operation.


The existing automation checks on weekdays at 09:35 and 17:35 Toronto time. It prioritizes interrupted or newly versioned historical work, refreshes broad listing/history evidence weekly after Friday's close, and continues the separate paper baseline. Routine unchanged checks stay quiet. The host must remain awake and connected; local background work and Codex follow-ups are not cloud services.
