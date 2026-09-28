# Return calibration: six controlled account comparisons

**Completed September 28, 2026: calibration reduced forecast error and preserved more capital, but did not establish a useful profitable strategy.** All six accounts completed. Three lost, two never traded, and the sole positive account earned USD10.05 from three trades in early 2016 with no subsequent activity. The study retained 1,180 simulated trade observations. No policy is promoted.

This follows the [18-account conditional-selection study](conditional-strategy-selection-results.md). Its optimistic return forecasts motivated one bounded change: for each model block and return horizon, estimate a calibration-only slope clipped to [0,1] and center the resulting forecast on the calibration outcome mean. The models, fitting samples, candidate population, corrected downside forecasts, whole-share sizing, positive-utility threshold, next-close timing and both cost scenarios remain unchanged. Both fee scenarios consume the same saved forecasts. This isolates attenuation of estimated returns; it does not add a new return-ranking signal.

The comparison covers repeated 1/3/5-session positions over January 4, 2016–September 18, 2026, with USD2,000 starting capital. Its 4,434 eligible US-listed equity instruments include closed-end funds, REITs and depositary shares. Current-member selection, revised source vintages and unresolved corporate actions remain limitations. These dates have been used in earlier research; this is a controlled follow-up, not a fresh untouched holdout. No prior member or trade was deleted to improve results.

## All six results

P is the original proportional 40-bps round-trip sensitivity. M is the frozen Moomoo Canada US-equity tariff scenario plus 40 bps. These are declared comparisons, not verified complete trading costs or evidence against every possible broker route. The original column is the matching dollar-ranked account before slope attenuation.

| Hold | Cost | Original return | New return | Ending USD | Max drawdown | Trades | Mean invested exposure |
|---|:---:|---:|---:|---:|---:|---:|---:|
| 1 | P | -38.92% | -5.67% | 1,886.59 | 9.38% | 812 | 1.017% |
| 1 | M | -12.15% | 0.00% | 2,000.00 | 0.00% | 0 | 0.000% |
| 3 | P | -37.15% | +0.50% | 2,010.05 | 0.19% | 3 | 0.007% |
| 3 | M | -46.20% | 0.00% | 2,000.00 | 0.00% | 0 | 0.000% |
| 5 | P | -26.29% | -8.64% | 1,827.25 | 15.75% | 240 | 3.214% |
| 5 | M | -64.37% | -32.35% | 1,352.94 | 34.40% | 125 | 2.467% |

Ending equity and drawdown improved in every matched comparison, alongside lower exposure and activity. This does not imply better expected profit per trade: the five-session net expectancy deteriorated to -USD0.72/P and -USD5.18/M. The M five-session account still exceeded the owner's 30% drawdown limit.

The three-session/P gain comes entirely from TK, CRDF and BCRX trades entered between January 20 and March 9, 2016. Their net gains were USD5.39, USD4.36 and USD0.30. Average invested exposure over the whole study was only 0.00717%. No trade after March 2016 contributes to that account's result. It is inadequate evidence of a repeatable opportunity set.

The one-session/P account lost 5.89% in 2022 and gained 0.24% in 2023, with zero returns in the other calendar-year periods. The five-session/P account returned +1.39% in 2016, -13.36% in 2022 and +3.995% in 2023, otherwise zero. The five-session/M account lost 34.04% in 2022 and gained 2.56% in 2023, otherwise zero. Flat years reflect inactivity. Two M accounts stayed entirely in cash. Cash interest is not modeled.

Gross P&L on the actual cost-affected paths was +USD98.96/one-session P, +USD10.56/three-session P, -USD43.13/five-session P and -USD63.25/five-session M. Modeled costs were USD212.37, USD0.51, USD129.62 and USD583.81 respectively. Removing those costs arithmetically is not a fee-free account rerun: affordability, ordering and subsequent positions depend on costs.

## What the forecast diagnostic tells us

All 33 return slopes were independently reconstructed from all 259,776 saved calibration rows using Decimal arithmetic. Twelve slopes became zero and one reached the upper bound of one. The latest model block's three return slopes are zero. All 3,133,575 candidate forecasts retain exactly the original candidate membership, raw forecasts and corrected downside bytes; no test outcome fitted a coefficient.

| Hold | Return MSE change versus original calibration | Return MSE change versus fitting-only setup mean | Blocks improving on original |
|---|---:|---:|---:|
| 1 | -0.951% | +0.108% | 11/11 |
| 3 | -2.874% | -0.007% | 10/11 |
| 5 | -5.403% | +3.095% | 10/11 |

Lower error is better. Attenuation improves on the original forecasts, but produces little or no advantage over the simple setup-mean comparator. These are overlapping, row-weighted candidate observations, not account returns or independent samples. Extreme source observations can influence squared error. A positive slope preserves return ordering; the combined return/downside utility order can still change.

## Decision and next strategy work

Retain attenuation as evidence that the previous forecasts justified too much activity, not as a promoted alpha strategy. Do not sweep slopes, thresholds or model families on these same outcomes to force a winner. A different return mechanism has higher research priority now.

The next experiment is a separately declared **intraday opening continuation versus reversal** pilot using actual raw SIP minute observations. Historical capture is running for six previously chosen source/cost-fixture stocks plus SPY, over 2016–2025. The initial seven-name, 2,514-session source request is frozen; the strategy requires completed opening hours, delayed 10:46 entry and a fixed 12:46 exit. Before outcomes, its activity feature was refined from raw share volume to `sum(minute_close × minute_volume)` to reduce cross-session split-unit distortion. The original proposal remains preserved. This six-name pilot is not the final broad universe or an hourly performance claim.

## Reproducibility

Evidence is under `.qualification/conditional-shrinkage20260928`. The frozen definition is `31302c331559629deccc4f324b0efa5edb6cf355fcc6a3827a43229a19631755`, binding 66 code files and 141 source/control inputs. The code archive, original controls, calibration samples, parameters, forecasts, six account ledgers, economic readout and every attempt remain saved. Twenty-two focused tests and two independent scientific reviews passed. The coefficient audit is `independent-coefficient-audit-20260928T211734Z.json`. Independent account reconstruction in `independent-account-audit-20260928T212725Z.json` verified all six paths and 1,180 trade observations with zero audit failures, including seven held-position and four pending-entry model-boundary crossings.

The existing provider split-labelled inventory identified no held-trade action crossing among those 1,180 observations across 481 symbols; see `independent-action-crossings-20260928T213014Z.json`. This bounded lookup does not establish ordinary-dividend completeness, clean training/lookback observations or independently verified issuer continuity. No recorded trade was removed or corrected.

This is isolated historical research. The active eleven-stock paper baseline, its frozen policy and simulated account were not changed.
