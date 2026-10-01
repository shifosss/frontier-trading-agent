# Independent account adapter review

Reviewed the frozen earnings specification and the existing daily cash/conditional
utility engine against account adapter SHA
`f1a67cd923188891c93514601fa210b5183d11c60b8d69a64389bdc421351aa7`.
No original-cohort model fits, economic account studies, network requests or orders
were run by this review.

One reproduced identity finding was corrected: a dictionary entry keyed by original
event A could contain a forecast whose internal event ID belonged to another original,
and the account still traded A. The corrected adapter requires matching event ID,
CIK and canonical prepared-row digest before consuming a supplied forecast.
The regression rejects all three independent identity substitutions.

Six independent synthetic tests passed. The twenty recipe/capital/cost combinations
each had four complete synthetic trades. All entry/exit notionals, side-specific fees,
net P&L, reservations, original quantities, five-session holds, historical settlement
dates, daily cash/settled cash/unsettled cash/NAV and weekly returns/target denominators
were reconstructed using separate Decimal arithmetic. The tariff formula is the
declared current-tariff counterfactual, not evidence about historical broker fees.

Additional cases showed that a sixth candidate is not substituted when the first of
five reservations fails its fill-time utility check; unavailable future prices keep
the causal candidate and invalidate the retained account prefix; nonpositive utility
preserves every event and leaves cash idle; and a holding crosses a year boundary
even when the next model fold abstains.

No open material finding remains in the reviewed scope. These synthetic checks do
not validate corporate-action completeness, actual fills or profitability.
Exact implementation and test/log hashes are in `verification.json`.
