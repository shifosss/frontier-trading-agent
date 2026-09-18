# Short-term signal study: frozen research declaration

Declared September 18, 2026, after inspecting the v1 study. Status: **specified; not implemented or evaluated**. This is the next bounded experiment, not a claim of an improved strategy or a new untouched holdout.

## Why this experiment

The completed daily short-hold study `90af4c840aad48f7ab58fba7a682f96a` did not establish useful after-cost activity. Its families mostly describe multiweek/monthly trends. Test a small set of signals explicitly based on two- and five-session moves before changing the cash engine, execution time, selection cadence or risk limits. More complex models are not justified until these simple comparisons have been measured.

[Nagel's Evaporating Liquidity](https://www.nber.org/system/files/working_papers/w17653/w17653.pdf) motivates reversal as a liquidity-provision hypothesis whose behavior depends on market conditions. [Medhat and Schmeling's Short-term Momentum](https://openaccess.city.ac.uk/id/eprint/31278/) reports a monthly return/share-turnover interaction. These motivate competing hypotheses; neither establishes profitability for our delayed, long-only, whole-share daily implementation. Our own dollar-volume ratio is not shares traded divided by historical shares outstanding, and this is not a replication of that paper.

## Frozen inputs and controls

- Reuse completed source run `90af4c840aad48f7ab58fba7a682f96a`, cutoff `2026-09-18T20:43:15.256344+00:00`, and all 8,434 declared instruments / 8,234 usable histories. No source repair, survivor filter based on future completeness, fresh download or universe change is included.
- Expected capture-index SHA256: `85202315acbf06dbdde838c98077bea198177617b0ef88a7584a7a9b1a0d6966`. Retain original raw-file verification and the inherited limitation that the oldest source did not originally freeze its index digest.
- V1 financial source identity: `9fc41227e51c48eeeeb3f64b534dab4fe893650f949070a783aa21e07a8441be`. New implementation receives a distinct version and code identity. Do not overwrite or relabel v1 results.
- Keep stock eligibility: 201 consecutive valid completed stock observations, existing 20-session nominal dollar-volume floors (USD5m / CAD1m), positive ATR and volatility, and existing cash/risk sizing. Do not add an unreported price, sector, market-cap or later-survival screen.
- Preserve daily independent-position management, next-session-close entry, 1/3/5-session holding periods measured from fills, dated settlement, whole shares, five slots, 20% entry limit and 0.5% two-ATR signal sizing.
- Preserve global **WARMUP=200**, **TRAINING=756**, **TESTING=252**, and **TRAINING_BLOCK=252**. First rolling evaluation is index 956; match the saved v1 session dates. The 253-observation maturity of the old intermediate-momentum signal is not a global warmup change.
- Preserve balances 500 / 2,000 / 10,000 / 100,000 in each native currency and 20 / 40 / 100 bps modeled round-trip costs. These are controlled sensitivity assumptions, not calibrated all-in broker costs; see [cost evidence](../../trading-cost-evidence.md).

## Exactly three signal families

Let P[i,t] be the stock's adjusted close and B[t] the adjusted close of SPY for USD or XIU.TO for CAD, on the same exchange session. Define:

- e[i,t] = log(P[i,t] / P[i,t-1]) - log(B[t] / B[t-1]). This is a unit benchmark difference, not estimated beta-adjusted alpha; the traded account remains long-only and unhedged.
- R[i,k,t] = sum of e[i,u] for u=t-k+1 through t.
- sigma[i,t] = sample standard deviation (ddof=1) of the 20 e observations from t-20 through t-1. It deliberately excludes the current signal observation.
- D[i,t] = reconstructed nominal close times reconstructed nominal share volume.
- A[i,t] = mean(D[i,t-4..t]) / mean(D[i,t-24..t-5]). The numerator and denominator windows do not overlap.

| Family ID | Eligibility beyond shared stock rules | Descending rank |
| --- | --- | --- |
| relative_reversal_2 | R[2] < 0 | -R[2] / (sigma × sqrt(2)) |
| relative_reversal_5 | R[5] < 0 | -R[5] / (sigma × sqrt(5)) |
| relative_volume_continuation_5 | R[5] > 0 and A >= 1.5 | R[5] / (sigma × sqrt(5)) |

All inputs end at completed session t and are available before order planning. At least the 22 adjusted stock/benchmark closes from t-21 through t are needed for the residual windows. The stock completeness rule is stricter. Zero/nonfinite sigma or zero/nonfinite prior-volume mean makes that stock ineligible; do not substitute epsilon, infinity, a fabricated quote or a zero return. Use alphabetic symbols for tied ranks. No 200-day market/trend gate, short position, leverage or extra unreported variant is added. The round 1.5 activity ratio is fixed before seeing these results, not optimized. These are relative-return rules: a reversal candidate can have risen in absolute price, and a continuation candidate can have fallen less than its benchmark. No absolute-return gate is implied. sigma × sqrt(k) is only a ranking scale, not a calibrated significance measure. The own-history dollar-volume ratio is partly price-driven.

Entry at t+1 close and exit at t+1+h close deliberately omit the immediate post-signal close-to-close return. Any conclusion is specific to this execution delay; next-open and intraday fills need separate declarations.

A missing required benchmark window must remain distinguishable from a valid day with no candidates. Preserve a required-benchmark-known mask; when a screening decision needs unavailable benchmark input, invalidate the account explicitly. Continue to invalidate missing required entry and held-price observations. Cash-only intervals must not conceal missing signal inputs.

## Declared comparison and acceptance

Three families × three holding periods give **nine hypotheses**, evaluated as **216 fixed portfolios** (two currencies × four balances × three costs × nine) and **24 rolling accounts**, plus matched cash/market references. The rolling selector considers these nine hypotheses only; it is a declared pool comparison against the saved v1 selector over 30 hypotheses. Do not merge pools or expand thresholds after seeing outcomes without another recorded experiment.

Retain the v1 training score and eligibility gates: 100-bps training cost, median of three 252-session block returns minus half maximum drawdown, at least 12 completed trades, at least two positive blocks, drawdown at most 30%, score strictly positive; otherwise cash. Forbid positions whose outcomes cross a training/test boundary. Faster selection and alternative cost models remain separate experiments. Existing v1 files supply the comparison; do not rerun unchanged v1 portfolios without a reproducibility reason.

Report every attempt, missing-data failure, actual trade count and holding time, net expectancy, turnover, exposure, weekly/monthly distribution, drawdown and profit concentration. Show calendar-period behavior instead of treating correlated trades as independent evidence. Any significance claim requires declared calendar-block inference and adjustment for the entire attempted family; this first comparison makes no such claim. A positive fixed row alone does not qualify promotion. Previously inspected history remains reused exploratory data.

## Implementation and verification order

1. Add the feature/ranking lane with a distinct identity, reusing existing market preparation, cash accounting and reporting. Avoid global monkey-patching, copied portfolio loops or a general strategy framework.
2. Test exact synthetic scores, volatility-window exclusion of t, nonoverlapping activity windows, ties, stock/benchmark gaps, zero denominators and future-price mutation invariance. Include relative-versus-absolute sign examples and split-invariant dollar-volume/adjusted-return checks. A signal from t must not fill before t+1 close.
3. Verify unchanged v1 output on a retained deterministic fixture. Test new required-benchmark failure propagation and unchanged holding/settlement/fold rules economically.
4. Run a real saved-data smoke, review correctness and source identities, then execute the declared full study. Retain failures and code/source definitions before viewing results.
5. Separately implement current broker-cost counterfactuals only after fee components/rounding and unmeasured spread assumptions are explicit. Fees affect sizing and settled cash; do not subtract a fee estimate from an already frozen equity curve and call that a valid replay.

Independent design review confirmed the formulas and identified the explicit benchmark-known mask and exact lagged sigma window as necessary. Warmup was checked against source and fixed at 200. No new performance result, software deployment, paper-policy migration or live action occurred during this declaration.
