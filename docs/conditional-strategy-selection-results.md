# Conditional strategy selection — completed results

The 18-account historical study completed on September 28, 2026. **All 18 accounts lost money under their declared costs.** All 11 model blocks produced usable models and 3,133,575 candidate forecasts. Independent reconstruction verified all 38,849 simulated trade observations and every daily cash/NAV path, with zero audit failures. Fourteen accounts exceeded 30% maximum drawdown. No strategy qualifies for promotion.

This was an isolated historical research worker. Its automatic economic analysis has completed; it is not an active experiment, the historical-lab dashboard job or the operating paper policy. The next research priority is correcting demonstrably optimistic return estimates and testing a distinct intraday mechanism, rather than adding more variants of the same weak return signal.

The question is whether learned conditions identify worthwhile reversal/continuation setups, and whether expected net dollars improve on percentage ranking. The [declared design](conditional-strategy-selection-plan.md) compares:

- A static three-setup rank control.
- Conditional forecasts ranked by positive estimated net utility per dollar.
- The same forecasts ranked by positive estimated net utility in dollars at affordable whole-share sizes.

Each policy has 1-, 3- and 5-session holds, USD 2,000 starting capital, and both proportional 40-bps and Moomoo-tariff-plus-40-bps scenarios. Every account screens daily, enters at the next close, respects settled cash and keeps positions through model refits. The learned policies' fill-price utility guard is a simulated contingent-fill convention requiring separate execution qualification.

The frozen capture supplies 5,664 usable histories from 5,675 requested USD instruments. **4,434 US-listed equity instruments are eligible on at least one test date**; the daily candidate count ranges from 470 to 2,351, with median 1,104. The listing parser's broad stock category includes closed-end funds such as EXG/EVV, depositary shares such as KEP and REITs such as AMH. This is not an exclusively operating-company universe or complete historical listing universe. The original membership and all trades remain preserved. The evaluation covers 2,693 sessions from January 4, 2016 to September 18, 2026. Eleven chronological model blocks use earlier fitting and calibration data, strict label purges and 37 causal inputs. Both learned policies and both costs share identical saved forecasts.

The first blocks completed with usable models: Ridge for the first block and boosted trees for the next two. These are fitting/forecast observations, not profitable account results. Two Windows denials of atomic progress-file updates interrupted blocks 3 and 5. Both failed attempts and their model artifacts were preserved. Five completed blocks were verified intact before resuming through `resume_with_persistence.py`, which changes only progress persistence to the project's existing Windows-retrying writer. All 58 original frozen files and scientific parameters remain unchanged; `operational-amendment.json` records the additional runtime identity. Six runner checks and three collision/error-propagation checks passed. While the worker runs, inspect append-only `stdout.log`.

Implementation and independent review passed 533 integrated tests, 54 exact comparisons with the earlier cash engine, and 160 independent quantity/cost-ranking cases. The final account audit independently reconstructed all 18 ledgers, verified all 58 frozen files and matched all 17,293 learned trades to their exact saved forecasts. It checked 315 held-position and 149 pending-entry crossings of model boundaries across all accounts. The seven active paper modules remain unchanged. These checks support accounting and implementation correctness, not corporate-action completeness or actual execution quality.

Evidence under `.qualification/conditional-selection20260928`:

- `request.json`, `definition.json`, `frozen-study-code.zip`: frozen parameters, 58 input/code identities and recoverable code. Definition SHA256: `27bc563d3a65af1328155d917e4ef673fd2f52c892c9d258f33f8d691a7230fc`.
- `candidate-coverage.json`, `preparation/coverage-preflight.json`, `preparation/source-evidence.json`: actual eligibility, chronological coverage and source provenance.
- `blocks/`: model selection, failures, warnings, exact sampled rows, calibration, raw/corrected forecasts and test diagnostics.
- `stdout.log`, `pipeline.jsonl`, `resumes/`: running progress, automatic analysis status and preserved interruption/resumption evidence.
- `operational-amendment.json`, `continuations/`: explicit progress-writer supplement, verified inherited block identities and links to new attempts. Amendment SHA256: `a366297336023eab8be26674cdcb4222a5fba2b263a94ffcd2835bba8195e03b`.
- `accounts/`, `summary.json`, `economic-results.json`, `economic-results.csv`: all 18 completed accounts and their economic comparisons.
- `independent-account-audit-20260928T205806Z.json`: independent full-account reconstruction; earlier partial audit reports remain preserved.
- `universe-scope-review.json` and `.md`: listing/source identities and confirmed examples of closed-end funds, REITs and depositary shares admitted by the broad equity classification.

All variants and failures remain in the denominator. The economic readout checks cash, source prices, independent fee arithmetic, projected utility, actual forecast identity and fee-estimation error; it also reports weekly/monthly/yearly consistency, exposure, concentration and crossings of the existing provider split-labelled inventory. Such crossings are descriptive attribution, not an ordinary-dividend/full-action audit or a corrected account.

The [earlier 54 accounts](strategy-interaction-results.md) all lost after their declared costs, and the [timing diagnostic](strategy-timing-results.md) did not support earlier next-open entry. Those results remain visible. This new study does not change fees or cutoffs to force a winner, and cannot automatically promote a policy to paper or live trading.

## All account outcomes

Returns below cover repeated short trades over the full test interval, not one multiyear stock holding. All accounts began with USD2,000. P means proportional 40-bps round-trip cost sensitivity; M means the frozen Moomoo Canada US-equity tariff scenario **plus** that sensitivity. Neither is a verified all-in execution cost. Actual funding FX, account subscription charges and taxes are outside these scenarios. A cheaper broker route requires its own independently supported cash-ledger comparison; these results do not prove failure at every possible cost.

| Policy | Hold | Cost | Ending USD | Return | Max drawdown | Trades |
|---|---:|:---:|---:|---:|---:|---:|
| Static setup rank | 1 | P | 126.44 | -93.68% | 93.68% | 13,015 |
| Static setup rank | 1 | M | 9.13 | -99.54% | 99.54% | 471 |
| Static setup rank | 3 | P | 680.99 | -65.95% | 69.33% | 4,482 |
| Static setup rank | 3 | M | 9.55 | -99.52% | 99.52% | 429 |
| Static setup rank | 5 | P | 1,606.87 | -19.66% | 39.75% | 2,689 |
| Static setup rank | 5 | M | 9.32 | -99.53% | 99.53% | 470 |
| Conditional percentage rank | 1 | P | 1,327.26 | -33.64% | 35.81% | 4,757 |
| Conditional percentage rank | 1 | M | 1,757.00 | -12.15% | 12.15% | 37 |
| Conditional percentage rank | 3 | P | 1,669.72 | -16.51% | 21.85% | 1,967 |
| Conditional percentage rank | 3 | M | 1,108.93 | -44.55% | 44.58% | 177 |
| Conditional percentage rank | 5 | P | 1,743.12 | -12.84% | 24.79% | 1,589 |
| Conditional percentage rank | 5 | M | 713.59 | -64.32% | 64.32% | 270 |
| Conditional dollar rank | 1 | P | 1,221.69 | -38.92% | 41.43% | 4,526 |
| Conditional dollar rank | 1 | M | 1,757.00 | -12.15% | 12.15% | 37 |
| Conditional dollar rank | 3 | P | 1,257.06 | -37.15% | 37.32% | 1,931 |
| Conditional dollar rank | 3 | M | 1,076.09 | -46.20% | 46.29% | 165 |
| Conditional dollar rank | 5 | P | 1,474.21 | -26.29% | 34.11% | 1,578 |
| Conditional dollar rank | 5 | M | 712.66 | -64.37% | 64.37% | 259 |

Conditional percentage selection preserved more capital than the static control in all six paired comparisons, but it also substantially reduced exposure. Dollar ranking worsened ending equity in five of six comparisons against percentage ranking and tied in the remaining one; all three proportional-cost dollar accounts exceeded the owner's 30% drawdown limit. The forecast's dollar magnitude is not reliable enough to justify allocating more capital to it.

The five-session percentage/P account earned USD133.22 gross on its actual fee-affected path, paid USD390.10 in modeled costs and lost USD256.88 net. Its average invested exposure was only 8.97%. It had 202 positive weeks out of 559, 66 positive months out of 129, and six positive calendar-year periods out of eleven (2026 is partial). Returns in 2023/2024/2025 were -8.35%/-6.39%/-7.01%. The largest five winning trades supplied 7.72% of positive-trade P&L. This is neither consistent profitability nor a fee-free rerun.

The smallest loss overall, -12.15%, belongs to both one-session learned M accounts. They made only 37 trades over the entire interval, averaged 0.167% invested exposure and still lost USD61.78 before USD181.23 of modeled costs. Cash preservation is not an economically useful trading edge. Across all accounts, unchanged cash ended at USD2,000 and therefore beat every strategy; cash interest is not modeled. The long-only SPY reference ended at USD8,299.23/P and USD8,295.08/M, with roughly 31.9% maximum drawdown. That reference supplies opportunity-cost context, not a substitute for the short-hold mandate or an exposure-matched benchmark.

The provider split-labelled inventory identifies 64 held-trade crossings across the 38,849 observations. Their absolute-P&L share is below 0.981% in every account, and none crosses the eight previously flagged known-issue events. This does not verify signal lookbacks, ordinary dividends, unlisted corporate actions or entity continuity. No trade was removed and no corrected account was manufactured. Regime partitions remain descriptive cohorts; a profitable subset cannot be treated as a separately traded account.

## Completed forecast diagnostics

Across the 11 test blocks, the selected models improved downside estimates more reliably than returns. The baseline is the fitting-only mean for each setup; comparisons below use matched, overlapping candidate observations, not sized trades or account returns.

| Hold | Return MSE versus setup mean | Downside MSE versus setup mean | Highest return interval: forecast / observed gross return | Missing outcomes |
|---|---:|---:|---:|---:|
| 1 sessions | +1.07% | -5.60% | 0.731% / 0.087% | 4,136 |
| 3 sessions | +2.95% | -7.44% | 1.939% / 0.251% | 7,774 |
| 5 sessions | +8.98% | -2.36% | 2.938% / 0.401% | 11,573 |

Lower MSE is better. Each block defines its own prediction intervals from calibration data only; the highest-interval means pool matched observations, so they are not one globally fixed cutoff. Return error improves on the simple setup baseline in only 0/1/0 of 11 blocks at the three horizons; downside error improves in 9/10/10. Mean-error calibration has not resolved optimistic upper-tail return forecasts.

Before whole-share affordability, holdings or cash constraints, positive proportional-cost estimated utility occurs in 5.75%, 12.70% and 13.93% of candidate rows at 1/3/5 sessions. Thus the study produces entry candidates; it has not yet established that they deserve trading. Ridge was selected in 3 blocks and boosted trees in 8.

Evidence: `.qualification/conditional-selection20260928/forecast-readout.json`. Revised sources, unresolved action units, current-member survivorship and previously researched test dates remain limitations.

## Strategy decisions and next experiments

1. **Test one calibration repair, not another model-family search.** Reuse the saved models and calibration pairs for a separately declared six-account comparison: attenuate each return head with a calibration-only least-squares slope clipped to [0,1], leave downside forecasts unchanged, and retain the dollar-ranking convention, cash mechanics and both cost scenarios. This isolates whether forecast overconfidence drives poor admissions. It does not create a new return ordering; all-cash outcomes must remain visible. The exact proposed formula is in the [forecast readout](../.qualification/conditional-selection20260928/forecast-readout.md). This follow-up has not run.
2. **Develop a distinct intraday signal.** The [research memo](../.qualification/conditional-selection20260928/next-alpha-research.md) specifies a small continuation-versus-reversal pilot with actual session-aligned minute data, a 09:30–10:30 opening-hour signal, earliest 10:46 entry to respect delayed SIP access, and a fixed 12:46 exit. The six existing source/cost-fixture stocks are a feasibility sample chosen independently of strategy results, not the final universe. Historical source capture and execution-cost qualification must precede performance claims. A broader expansion must use a predeclared listing/liquidity rule, not only names that won the pilot. No intraday capture or backtest has started.
3. **Keep event-driven strategies in the research queue.** Earnings/filing drift offers different information from technical prices, but needs accession-level publication timestamps and as-reported fundamentals before use. The memo compares this with the intraday path and explains why it is not yet an executable historical test.

These are bounded research choices prompted by observed failure mechanisms. Minor code cleanup has lower priority. No unchanged grid will be rerun merely to search for a favorable result; no historical winner will automatically replace the active paper baseline.
