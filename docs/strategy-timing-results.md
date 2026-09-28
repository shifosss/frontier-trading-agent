# Daily strategy timing results

Completed September 28, 2026, 19:44 UTC. **Earlier next-open entry does not rescue these nine tested strategies.** Every policy has a negative mean next-open versus next-close difference when the exit is held constant. Waiting until the next close avoided an adverse entry-day move on average in this frozen sample. Eight of nine exploratory block intervals are entirely negative; trend-conditioned reversal's interval crosses zero. This is an observed price-event result, not portfolio profitability or a claim about every possible intraday strategy.

The [separately declared study](strategy-timing-study-2026-09-28.md) reuses the unchanged signals and cache from the 54-account strategy experiment. No model is refitted and no price is repaired. Signal dates are January 4, 2016–September 10, 2026, with exits through September 18, 2026. Results cover 81 strategy timing/holding cells and nine SPY reference cells.

## Does the next-close delay consume an entry-day edge?

Values below are **log-return basis points**, equally weighting selected stocks within each date and then dates. They are neither account returns nor money earned. A negative difference means entering at the open worsens the same-exit gross outcome. The difference equals `log(raw close / raw open)` on the entry session; subsequent split/dividend adjustment factors cancel algebraically. The 1/3/5-session horizons therefore share this same primary contrast, not three independent confirmations.

| Policy | Mean open-minus-close | Median date | Exploratory 95% block interval | Positive annual means |
| --- | ---: | ---: | --- | ---: |
| Relative reversal 2 | -27.71 | -12.64 | [-39.34, -16.58] | 1/11 |
| Relative reversal 5 | -21.39 | -8.99 | [-32.65, -10.52] | 2/11 |
| Trend pullback | -6.44 | -0.68 | [-11.55, -0.94] | 3/11 |
| Volume continuation 5 | -90.74 | -32.33 | [-112.38, -70.11] | 1/11 |
| Beta-residual reversal 2 | -26.86 | -12.66 | [-39.06, -15.87] | 3/11 |
| Trend-conditioned reversal 5 | -6.35 | -0.48 | [-12.71, +0.09] | 3/11 |
| Compression continuation 5 | -24.96 | -13.92 | [-33.92, -16.23] | 1/11 |
| Equal-percentile blend | -51.10 | -22.51 | [-65.48, -36.71] | 1/11 |
| Volatility-regime selector | -62.80 | -22.25 | [-80.26, -45.91] | 0/11 |
| SPY reference | +1.94 | +5.27 | [-0.73, +4.70] | 8/11 |

Every stock policy has a negative median date as well as a negative mean. The volatility selector's entry-day effect is negative in all 11 calendar-year segments; the other tactics are positive in only one to three. The 2026 segment is partial. SPY's +1.94bps mean is a context reference with different stock selection/risk; its interval includes zero. All intervals reuse previously studied history, overlap across rules/dates and are not multiplicity-adjusted qualification tests.

## Regime and overnight attribution

The frozen selector calls 1,410 dates continuation state (benchmark above its 200-day mean and RV20 no higher than the preceding 252-value median) and 1,277 dates reversal state. These are observable rule states, not proven economic regimes. All nine strategy means are negative in both states:

| Policy | Entry-day mean: continuation state | Entry-day mean: reversal state | Signal-close to next-open gap |
| --- | ---: | ---: | ---: |
| Relative reversal 2 | -28.64 | -26.68 | +0.34 |
| Relative reversal 5 | -19.58 | -23.39 | +1.09 |
| Trend pullback | -3.51 | -9.68 | +6.96 |
| Volume continuation 5 | -98.50 | -82.17 | -90.62 |
| Beta-residual reversal 2 | -27.51 | -26.14 | -0.40 |
| Trend-conditioned reversal 5 | -10.57 | -1.69 | +5.90 |
| Compression continuation 5 | -26.98 | -22.72 | +3.83 |
| Equal-percentile blend | -54.40 | -47.46 | -45.50 |
| Volatility-regime selector | -98.50 | -23.39 | -47.39 |
| SPY reference | +1.67 | +2.24 | +3.67 |

All values are log basis points. Overnight gaps occur before a next-open entry and cannot be credited to an agent deciding after the previous close. Some pullback rules have positive average gaps but negative entry-day moves; the large negative continuation gaps instead suggest substantial weakness before its proposed entry. These are diagnostic observations, not justification to short the names or assume an executable gap-conditioned fill.

## Holding-clock comparison and coverage

All 90 cells remain in `.qualification/strategy-timing20260928/comparison-cells.csv` and `summary.json`. The secondary opening-to-opening comparison does not reveal a broad rescue either. For example, the five-session trend-pullback means are +13.38bps for close-to-close, +6.94bps for next-open to the same close exit, and +9.10bps for opening-to-opening. Trend-conditioned reversal gives +9.75bps, +3.40bps and +4.58bps respectively. These small positive gross price means do not establish net returns after spread, fees, changing position sizes or overlapping cash commitments. Most other groups have negative mean outcomes at every timing and horizon.

There are **120,772 planned stock events**, plus 2,687 SPY reference events, yielding **370,377 event-horizon rows**. All selected required endpoints are available and pass the declared bar checks: zero missing/invalid cells and zero replacements. Four names are absent from the full five-name total for trend-conditioned reversal; compression has 13,296 events over 2,684 active dates and three dates with no selected candidates. The remaining stock policies have 13,435 events over 2,687 active dates. Empty dates were counted rather than credited as profitable zero returns.

The run verifies **3,959 raw-source hashes** and 286,933 required source sessions. The earlier independent schema sample's missing/out-of-range opens remain recorded but do not intersect this selected required-bar set. Passing endpoint checks does not establish correctness of every source observation or issuer action. Current-member survivorship, revised data, known AIXI unit issues and synthetic dividend adjustments remain material; original prices and action-crossing records are preserved.

## Verification and strategy decision

Same-bar adjustment and paired timing identities reconcile within 3.56e-15 log-return units. A separate auditor imports no Frontier financial code: it independently reconstructs all primary means, medians and denominators from saved cohorts/CSV, then verifies a return-independent sample of 30 policy/horizon cells against 28 raw sources using 50-digit Decimal arithmetic. Maximum source-return difference is 8.05e-16; all checks pass. Its initial omitted-zero-counter assumption failed before source sampling; that failed checker is retained and only the auditor was corrected. The timing request, script, cache and outputs remained unchanged.

**Do not migrate these policies to next-open entry on this evidence.** The priority is better stock selection and a stronger underlying return hypothesis, rather than simply advancing execution by one session. Distinct intraday/catalyst strategies remain untested; they require their own causal signals and realistic execution study. Any future timing candidate must earn a separate cash-account comparison with actual open availability, gap-aware sizing and execution costs. This event study models no broker fills, settled cash, portfolio equity, tax or FX and authorizes no paper/live promotion.

Evidence: `.qualification/strategy-timing20260928/` contains the predeclared request, source audit, selected cohorts, every event outcome, all timing summaries, dated `regime-context.json`, independent audit and preserved failures. The completed cache and original 54-account experiment were not changed.
