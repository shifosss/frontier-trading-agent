# ETF reversal: completed comparison and next priorities

**This fixed reversal strategy is not ready for trading. All eight reversal accounts lost money.** The only positive account among all twelve was the USD10,000 Wealthsimple matched-count control, which did not select the ETFs with the most negative residuals. That result does not qualify the control for promotion either.

Run `42a36d81473b47e89fafe5d8a5ce38ec` completed all twelve paths. These are cumulative whole-account returns for 2017–2025 entries, with a liquidation tail through January 16, 2026; each ordinary position lasted three sessions. The accounts used the predeclared 15-bps round-trip friction allowance plus each broker profile's modeled charges. Costs below include that friction, not solely broker commissions. USD funding/subscription costs, taxes and unverified venue charges remain omitted.

R = residual reversal; T = the same reversal with the SPY trend gate; C = matched-date/count control. Year counts are positive / negative / zero-return calendar years during 2017–2025. Exposure is mean daily invested NAV over the complete account interval, including time after a halt.

| Capital | Broker | Arm | Net return | Max drawdown | Trades | Modeled costs | Exposure | Years + / − / 0 |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| $10,000 | Wealthsimple USD | R | −0.91% | 10.22% | 535 | $1,107.96 | 9.91% | 4 / 5 / 0 |
| $10,000 | Wealthsimple USD | T | −5.24% | 9.25% | 427 | $958.07 | 8.68% | 3 / 6 / 0 |
| $10,000 | Wealthsimple USD | C | +4.15% | 8.92% | 643 | $1,368.41 | 11.92% | 6 / 3 / 0 |
| $10,000 | Moomoo Canada | R | −22.38% | 22.60% | 534 | $3,119.91 | 9.80% | 2 / 7 / 0 |
| $10,000 | Moomoo Canada | T | −21.42% | 21.65% | 427 | $2,586.34 | 8.62% | 1 / 8 / 0 |
| $10,000 | Moomoo Canada | C | −22.18% | 23.80% | 641 | $3,749.34 | 11.71% | 1 / 8 / 0 |
| $2,000 | Wealthsimple USD | R | −2.67% | 8.41% | 415 | $146.92 | 6.64% | 4 / 5 / 0 |
| $2,000 | Wealthsimple USD | T | −5.66% | 7.80% | 339 | $129.25 | 5.88% | 3 / 6 / 0 |
| $2,000 | Wealthsimple USD | C | −1.82% | 7.48% | 486 | $174.38 | 7.83% | 6 / 3 / 0 |
| $2,000 | Moomoo Canada | R | −29.94% | 30.01% | 132 | $571.76 | 2.31% | 0 / 3 / 6 |
| $2,000 | Moomoo Canada | T | −29.99% | 30.02% | 136 | $591.41 | 2.52% | 0 / 4 / 5 |
| $2,000 | Moomoo Canada | C | −30.05% | 30.05% | 147 | $637.91 | 2.61% | 0 / 3 / 6 |

The primary USD10,000 Wealthsimple reversal trailed its control by **5.06 percentage points**, despite paying less total modeled cost. Its executed trades produced $1,016.93 gross P&L, then incurred $1,107.96 of modeled costs. The control produced $1,783.82 gross and retained $415.41 net. These are arithmetic decompositions of the actual cost-aware ledgers, not zero-cost counterfactual accounts. The control filled 643 positions versus 535 and held more exposure, so this is evidence against the declared selection rule, not an exposure-matched causal estimate.

The trend gate did not rescue the hypothesis. Under the lower-cost broker profile it worsened returns at both balances. At USD10,000 Moomoo it lost slightly less than unfiltered reversal, while taking fewer trades and paying $533.57 less modeled cost; this does not establish stronger alpha. Every reversal path still failed to beat cash. These findings reject the economic case for this specific two-session signal, next-close entry and three-session long-only implementation under the tested costs. They do not prove that all ETF reversals, other timing conventions or all residual models lack an edge. No such alternatives have been tested here.

Annual results also lack a robust reversal advantage. USD10,000 Wealthsimple reversal had five losing years; its 2021–2025 compounded gain was only 1.71%, versus 5.35% for the control. Trend reversal lost 1.99% over those recent five years. Both USD10,000 Moomoo reversal versions lost roughly another 11% over 2021–2025. The three USD2,000 Moomoo paths halted on March 19, 2019 (control), June 26, 2019 (reversal), and January 31, 2020 (trend). Their later flat years reflect stopped trading, not demonstrated stability. Actual maximum drawdowns slightly exceeded 30%, as the declared close-based halt permitted.

Contributions are uneven. In the USD10,000 Wealthsimple reversal account, XLP contributed +$416.60 while XLU lost $388.03 and XLF lost $284.98. This does not justify retaining XLP and deleting losing ETFs after the result. In the sole positive control, DIA contributed $382.26, or 92% of its $415.41 net gain after other ETFs offset one another; XLP and XLE together lost $525.85. The strongest single winning trade supplied only about 1.3% of that control's total positive trade P&L, so its concentration is across ETF contributions rather than one exceptional fill. Full contributions for all twelve paths remain in facts.json.

More capital improved implementation, not the signal's underlying justification. Wealthsimple reversal's median entry notional rose from $243 at USD2,000 to $1,464 at USD10,000, and completed trades rose from 415 to 535. Both accounts nevertheless lost. Moomoo's larger accounts avoided the early 30% halt but still lost more than 21%. Lower fee drag and fewer integer-share constraints are useful; neither creates a percentage return edge.

**No account had even one entry-period week reaching 5%, 10% or 15%.** Each denominator is 470 weeks, including idle and losing weeks and the explicitly labelled year-end boundary week; the full saved series has 473 weeks including initialization and the remaining liquidation tail. All weekly medians were zero. The best week anywhere was +3.02%; the worst was −5.88%. The USD2,000 Moomoo reversal arms each had an eighteen-week losing streak. Reusing those same dates across policies does not create independent evidence from twelve accounts, and low exposure must not be turned into a speculative leveraged return target.

The next strategy priority remains the already predeclared 100-issuer earnings-quality experiment: original-vintage income surprises, cash backing, price/volume/market conditions, and the fixed Ridge/HGB comparisons. Its source acquisition is underway; this memo neither changes its criteria nor predicts its results. That experiment adds information absent from this ETF rule and can proceed without requiring a simple baseline to be profitable first.

The parallel options priority is source qualification only: historical as-of chain membership, actual timestamped OPRA bid/ask evidence with known availability, and original multipliers/deliverables/exercise terms. The existing daily option bars do not provide those capabilities. Options must be evaluated as a distinct strategy and execution instrument, not substituted for ETF shares to amplify a losing signal. No new calls, runs, parameter changes or outcome-selected fees were made for this interpretation.

All account hashes were checked against the completed summary. Saved trade P&L, modeled costs and ending-equity changes reconcile within $0.0000001 on each path. This is a descriptive ledger check, not a substitute for the separate full execution audit. The current-member universe, revised prices, synthetic adjusted-notional marks, purposive quote sample and omitted costs continue to limit promotion. The complete per-account facts and annual series are retained in `facts.json`; no path was omitted.
