# Execution cost implementation report

Date: 2026-09-19.

Implemented only src/frontier/execution_costs.py, tests/test_execution_costs.py and docs/execution-cost-model.md, plus this task report. API: immutable ExecutionCosts(name="proportional", round_trip_bps=40), get_cost_profile(name, round_trip_bps=40), fee(quantity,notional,side), maximum_quantity(max_quantity,price,budget,side="buy"), specification property and to_dict().

Proportional fee calculation preserves exact legacy float operation order. Broker profiles add declared half-round-trip friction. Moomoo applies separate commission/platform minima, USD1 bracket, sell SEC fee, and per-component Decimal cent ceilings. The rounding convention is explicitly unverified and declared. Whole-share binary search respects strict gross cash budgets and negative/no cash.

Primary sources verified live using web tool: https://www.moomoo.com/ca/support/topic10_122 (indexed primary Canadian schedule); https://www.wealthsimple.com/en-ca/legal/fees/trade (direct legal page); https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2 (direct). Existing primary review was also read at .qualification/daily-model-bridge/cost-tariff-source-review.json. Moomoo previous direct HTTP403 limitation preserved. No broker connection/action or paid service used.

Metadata explicitly declares current-tariff counterfactual, missing expenses, scenario friction, unknown actual tariff/promotions/rounding, initial/eventual FX and account expense exclusions. Incomplete lower-bound coverage cannot establish net profitability or a formal lower bound on actual charges. Original entry quantities/synthetic adjusted exit notional are not corporate-action-complete; per-share fees and USD1 brackets can differ from actual broker quantities/prices.

Validation: 35 tests passed (0.07s). Independent hand-calculated schedule examples, penny stock and USD1 cases, explicit rounding, zero cash/order, strict boundary/partial reservation, exact proportional arithmetic, profile immutability, malformed inputs, and exhaustive binary-search/maximality/monotonicity checks. Ruff check passed. Initial Ruff line-length finding corrected; no test failures. Tools required escalation because sandbox setup helper failed, not because of an approval rejection. No commits and no old artifact or paper-file mutations.
