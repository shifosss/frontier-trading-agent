# Declared execution-cost scenarios

`frontier.execution_costs.get_cost_profile(name, round_trip_bps=40)` returns an
immutable `ExecutionCosts`. `fee(quantity, notional, side)` returns USD costs for
one single-day order; zero quantity and zero notional cost zero. `maximum_quantity`
uses bounded binary search over whole shares and requires notional plus fees to
fit the budget exactly, including minimum fees. The optional sell side uses the
same gross-cost budget definition, not net proceeds. Negative cash allows no shares.
Each profile exposes a detached JSON-serializable `.specification` or `.to_dict()`.

The `proportional` profile preserves the legacy floating-point calculation:
`notional * (round_trip_bps / 20000)` on both sides. The broker profiles add that
same declared friction sensitivity to explicit order charges. This is neither
quoted-spread calibration nor realized execution slippage. Zero bps isolates
the modeled explicit charges; it does not assert costless execution.

Primary tariffs were checked September 19, 2026:

| Profile | Modeled explicit USD order charges |
| --- | --- |
| `wealthsimple_usd` | Zero listed-security commission and no trade FX, assuming existing USD cash and an active USD account. |
| `moomoo_ca_us` | Commission max(0.99, 0.0049 × shares) plus platform max(1.00, 0.005 × shares) for average order price at least USD1; both per-share rates become 0.0005 below USD1. Sell SEC charge max(0.01, 0.0000206 × proceeds). |

Sources: [Wealthsimple legal tariff](https://www.wealthsimple.com/en-ca/legal/fees/trade),
[Moomoo Canadian entity US schedule](https://www.moomoo.com/ca/support/topic10_122),
[SEC 2026 advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2).
Wealthsimple and SEC were retrieved directly. Moomoo was verified through indexed
primary content; the preceding direct retrieval returned HTTP403. The SEC rate is
effective April 4, 2026. Applying these charges to earlier sessions is a **current
tariff counterfactual**, never a historical tariff reconstruction.

Each Moomoo explicit component is independently rounded **up** to a cent using
Decimal arithmetic; proportional friction remains unrounded. This is a declared
conservative scenario convention because carrying-broker rounding is unverified.
For 201 shares at USD10, commission is USD0.99 and platform USD1.01 after rounding;
buy fees are USD2.00 before friction. Sell adds USD0.05 SEC. One order per side per
day is assumed; multiday fills would repeat minima and are not modeled.

Both broker profiles are marked incomplete-cost lower-bound scenarios because
venue, service taxes and unverified regulatory/clearing charges are not resolved.
This label describes missing coverage, not a mathematical bound on actual charges:
the cent-ceiling rule and declared friction can exceed a particular realized fee.
Promotions and the owner's actual tariff are unverified. Funding/withdrawal FX and
variable FX spread are separate exclusions. Wealthsimple's ordinary CAD10 monthly
USD-account subscription plus tax is excluded; waiver eligibility is unknown.
These results cannot establish all-in net profitability.

The existing research engine retains original entry whole-share quantities and
synthetic adjusted exit notionals. Splits/dividends are not reconstructed as an
action-complete share/cash ledger. Consequently per-share charges and the USD1
bracket can be distorted around actions. Cost-aware simulated cash accounting
does not establish broker-realizable share quantities or realized fill fees.

Tests use independently computed tariff examples, strict affordability boundaries,
no-cash and partial-reservation cases, exact legacy fee arithmetic, and exhaustive
quantity enumeration to check binary search and fixed-price monotonicity.

September 26 recheck: the linked Wealthsimple, indexed Moomoo Canadian schedule and
SEC advisory still support these declared components. The profile retains its
September 19 tariff identity; no price-dependent assumptions were retuned.
