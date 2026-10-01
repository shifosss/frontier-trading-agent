# Original filing event accounts: execution design

Prepared September 28, 2026 before any event returns. Implements the four-account hypothesis in `../filing-feasibility20260928/strategy-memo.md`; it does not expand the threshold/horizon grid.

## Information and account clocks

Use qualified original 10-Q events filed in 2017–2025, with earlier 2012–2016 filings used only for the eight-observation history. The income treatment admits S >= 1 and orders simultaneous events by decreasing S, then symbol. The structurally eligible unconditional event control uses alphabetical order. Both require the same complete, original eight-event history and nonzero sample standard deviation. No return label participates in feature extraction, entry eligibility or threshold choice.

The conservative availability floor is the later of the acceptance date in New York and filing date, at the end of that date plus one hour. Decide at the first subsequent exchange-session 09:00 ET after this floor; enter at its close and exit five exchange sessions later. Use only prices/ATR/NAV from the preceding completed session and cash known to settle at the entry session's open. Retain decision, source availability, prior-price session, entry and exit separately. Calendar dates are verified against the existing frozen daily cache. Final liquidation can extend through 2026-01-16; the event population is determined by filing date, not by profitable endpoint availability.

## Reuse without changing prior experiments

Reuse the existing `_simulate_daily` engine in successive one-session streaming calls, preserving its position/cash/receivable state. An event ranking occupies the prior-price row as an indexing adapter: it is explicitly a decision at the following session's 09:00, never a claim that the filing was available at the prior close. Existing source modules remain unchanged. Independent design review confirmed the equivalence when these clocks are explicit.

Keep an immutable intent record containing original quantity and fee-inclusive cash reservation. Immediately before the simulated entry, cap quantity by that original reservation. The shared engine may reduce it further for actual settled cash and its 20%-NAV limit. Invalid or missing entry prices must reach the existing invalid-account path, not become zero-quantity abstentions. No reranking, replacement candidate or increased quantity is allowed at fill time. Entry/exit fees, next-opening settlement and scheduled exits remain owned by the shared engine. Sizing remains whole shares, five positions, 20%-NAV allocation and 0.5%-NAV at a known two-ATR distance; this is not a guaranteed loss stop.

Accounts: treatment and control, each at USD2,000, proportional40bps and frozen Moomoo Canada US-equity tariff plus40bps. Reuse adjusted-notional marks/exits and disclose that this does not establish complete cash-dividend/corporate-action accounting or executable close fills. All original cost scenarios remain sensitivity comparisons. Report every path, failed prefix, trade, fee, daily NAV/settled/unsettled balance, weekly/monthly/yearly returns, concentration, exposure and action/source limitations. A profitable event average is not a funded account return.

## Sources and qualification

The original verified daily cache supplies AAPL/MSFT/F/HRL/BANF and SPY. T is absent from its requested USD population, rather than a failed captured history. Do not replace or silently drop the predeclared issuer. A separately declared targeted SIP daily T capture will retain raw and all-adjusted bars, fixed2016-01-04 through2026-09-18 dates, exact asof/feed/source identities and failures. This creates an explicit mixed-provider exploratory price panel; it does not retroactively change any old account. Financial features do not depend on price outcomes.

Before actual accounts: complete source acquisition; qualify exact quarterly facts, eight prior events and conservative clocks; freeze all feature/source/code identities; review price normalization and meaningful synthetic execution tests. Any additional source extraction path is separately declared and preserves original gaps. Run all four accounts together only after those prerequisites. This plan does not itself report strategy results or promotion.
