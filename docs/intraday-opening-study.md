# Intraday opening continuation versus reversal

**Declared and completed September 28, 2026. All four accounts lost under the declared assumptions; see the [complete results](intraday-opening-results.md).** The specification below preserves the pre-execution choices following the [calibration comparison](calibration-shrinkage-results.md), whose smaller forecast errors did not establish a useful return signal.

## What this tests

Two competing mechanisms can produce a strong opening move. Continued buying may carry a stock higher; a sharp opening decline may instead exhaust selling and reverse. This pilot compares those hypotheses directly using the stock's first-hour return relative to SPY, its position within that hour's range, and unusually high opening dollar activity. These are hypotheses, not explanations already established by the data.

The original proposal and supporting research remain in `.qualification/conditional-selection20260928/next-alpha-research.md`. Before accessing strategy outcomes, the activity measure was refined from share volume to the sum of minute close times minute volume. This reduces distortion from splits changing share units across sessions. It is a turnover proxy, not exact traded dollars or a complete corporate-action solution.

| Choice | Declared rule |
|---|---|
| Stocks | AAPL, MSFT, F, T, HRL, BANF; SPY is a reference only |
| History | 2016 warmup; every actual exchange session in 2017–2025 |
| Observation | All 60 valid stock and SPY minutes from 09:30 to 10:30 New York time |
| Activity filter | Above the median of the stock's immediately preceding 20 complete opening hours; missing sessions are not skipped |
| Continuation | Positive return relative to SPY and close in the top quarter of the opening range |
| Reversal | Negative relative return and close in the bottom quarter |
| Ranking | Largest absolute relative move, alphabetical tie-break |
| Entry / exit | Observed 10:46 / 12:46 minute opens; entry allows 15-minute data delay plus one minute of processing |
| Accounts | Both hypotheses under proportional 40-bps friction and the frozen Moomoo tariff plus 40 bps: four accounts total |
| Capital | USD2,000; whole shares, at most five positions, 20% fee-inclusive entry allocation and settled cash only |
| Sizing | 0.5% of NAV divided by the observed opening range, further limited by cash; this is not a guaranteed loss limit |

All positions are intended to close after two hours, including on early-close sessions. There is no shorting, margin, overnight hold or stop/target sweep. Quantities may decrease at entry to fit their existing cash reservations; future prices cannot cause candidate replacement or larger quantities. Missing a required entry or exit invalidates that account's full-period result and preserves the failure and unresolved position.

## How the comparison will be judged

Preserve every account, loss, abstention and failure. Report net trade dollars, fees, weekly/monthly/yearly returns, stock concentration, signal-to-entry gaps, cash settlement and invested exposure. Intraday NAV uses observed minute marks with explicit stale-price ages where observations are missing. Its sampled drawdown is not a guarantee about losses between observations.

Cash is the funded zero-return reference. A separate descriptive event reference uses the same causal data/activity eligibility without the continuation/reversal sign and location filters. It reports matched and missing endpoints, averaging stocks within each matched date and then dates equally; it is not a funded portfolio benchmark.

The six stocks were chosen previously for source/cost fixtures, independently of this experiment's returns. They are a surviving, purposive feasibility sample, not the eventual universe. Even a positive result would require a separately declared broader sample using dated listing/liquidity rules. The 40-bps scenario is a sensitivity, not a measured universal execution cost; the Moomoo tariff is a current-tariff counterfactual. Neither historical reference opens nor quoted spreads prove achievable fills.

## Source and execution status

The frozen source request spans 2,514 sessions and seven symbols, with 6,836,760 expected regular-session minute slots. Capture preserves raw SIP responses, pagination, session-asof parameters, actual exchange hours, sparse observations, request failures and revisions. The request SHA256 is `092e82a1bfcb7e5fc0990e72c4bed590d295a2f2e619c4d2c0e8aaef03c43447`.

The strategy, source adapter and automatic runner passed 28 focused tests and independent review. Definition `d9c539e611076c9d2a18c56aa2e9f9e0a702411dcb0fcb9f96ea08b7568f3463` freezes 63 implementation/configuration files; request `17bbf306dcc44de9642834f561bd31e258f9d62a150cec168b4d9334022890a0` and `frozen-study-code.zip` are preserved before outcomes.

The automatic study worker was launched at 21:47 UTC on September 28 with `--wait-for-source`. Source capture completed all 2,514 sessions at 22:03 UTC; the worker then qualified every session before automatically running all four accounts. Complete transport still permits legitimately missing minute observations; those were never filled or silently replaced. The runner preserves source constraints and committed account failures rather than treating a partial history as complete or silently retrying failed accounts. This experiment is now complete and must not be restarted unchanged.

Evidence lives under `.qualification/intraday-opening20260928` and `.qualification/intraday-opening-strategy20260928`. The strategy's committed `completed.json` identifies immutable attempt `75d60237bbe6436da358465eb6d3d820` containing all four outcomes and their ledgers. Retain the original capture interruptions, recovery evidence and caches; completion does not erase those attempts.

The active eleven-stock Alpaca paper baseline remains separate. This experiment neither changes that policy nor qualifies a live strategy.
