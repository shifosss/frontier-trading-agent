# Conditional strategy selection — running study

The 18-account historical study started on September 28, 2026. **All 11 model blocks are complete, with 3,133,575 saved candidate forecasts; account comparisons are running.** Final economic results are pending. This is an isolated research worker, not the active paper policy or the historical-lab dashboard job. The launcher automatically runs the economic analysis after the account comparisons finish.

The question is whether learned conditions identify worthwhile reversal/continuation setups, and whether expected net dollars improve on percentage ranking. The [declared design](conditional-strategy-selection-plan.md) compares:

- A static three-setup rank control.
- Conditional forecasts ranked by positive estimated net utility per dollar.
- The same forecasts ranked by positive estimated net utility in dollars at affordable whole-share sizes.

Each policy has 1-, 3- and 5-session holds, USD 2,000 starting capital, and both proportional 40-bps and Moomoo-tariff-plus-40-bps scenarios. Every account screens daily, enters at the next close, respects settled cash and keeps positions through model refits. The learned policies' fill-price utility guard is a simulated contingent-fill convention requiring separate execution qualification.

The frozen capture supplies 5,664 usable histories from 5,675 requested USD instruments. **4,434 stocks are eligible on at least one test date**; the daily candidate count ranges from 470 to 2,351, with median 1,104. This is current-member historical coverage, not a complete historical listing universe. The evaluation covers 2,693 sessions from January 4, 2016 to September 18, 2026. Eleven chronological model blocks use earlier fitting and calibration data, strict label purges and 37 causal inputs. Both learned policies and both costs share identical saved forecasts.

The first blocks completed with usable models: Ridge for the first block and boosted trees for the next two. These are fitting/forecast observations, not profitable account results. Two Windows denials of atomic progress-file updates interrupted blocks 3 and 5. Both failed attempts and their model artifacts were preserved. Five completed blocks were verified intact before resuming through `resume_with_persistence.py`, which changes only progress persistence to the project's existing Windows-retrying writer. All 58 original frozen files and scientific parameters remain unchanged; `operational-amendment.json` records the additional runtime identity. Six runner checks and three collision/error-propagation checks passed. While the worker runs, inspect append-only `stdout.log`.

Implementation and independent review passed 533 integrated tests, 54 exact comparisons with the earlier cash engine, and 160 independent quantity/cost-ranking cases. The seven active paper modules remain unchanged. Validation supports implementation correctness; profitability and source completeness remain unproven.

Evidence under `.qualification/conditional-selection20260928`:

- `request.json`, `definition.json`, `frozen-study-code.zip`: frozen parameters, 58 input/code identities and recoverable code. Definition SHA256: `27bc563d3a65af1328155d917e4ef673fd2f52c892c9d258f33f8d691a7230fc`.
- `candidate-coverage.json`, `preparation/coverage-preflight.json`, `preparation/source-evidence.json`: actual eligibility, chronological coverage and source provenance.
- `blocks/`: model selection, failures, warnings, exact sampled rows, calibration, raw/corrected forecasts and test diagnostics.
- `stdout.log`, `pipeline.jsonl`, `resumes/`: running progress, automatic analysis status and preserved interruption/resumption evidence.
- `operational-amendment.json`, `continuations/`: explicit progress-writer supplement, verified inherited block identities and links to new attempts. Amendment SHA256: `a366297336023eab8be26674cdcb4222a5fba2b263a94ffcd2835bba8195e03b`.
- `accounts/`, `summary.json`, `economic-results.json`, `economic-results.csv`: written as the account comparisons and automatic economic checks complete.

All variants and failures remain in the denominator. The economic readout checks cash, source prices, independent fee arithmetic, projected utility, actual forecast identity and fee-estimation error; it also reports weekly/monthly/yearly consistency, exposure, concentration and crossings of the existing provider split-labelled inventory. Such crossings are descriptive attribution, not an ordinary-dividend/full-action audit or a corrected account.

The [earlier 54 accounts](strategy-interaction-results.md) all lost after their declared costs, and the [timing diagnostic](strategy-timing-results.md) did not support earlier next-open entry. Those results remain visible. This new study does not change fees or cutoffs to force a winner, and cannot automatically promote a policy to paper or live trading.

## Completed forecast diagnostics

Across the 11 test blocks, the selected models improved downside estimates more reliably than returns. The baseline is the fitting-only mean for each setup; comparisons below use matched, overlapping candidate observations, not sized trades or account returns.

| Hold | Return MSE versus setup mean | Downside MSE versus setup mean | Highest return interval: forecast / observed gross return | Missing outcomes |
|---|---:|---:|---:|---:|
| 1 sessions | +1.07% | -5.60% | 0.731% / 0.087% | 4,136 |
| 3 sessions | +2.95% | -7.44% | 1.939% / 0.251% | 7,774 |
| 5 sessions | +8.98% | -2.36% | 2.938% / 0.401% | 11,573 |

Lower MSE is better. Each block defines its own prediction intervals from calibration data only; the highest-interval means pool matched observations, so they are not one globally fixed cutoff. Return error improves on the simple setup baseline in only 0/1/0 of 11 blocks at the three horizons; downside error improves in 9/10/10. Mean-error calibration has not resolved optimistic upper-tail return forecasts.

Before whole-share affordability, holdings or cash constraints, positive proportional-cost estimated utility occurs in 5.75%, 12.70% and 13.93% of candidate rows at 1/3/5 sessions. Thus the study produces entry candidates; it has not yet established that they deserve trading. Ridge was selected in 3 blocks and boosted trees in 8.

Evidence: `.qualification/conditional-selection20260928/forecast-readout.json`. Revised sources, unresolved action units, current-member survivorship and previously researched test dates remain limitations. The full account comparison determines the next controlled strategy experiment.
