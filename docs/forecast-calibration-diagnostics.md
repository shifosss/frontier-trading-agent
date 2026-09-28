# Frozen-model forecast diagnostics

Diagnostic date: September 19, 2026. This is exploratory analysis of saved candidate `83d99338fd394e7cad44bdad045b25ad`, not a new untouched test or economic qualification. No model is refitted, no production threshold is changed, and no account or broker is accessed.

September 28 source update: [the AIXI audit](aixi-source-continuity.md) confirmed mixed ADS units behind the +548.11% target. The original tables below remain uncorrected and must not be interpreted as economically clean labels. A separately versioned source correction and affected-model/calibration rerun are required.

## Reconstruction and interpretation

The diagnostic reuses frozen capture `814780d48b4141b9a82a3fb917d1b85a` and its original source `90af4c840aad48f7ab58fba7a682f96a`. The saved payload digest is `8f6baa20861931ca7c52f593d7c8057c8b8e6f5ab59cc0ff07540c9f8942ab7a`. It rebuilds the same bounded USD history, market and causal features, then uses the persisted fitted preprocessing and six model/ensemble forecasts. CPU numerical libraries are capped at two threads.

Fit starts September 13, 2023; its latest outcome is September 16, 2025. Calibration starts September 17, 2025; its latest outcome is September 17, 2026. The signal session is September 18, 2026. All six targets are purged jointly at each boundary. Exact fit and calibration samples contain 47,808 and 23,616 rows, respectively: 96 stocks per date across 498 and 246 sampled dates. Calibration inputs were not used to fit model coefficients or preprocessing, but calibration outcomes already selected ensemble weights. These diagnostics reuse those outcomes again. They must not be called an untouched holdout.

Return labels enter at the next session close and exit 1, 3 or 5 sessions later. Downside is the largest loss at completed closes over that interval; it is neither an intraday excursion nor portfolio drawdown. All metrics use simple returns. Per-date Spearman IC measures cross-sectional ranking rather than market timing. Model error is compared with the persisted training-target mean; calibration-mean and same-date-mean baselines are explicitly ex-post oracles, not executable strategies.

Within-date deciles contain approximately 9–10 sampled stocks. Ascending stable ranks assign decile 10 the highest forecast; ties are deterministically split in sample order, and daily unique-forecast counts are retained. Both predicted-return and production-score rankings are evaluated. Conditional returns and top-minus-bottom spreads are descriptive and do not simulate five slots, cash settlement, overlapping holdings, or realized fills. Equal-date averages give each date the same weight. Exploratory 95% percentile intervals use 2,000 circular moving-block resamples of 10 consecutive dates with seed 1729. They preserve within-date dependence and some temporal overlap, but are not adjusted for the many comparisons and are not qualification evidence.

"Reference feasible" means at least one whole share fits the saved USD 2,000 isolated account's 20% entry cap including the proportional entry fee and the 0.5% NAV/(2 ATR) risk limit, at the signal reference price. This is a membership diagnostic, not proof of an executable order or an actual portfolio allocation. Latest forecasts have no complete future labels and are never assigned realized returns.

## Evidence files

All numerical evidence is retained under `.qualification/forecast-diagnostics/`:

- `run_diagnostics.py`, `attempt.json` and any `failed-attempt-*.json`: procedure, completion or failure evidence.
- `source-and-verification.json`: full verified source identities, raw hashes, normalization, original and current implementation hashes, persisted model warnings, exact reconstruction checks and latest universe rejections.
- `sample-identities.json`: every fit/calibration session-symbol identity and both identity/index digests.
- `reconstructed-samples.npz`: sampled outcomes, calibration predictions, latest predictions, session/symbol membership and reference sizing inputs.
- `per-date-head-metrics.csv`, `metrics-summary.json`: every model, six heads and sampled date; target/prediction means, bias, error, baseline error and rank IC/counts.
- `per-date-deciles.csv`, `decile-summary.json`, `decile-spreads.json`: return/score deciles, conditional returns, feasible membership and equal-date block intervals.
- `score-decomposition.json`, `latest-all-model-forecasts.csv`: before-fee/after-fee/after-risk positive counts and all latest stock/model/horizon forecasts.
- `date-exclusions.csv`, `runtime-warnings.json`: sampling/purging/missing-label counts and runtime warnings.

Current-member survivorship, adjusted-price vintage, unresolved TPX source provenance and uncalibrated execution friction remain limitations. The saved MLP reached its 60-iteration limit. Fixed/minimum broker costs introduced elsewhere are not silently substituted into this saved 40 bps policy diagnostic.

## Findings

The no-entry result is reproducible. The calibrated ensemble assigns **100% weight to Extra Trees at every horizon**. Return-MSE improvements over the training-mean baseline are only 0.0448%, 0.0493% and 0.3554% at 1, 3 and 5 sessions. All three equal-date block intervals for MSE improvement cross zero. Small positive point estimates yield a concentrated model choice, not evidence of reliable economic superiority.

Extra Trees has **zero positive full scores across all 23,616 sampled calibration rows at all three horizons**, and zero among the 2,878 latest stocks. At five sessions the latest mean forecast is +0.09694%, proportional fee deduction is 0.40019%, and half the predicted downside subtracts 1.69167%, giving a mean score of -1.99493%. Maximum score is -1.10625%. In calibration mean predicted downside is 3.65807% versus realized 3.76537%; average downside overestimation does not explain abstention.

Latest five-session comparisons (2,878 eligible stocks):

| Model | Positive gross | Positive after fees | Positive full score | Full score positive and reference feasible |
| --- | ---: | ---: | ---: | ---: |
| Ridge | 1,164 | 347 | 1 | 1 |
| Extra Trees | 2,701 | 230 | 0 | 0 |
| Histogram gradient boosting | 51 | 7 | 1 | 1 |
| Multi-head MLP | 418 | 265 | 26 | 24 |
| Equal ensemble | 479 | 87 | 0 | 0 |
| Calibrated ensemble | 2,701 | 230 | 0 | 0 |

There are 2,431 stocks with at least one reference-feasible share before score filtering; 447 fail the isolated account sizing test. Statistical ranking and the USD 2,000 tradable subset are distinct. Counts are signals, not orders.

Five-session calibration return diagnostics (23,616 rows over 246 dates):

| Model | Predicted mean | Bias vs realized +0.16585% | MSE improvement vs training mean | Daily Spearman IC [95% block interval] |
| --- | ---: | ---: | ---: | --- |
| Ridge | +0.02406% | -0.14179 percentage points | -0.8441% | 0.0406 [0.0147, 0.0662] |
| Extra Trees | +0.17265% | +0.00679 percentage points | +0.3554% | 0.0302 [0.0083, 0.0509] |
| Histogram gradient boosting | +0.22850% | +0.06265 percentage points | -0.5144% | 0.0215 [-0.0059, 0.0476] |
| Multi-head MLP | -0.07414% | -0.24000 percentage points | -13.4099% | 0.0060 [-0.0142, 0.0269] |
| Equal ensemble | +0.08777% | -0.07809 percentage points | -0.9779% | 0.0258 [0.0056, 0.0461] |
| Calibrated ensemble | +0.17265% | +0.00679 percentage points | +0.3554% | 0.0302 [0.0083, 0.0509] |

Downside forecasts carry substantially stronger cross-sectional information. Extra Trees' five-session downside IC is 0.3016 [0.2638, 0.3387] and downside MSE improves 21.68%; histogram boosting improves downside MSE 22.64%. The utility subtracts a meaningful downside quantity from a small expected return. Return-MSE, risk prediction and portfolio utility answer different questions.

The Extra Trees highest predicted-return decile realizes +0.53224% gross and +0.13117% after proportional fees; its gross-return interval is [-0.58566%, +1.69205%]. Mean realized downside is 5.74088%. The lowest decile realizes -1.40034%; top-minus-bottom spread is +1.93258% [0.82473%, 2.99144%]. This includes a weak bottom group and does not prove a profitable long-only top group. Ranking by full score gives top-decile gross +0.15782%, net -0.24249%, and realized downside 1.63229%. The penalty identifies lower-risk names while changing the return distribution. These are sampled conditional outcomes, not portfolio returns.

The MLP's greater activity is not a reason to select it. Its highest predicted-return decile predicts +2.82043% but realizes -0.18049% gross; the saved fit did not converge within 60 iterations. Return forecasts remain unbounded. The largest 1% of five-session squared errors contribute about 48% of Extra Trees error and 51% of MLP error. The sampled AIXI target on August 28, 2026 is +548.11%. This is a source/target audit candidate, not a verified bad price; no row is repaired or removed.

## Reconstruction checks and coverage

The run completed in 266.6 seconds, loading 4,972,463 bounded rows from 5,664 usable USD histories against 5,675 requested instruments. Source identity, full fit/calibration audits and digests, training means, baseline/base-model calibration MSEs and every latest persisted calibrated forecast reproduced exactly. Causal reconstruction modules matched saved hashes. The sole mismatch was daily_policy.py during concurrent cost/state integration; this diagnostic uses frozen 40 bps/half-downside arithmetic and records both identities. No fitting was invoked. No runtime warnings or numerical-check failures occurred; the original MLP warning is retained.

Calibration's 698,440 eligible date-stock rows include 17,108 boundary-purged rows, 12 unavailable-label rows and 657,704 valid but unsampled rows. These diagnostics are not exhaustive historical universe forecasts. Latest universe retains 2,797 rejection records. Fit identity digest: 29d86a176439e4809094cd6fdff5650ae4e6b05e7c9ff2eac92dfad148783690; calibration identity digest: 9016c8e233ae5a098dc379aa4147908e8732639ce27fbc3f5d467a8b79041e68.

Additional retained evidence:

- per-date-score-decomposition.csv and positive-membership-outcomes.json: date-level scores/counts and outcomes conditional on positive forecasts. Selected-date means omit empty dates and are not account returns.
- tail-error-concentration.json and extreme-target-rows.csv: concentration and unmodified extreme identities.
- supplement.py, verification.json and artifact-inventory.json: coverage checks, missing/unperformed tests and artifact hashes. Coverage is 8,856 date/head rows, 88,560 date/decile rows, 4,428 date/score rows and 51,804 latest model/horizon rows.

## Next comparison to declare before execution

The evidence supports testing ranking and portfolio risk, not reducing a production threshold to manufacture trades. The next separate study should freeze this comparison and retain every result:

1. Retain current calibrated score as control, plus cash and the existing benchmark. Keep all base models and equal/calibrated ensembles visible; do not choose a winner from this reused table.
2. Add one separate return-ranking policy: rank forecast return after declared quantity-dependent fees, require positive predicted net return, and keep five slots, 20% position cap and ATR sizing. This is an experimental alternative objective, not modification or promotion of the current half-downside score. Retain downside prediction as a risk diagnostic. Do not search a grid of penalties or cutoffs.
3. Use earlier fit/calibration windows with strict outcome purging and later sequential account replay. Previously studied windows remain exploratory even if later than a particular model's fit. Save full source/model/policy/cost identities, losses and abstentions, turnover, trades, cash exposure, drawdown and date-block uncertainty. Apply declared broker/minimum-fee profiles and whole shares; decile spreads cannot substitute for accounting.
4. Audit extreme targets using a predeclared, model-independent corporate-action rule. Report raw and independently justified corrected series; never exclude rows because they hurt a model. Preserve the MLP warning and compare future training changes only as new declared candidates.
5. Lock the specification before collecting genuinely new completed sessions. This capture has no untouched future test; no current result authorizes activation or claims a profitable strategy.

