# Daily short-hold historical study

Run `90af4c840aad48f7ab58fba7a682f96a`, published 2026-09-18T22:08:08Z after a 14-minute-59-second run. The owner requested that the agent run the study; no manual launch was needed. This report evaluates the daily 1/3/5-session lane and preserves every declared attempt.

## Decision and findings

**The study is complete, but this rule set does not yet justify an active-trading deployment.** The simulator now implements the requested short holding periods; increasing turnover did not create a cost-resistant trading edge.

- **509 of 720 fixed portfolios completed; 211 Canadian paths were invalidated by missing required prices.** All 24 rolling accounts and 48 references completed. Cash-only completion does not qualify the underlying Canadian stock data.
- At **40 bps (0.4%) modeled round-trip cost**, only one of the 168 complete fixed portfolios across both markets had positive total return. That USD100,000 five-session intermediate-momentum/market-trend portfolio returned just **2.23% cumulatively** with **44.03% maximum drawdown**. It fails the owner's drawdown preference and is not a candidate for promotion.
- At **100 bps**, none of the 179 complete fixed portfolios made a profit. At 20 bps, 49 of 162 complete portfolios were profitable, but only 17 also stayed within 30% drawdown. These are exploratory full-period selections, not evidence of a rule chosen in advance.
- **18 of 24 rolling accounts stayed entirely in cash.** The other six, USD2,000 and USD10,000 at each cost, traded only the first test block, October 23, 2003 to October 22, 2004, then selected cash for the remaining 22 blocks. Their small positive cumulative returns at lower modeled costs are not a continuously useful trading strategy. Both accounts lose in their 100-bps evaluation.
- All twelve Canadian rolling accounts selected cash in all 23 blocks. The declared stressed-cost training criteria found no qualifying rule; this is not a finding that Canadian markets lack opportunities.

The next useful iteration should examine **short-term hypotheses and execution costs**, rather than repeat this unchanged grid or loosen its filters solely to force trading. First freeze a small set of reversal/continuation variants designed for 1/3/5-session returns, separate their lookback and holding choices, and test them against the same retained baselines. Calibrate realistic small-account costs from authorized broker/quote evidence independently of which assumption makes a backtest profitable. Keep any faster rule-selection experiment separate so its effect is measurable. Source repairs and hourly-data qualification remain explicit work streams. No strategy or account was promoted by this run.

## Scope and interpretation

The study reused the exact original data cutoff (2026-09-18T20:43:15.256344+00:00), universe and **8,234 usable histories / 28,621,250 daily bars** from `577a24e71a844022b3ac86ca66e32c34`. No new download or issuer-data repair was inserted. Requested history starts in 2000, but individual listings have shorter histories. The 200 failed captures remain recorded. Current-listed membership and current-vintage adjusted prices introduce survivorship and availability limitations.

Ten rule families × three holding periods × four native-currency balances × three round-trip costs × two markets produce **720 fixed portfolios**, plus **24 rolling-selection accounts**. Signals are screened daily; a close signal enters at the next close and each filled position exits after 1, 3 or 5 sessions. These are repeated overnight/daily trades, not five-year stock holdings or an hourly simulation.

The selector uses the preceding 756 sessions at 100-bps costs and fixes the chosen rule for a 252-session evaluation block. Positions still change daily inside each block. Cash is a valid selection when no candidate qualifies. Whole-share sizing, dated settlement and independent cash/position management apply. Nominal sizing and synthetic adjusted-return marks are exploratory, not a complete corporate-action payment ledger.

## All rolling accounts

Each row is a separate simulated account. The US rolling interval is October 23, 2003 through September 18, 2026; the Canadian interval is 2003-10-22 through 2026-09-18. Return is cumulative over that interval; drawdown uses daily equity. Incomplete rows have no profitability aggregate. Trade counts on incomplete rows cover only the observed prefix.

| Market | Start | Round-trip bps | Status | Return | Max drawdown | Trades | Trades / 5 sessions | Mean hold sessions | Profitable months |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| USD | 500 | 20 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| USD | 500 | 40 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| USD | 500 | 100 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| USD | 2,000 | 20 | complete | 1.63% | 6.45% | 225 | 0.20 | 5.00 | 3.62% |
| USD | 2,000 | 40 | complete | 1.55% | 6.25% | 224 | 0.19 | 5.00 | 3.62% |
| USD | 2,000 | 100 | complete | -8.04% | 10.31% | 224 | 0.19 | 5.00 | 1.45% |
| USD | 10,000 | 20 | complete | 3.11% | 5.27% | 224 | 0.19 | 5.00 | 3.62% |
| USD | 10,000 | 40 | complete | 0.64% | 8.10% | 223 | 0.19 | 5.00 | 2.90% |
| USD | 10,000 | 100 | complete | -13.06% | 15.43% | 224 | 0.19 | 5.00 | 1.45% |
| USD | 100,000 | 20 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| USD | 100,000 | 40 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| USD | 100,000 | 100 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 500 | 20 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 500 | 40 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 500 | 100 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 2,000 | 20 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 2,000 | 40 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 2,000 | 100 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 10,000 | 20 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 10,000 | 40 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 10,000 | 100 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 100,000 | 20 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 100,000 | 40 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |
| CAD | 100,000 | 100 | complete | 0.00% | 0.00% | 0 | 0.00 | — | 0.00% |

## Full fixed-rule grid

These are exploratory comparisons after seeing the full historical period, not rules selected using only information available before that period. Positive/under-30% counts are descriptive screens and do not establish deployable edge. No failed path is omitted.

| Market | Start | Round-trip bps | Complete / 30 | Incomplete | Positive return | Positive and ≤30% drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| USD | 500 | 20 | 30 | 0 | 5 | 1 |
| USD | 500 | 40 | 30 | 0 | 0 | 0 |
| USD | 500 | 100 | 30 | 0 | 0 | 0 |
| USD | 2,000 | 20 | 30 | 0 | 6 | 3 |
| USD | 2,000 | 40 | 30 | 0 | 0 | 0 |
| USD | 2,000 | 100 | 30 | 0 | 0 | 0 |
| USD | 10,000 | 20 | 30 | 0 | 6 | 4 |
| USD | 10,000 | 40 | 30 | 0 | 0 | 0 |
| USD | 10,000 | 100 | 30 | 0 | 0 | 0 |
| USD | 100,000 | 20 | 30 | 0 | 5 | 4 |
| USD | 100,000 | 40 | 30 | 0 | 1 | 0 |
| USD | 100,000 | 100 | 30 | 0 | 0 | 0 |
| CAD | 500 | 20 | 10 | 20 | 7 | 2 |
| CAD | 500 | 40 | 14 | 16 | 0 | 0 |
| CAD | 500 | 100 | 15 | 15 | 0 | 0 |
| CAD | 2,000 | 20 | 10 | 20 | 6 | 1 |
| CAD | 2,000 | 40 | 12 | 18 | 0 | 0 |
| CAD | 2,000 | 100 | 13 | 17 | 0 | 0 |
| CAD | 10,000 | 20 | 11 | 19 | 6 | 1 |
| CAD | 10,000 | 40 | 11 | 19 | 0 | 0 |
| CAD | 10,000 | 100 | 17 | 13 | 0 | 0 |
| CAD | 100,000 | 20 | 11 | 19 | 8 | 1 |
| CAD | 100,000 | 40 | 11 | 19 | 0 | 0 |
| CAD | 100,000 | 100 | 14 | 16 | 0 | 0 |

## Missing-data failures

- `WJX.TO:2005-06-15:mark` invalidated 55 declared account paths.
- `ARX.TO:2026-07-20:mark` invalidated 4 declared account paths.
- `CPH.TO:2014-12-24:mark` invalidated 15 declared account paths.
- `AUXX.V:2026-09-17:mark` invalidated 25 declared account paths.
- `PHOS.CN:2026-09-17:mark` invalidated 20 declared account paths.
- `REI-UN.TO:2026-09-17:mark` invalidated 4 declared account paths.
- `LGN.V:2026-09-17:entry` invalidated 25 declared account paths.
- `SPB.TO:2009-01-07:entry` invalidated 23 declared account paths.
- `WJX.TO:2005-06-15:entry` invalidated 22 declared account paths.
- `ARX.TO:2026-07-20:entry` invalidated 6 declared account paths.
- `BIG.V:2026-09-17:mark` invalidated 2 declared account paths.
- `CPH.TO:2014-12-24:entry` invalidated 3 declared account paths.
- `WTE.TO:2012-07-05:entry` invalidated 10 declared account paths.
- `MAXX.CN:2026-09-17:mark` invalidated 5 declared account paths.
- `SPB.TO:2009-01-07:mark` invalidated 1 declared account paths.
- `KMP-UN.TO:2026-09-17:mark` invalidated 1 declared account paths.
- `TECK-B.TO:2026-09-17:mark` invalidated 3 declared account paths.
- `MGA.TO:2006-09-06:entry` invalidated 1 declared account paths.
- `CRON.TO:2018-05-24:entry` invalidated 1 declared account paths.

## Evidence and limits

- Full result and compact summary: `artifacts/historical-lab/runs/90af4c840aad48f7ab58fba7a682f96a/`.
- All result groups and comparison with the old rolling accounts: `artifacts/historical-lab/reports/90af4c840aad48f7ab58fba7a682f96a/analysis.json`.
- Fixed-grid reports retain daily equity and aggregate trade statistics. Rolling accounts retain all completed trades; detailed fixed views can be deterministically replayed.
- Weekly/monthly summaries include cash periods and partial first/last calendar periods. No monthly contributions, fixed commissions, FX conversion costs or taxes are modeled.
- A 30% training drawdown filter does not enforce a future loss cap. These results do not change the frozen paper account or authorize live execution.
- Source reuse validates membership, capture count and individual raw hashes. This older source lacks an originally frozen capture-index digest; the new run explicitly records that limitation and freezes its own index digest.
- See [methodology](historical-research.md), [cadence](trading-cadence.md), [sources](historical-research-sources.md) and [verification](code-quality-review.md).

## Validation and operation

The project suite passed **307 tests**, Ruff and the production TypeScript/Vite build. An independent final audit checked all **792 top-level account/reference rows**, verified that all 211 incomplete accounts retain null profitability aggregates, and independently reconstructed every daily cash, settled-cash and equity value for all 24 rolling accounts. Their **1,344 completed trades** reconcile to raw-source entry/exit prices, fees, next-close entries, exact holding periods and separately computed settlement dates. All 8,234 raw hashes, frozen source/code identities and latest publication pointer agree.

The actual completed interface passed **96 currency/balance/cost comparisons across four viewport widths**, including fixed rows, rolling trades/periods/folds and benchmarks. No page errors, horizontal overflow or mutation occurred. A one-byte ranged request verified the downloadable full report without transferring its entire payload. The earlier running-state checks preserved the previous report and displayed the new mode/stage accurately.

Evidence: `.qualification/historical-source-probes/independent-short-horizon-90af4c840aad48f7ab58fba7a682f96a.json` and `.qualification/historical-ui/short-hold-actual-report.json`. The owner did not need to launch the study manually. Existing weekday 09:35/17:35 Toronto follow-ups now read this report and prioritize the next declared short-term hypotheses and cost qualification. No live account or active paper policy was changed.

## Next declared comparison

The [three-family short-term signal study](superpowers/plans/2026-09-18-short-term-signal-study.md) fixes nine rule/holding-period hypotheses before implementation or outcome inspection. [Current broker cost evidence](trading-cost-evidence.md) separates per-order fee floors from proportional stress assumptions, FX and recurring account charges. These are the next research definition and tariff evidence, not new strategy results.
