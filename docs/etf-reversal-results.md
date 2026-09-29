# ETF residual reversal: declared comparison and results

The twelve-account comparison completed on September 28, 2026 (Toronto), using a fixed 15-basis-point round-trip execution allowance plus the declared broker fees. **All eight reversal-strategy accounts lost money. None of the twelve accounts had a week returning 5%, 10% or 15%.** One matched-count control gained 4.1541% over the entire nine-year entry period. Independent review reconciled all twelve accounts and 4,862 trades. This does not establish a deployable strategy or support the owner's weekly target.

## Hypothesis and comparison

The strategy buys an equity ETF after an unusually weak two-session move relative to SPY. A rolling 60-session regression ends before those two formation sessions; the signal requires a residual score at or below −2. A second arm additionally requires SPY above its 200-session average. These fixed choices test short-term correction after a relative dislocation. They do not measure an options edge, earnings surprise, a calibrated probability or a market-neutral return.

The ten tradable ETFs are DIA, IWM, QQQ, XLE, XLF, XLI, XLK, XLP, XLU and XLV. SPY is the reference, not a tradable candidate in these accounts. A return-blind control selects the same number of eligible ETFs on each unfiltered signal date using a fixed hash order. Actual filled positions and exposure can differ, so this is not an exposure-matched causal estimate. The broader individual-stock universe and separate 100-issuer earnings study remain in place.

Decisions use the completed session's information, become available one minute after its close and fill at the following exchange-session close. Each position normally exits three sessions after entry. Accounts run continuously with no deposits or annual resets: first allowed entry January 3, 2017; last allowed entry December 31, 2025; liquidation/settlement tail through January 16, 2026. Multi-year evaluation measures repeated short trades, not a nine-year unchanged ETF allocation. The user's reserved ETF portfolios are untouched.

Each account has five position slots, a 20% position cap and the existing 0.5%-of-NAV/two-ATR sizing rule. Orders retain their original fee-inclusive cash reservation; execution can reduce whole-share quantity but cannot increase it. USD settlement follows the historical T+3/T+2/T+1 calendar. A first observed 30% drawdown stops future entries and advances remaining exits to the next close. Gaps and costs can take the eventual loss beyond 30%; the record retains that overshoot.

## All twelve accounts

Returns below cover the **entire account period**, after modeled trading costs, before subscription charges, funding/FX, personal taxes and unknown venue charges. They are not weekly returns. WS means the current Wealthsimple USD-account commission scenario; Moomoo means the current Canadian US-stock tariff scenario. Current tariffs are counterfactual assumptions for the historical period, not reconstructed archived charges.

| Arm | Initial USD | Broker scenario | Total return | Maximum drawdown | Trades | Modeled fees USD | Average exposure |
|---|---:|---|---:|---:|---:|---:|---:|
| Reversal | 10,000 | WS | −0.9104% | 10.2209% | 535 | 1,107.96 | 9.91% |
| Reversal | 10,000 | Moomoo | −22.3826% | 22.6034% | 534 | 3,119.91 | 9.80% |
| Reversal | 2,000 | WS | −2.6671% | 8.4135% | 415 | 146.92 | 6.64% |
| Reversal | 2,000 | Moomoo | −29.9434% | 30.0095% | 132 | 571.76 | 2.31% |
| Reversal with trend | 10,000 | WS | −5.2398% | 9.2454% | 427 | 958.07 | 8.68% |
| Reversal with trend | 10,000 | Moomoo | −21.4232% | 21.6500% | 427 | 2,586.34 | 8.62% |
| Reversal with trend | 2,000 | WS | −5.6609% | 7.7970% | 339 | 129.25 | 5.88% |
| Reversal with trend | 2,000 | Moomoo | −29.9930% | 30.0233% | 136 | 591.41 | 2.52% |
| Matched-count control | 10,000 | WS | +4.1541% | 8.9243% | 643 | 1,368.41 | 11.92% |
| Matched-count control | 10,000 | Moomoo | −22.1807% | 23.7953% | 641 | 3,749.34 | 11.71% |
| Matched-count control | 2,000 | WS | −1.8210% | 7.4819% | 486 | 174.38 | 7.83% |
| Matched-count control | 2,000 | Moomoo | −30.0452% | 30.0452% | 147 | 637.91 | 2.61% |

All accounts retain 473 calendar-week observations: one initialization week, 469 entry-only weeks, one week spanning the final entry dates and liquidation tail, and two tail-only weeks. The entry-period denominator is 470, including the boundary week. Every account has zero weeks at all three return targets under either denominator; every median week is zero. The highest weekly return anywhere in the twelve accounts is 3.0217%, in the USD10,000 WS trend arm, which still lost money over the full period. The worst week across all paths is −5.8798%. Idle weeks after a drawdown halt remain in the record.

All three USD2,000 Moomoo accounts reached the drawdown halt: reversal on June 26, 2019; trend on January 31, 2020; control on March 19, 2019. Their lower subsequent activity reflects a stopped account, not improved signal quality. The USD10,000 WS reversal arm had four positive years out of nine; the trend arm had three; the control had six. The full annual, monthly and weekly series, losses, affordability rejections and ETF contributions are retained in the account artifacts.

## What this changes

The declared residual-reversal hypothesis fails its economic test under these execution and sizing assumptions. The trend gate does not rescue it: it loses more in the WS comparison while reducing exposure. The larger account alleviates fixed-fee and whole-share constraints, but neither reversal variant becomes profitable. About 92% of the small positive control's net gain comes from DIA; that is not grounds to promote a hash-selected portfolio or retrospectively prune its symbols. The [all-account interpretation](../.qualification/etf-reversal20260928/strategy/interpretation.md) retains concentration, gross/cost/net reconciliation and yearly comparisons.

The next strategy work is the separately predeclared original-filing earnings/cash-backing study, including Ridge and boosted-tree forecasts, and qualification of historical option quotes and contract records. Increasing leverage or fitting thresholds to repair this losing ETF result would not establish a new edge. No active paper policy is changed and no winner is promoted from this study.

## Costs, verification and limitations

Before account outcomes, 33 fixed ETF quote cells were captured: eleven symbols, the first trading session of 2016/2020/2024, and the final regular-session minute. All cells met the declared 59-second valid-state gate. Independent Decimal calculations verified 220,121 quotes across 23 HTTP200 pages. The largest duration-weighted full spread was 4.266721 bps. The frozen rule, `ceil(maximum spread) + 10 bps`, therefore set 15 bps round trip for every ETF and both brokers. The extra 10 bps is an uncalibrated adverse-execution allowance. Three January dates are a purposive sample; quotes are not fills, closing-auction executions or an upper bound on future costs. See the [cost audit](../.qualification/etf-reversal20260928/costs/independent-verification/report.md).

Wealthsimple subscription/funding costs are separate. At the saved September 28 CAD/USD reference, CAD120 annually would be about USD84.70 before subscription tax—4.23% of USD2,000 or 0.85% of USD10,000. Eligibility for a waiver is unknown. That current illustration is not deducted as a falsely precise historical annual cash series. Broker fee evidence and its assumptions remain in [tariff-recheck.json](../.qualification/etf-reversal20260928/costs/tariff-recheck.json).

Independent pre-run review reconciled 138,875 price/volume values, 27,775 ATR values, 24,630 eligible regression rows, all rankings, 2,525 decision clocks and settlement indices. Seventeen focused signal/preparation/account/report tests passed. A separate review confirmed 473/470 weekly denominators. The 147-member archive, containing the 146 frozen inputs plus the account definition, was verified byte-for-byte.

The [independent account audit](../.qualification/etf-reversal20260928/account-verification/audit-20260929T004447Z.json) passed every account and all 4,862 trades. It rebuilt fees and adjusted marks, daily equity and settled cash, original reservations, whole-share fill caps, ranked planned orders, halt behavior, weekly target denominators and annual compounding without running the account engine again. Arithmetic verification does not resolve the source/execution limitations below.

Prices are revised Yahoo historical data for a fixed current-member ETF sample. Adjusted-price ratios are used for marks and returns, with provider-reported split reconstruction for nominal prices and ATR. This does not model each dividend, actual dividend-payment cash timing, adjusted share deliverable or corporate action as a broker would. No source completeness, point-in-time listing reconstruction or execution qualification is inferred from arithmetic agreement. Historical data have already been used in other research; this is not an untouched holdout.

The [frozen definition](../.qualification/etf-reversal20260928/definition.json) is `c3cf9398debf716a0796f03b863c1c483c9356f5738053704efeb0cee692a6e4`. The single account attempt is `42a36d81473b47e89fafe5d8a5ce38ec`: [all account results](../.qualification/etf-reversal20260928/attempts/42a36d81473b47e89fafe5d8a5ce38ec/summary.json), [full artifact identities](../.qualification/etf-reversal20260928/completed.json), [strategy rationale](../.qualification/etf-reversal20260928/strategy/research-note.md), [source/account review](../.qualification/etf-reversal20260928/source-adapter-review.json), [runner review](../.qualification/etf-reversal20260928/strategy/runner-review.json).
