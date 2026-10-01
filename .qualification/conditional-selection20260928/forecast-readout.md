# Conditional forecast evidence

The current models predict downside more successfully than returns under this diagnostic. Improving risk forecasts has not established a profitable trading edge. The next strategy decision must wait for all 18 cash-account outcomes; these forecast observations do not measure an investable portfolio.

All 11 completed model blocks were read through their verified manifests: 3,133,575 eligible stock/date rows, with finite raw and corrected predictions for every row and no invalid-feature exclusions. Eight blocks selected boosted trees and three selected Ridge using the declared historical inner validation. No model was selected or fitted for this readout. The status-only operational continuation is retained in the source identities.

| Holding sessions | Corrected return MSE versus setup mean | Corrected downside MSE versus setup mean | Positive predicted proportional utility |
|---|---:|---:|---:|
| 1 | 1.07% worse | 5.60% lower | 180,061 / 3,133,575 = 5.75% |
| 3 | 2.95% worse | 7.44% lower | 398,075 / 3,133,575 = 12.70% |
| 5 | 8.98% worse | 2.36% lower | 436,416 / 3,133,575 = 13.93% |

The return models beat the setup-mean comparator in only 0, 1 and 0 of 11 blocks, respectively. The corresponding downside outputs improve on it in 9, 10 and 10 blocks. The comparator uses only each fitting sample's setup-specific target means, averaging the active setup means for an overlapping candidate. Missing setup means fall back to the pooled fitting mean. This baseline is descriptive; it has not been tested as an account policy.

The MSE figures pool squared errors over matched candidate rows, weighting each block's saved MSE by its matching model/baseline denominator. The denominators are 3,129,439, 3,125,801 and 3,122,002 for the 1-, 3- and 5-session outputs, respectively, for both return and downside. Missing outcomes total 4,136, 7,774 and 11,573; these rows remain in prediction coverage. Most missing outcomes occur near the final capture boundary, with 2, 4 and 6 already missing in the preceding block. This row-weighted output-error comparison is different from the dollar-weighted, equal-date composite loss used to select the model family.

The upper return forecasts remain much too optimistic on average after the mean-bias correction:

| Holding sessions | Mean corrected return forecast in highest calibration interval | Mean later observed gross return | Matched rows |
|---|---:|---:|---:|
| 1 | 0.7311% | 0.0866% | 636,750 |
| 3 | 1.9387% | 0.2514% | 647,946 |
| 5 | 2.9384% | 0.4008% | 649,736 |

For each block and each output, the intervals are defined only by that output's saved calibration prediction quintiles; duplicate edges are collapsed. The table combines the highest interval from each block, weighting its forecast and outcome means by matched rows. Numeric thresholds differ across blocks. This is neither a global test-period quintile nor a promise that exactly 20% of test observations fall in the interval. Every block's exact edges, bin counts, missing outcomes and means are preserved in `forecast-readout.json`.

Positive utility means `0.998 * predicted_return - 0.004 - 0.5 * predicted_downside > 0`, using the same saved corrected forecasts and proportional 40-basis-point round-trip scenario. It comes before whole-share sizing, cash, held-position restrictions, fixed broker fees, reservations and fill checks. It is not a trade count or realized return. The positive shares vary substantially: the 2022-01-04–2023-01-04 block reaches 18.86%, 58.16% and 59.64%; the 2021-01-05–2022-01-03 block has only 0.18%, 0.24% and 0.11%. The latest 2026-01-12–2026-09-18 block has 0.75%, 5.79% and 8.11%. Activity therefore depends strongly on the learned/calibrated period; lowering a fixed qualification threshold would not resolve the demonstrated forecast problem.

## One bounded follow-up design — not executed

If the completed accounts support the diagnosis, compare the existing net-dollar policy with a calibration-only return-shrinkage variant. Reuse all saved raw forecasts, model choices, candidate membership, downside forecasts, cash constraints and fee assumptions. For each block and return horizon, use only its already saved, purged calibration pairs to compute a least-squares slope `s = clip(cov(raw_return, realized_return) / var(raw_return), 0, 1)`, with `s=0` for zero prediction variance. Set the corrected return to `mean(calibration_realized_return) + s * (raw_return - mean(calibration_raw_return))`. Keep corrected downside exactly unchanged. The existing correction is the corresponding slope-one treatment.

This is six new account paths: net-dollar ranking, three holding periods and the same two cost profiles, compared against their already declared original counterparts. Net-dollar ranking is specified because the experiment asks whether forecast magnitude justifies committing scarce cash after fees; it must not be chosen because it happens to win the current run. Fit one slope per block/horizon, shared by both fees, with no threshold sweep, no alternative model refit and no test-outcome fit. Preserve the continuous account and original execution conventions.

This comparison isolates whether upper-tail overconfidence, which a mean-only correction cannot fix, drives economically poor admissions. The zero-to-one bound tests attenuation rather than inventing reversed or amplified trading signals. It cannot create new within-horizon return ordering; a positive slope preserves that ordering. Thus improved MSE alone would not establish a new source of return. Report every path and all-cash outcomes. Failure to improve net expectancy, drawdown and dated stability would refute this as a useful allocation repair and support investigating a separately declared return-ranking target. A risk-only policy would require an additional admission/ranking rule and its own control, so it should not be bundled into this comparison.

## Interpretation limits

Candidate observations and holding periods overlap. These are not independent samples, sized trades, account returns or proof of profitability. All evaluation periods were previously researched; current-member survivorship, revised source vintages and unresolved entity/action/price-unit issues remain. No problematic stock or outcome was removed. Mean-squared errors can be dominated by extreme observations, including source problems; no causal attribution to a particular source defect is made here. Quoted gross outcomes use the existing adjusted-price convention and do not establish actionable closing-auction execution. The 40-basis-point cost is a declared sensitivity, not verified realized slippage.

The readout retains exact input identities. `forecast-readout-audit.json` independently verifies 24 pooled MSE calculations with Decimal and 99 deterministic forecast-utility examples through the expanded entry/exit fee formula. These checks validate derived arithmetic, not source completeness or profitability.
