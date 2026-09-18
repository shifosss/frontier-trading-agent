# Execution-cost evidence for the next short-hold study

Checked September 18, 2026. These are **published fee arithmetic and current-cost scenarios**, not measured execution spreads, this owner's verified tariff, or a historical 2000–2026 fee archive. Existing [account readiness](active-account-readiness.md) and [USD funding](usd-funding-study.md) findings remain in force. No account, subscription, trade or conversion was changed.

## Explicit transaction charges

For Moomoo Financial Canada US stocks/ETFs priced at least US$1, per-side commission is max(0.99, 0.0049 × shares) and platform fee is max(1.00, 0.005 × shares), in USD. Below US$1, each per-share rate is 0.0005 with the same minima. Venue costs and applicable service taxes can be additional. Multiday GTC fills can trigger repeat minima. The US schedule was rechecked through indexed primary-page content; direct retrieval failed, so preserve that access limitation. [Canadian entity US schedule](https://www.moomoo.com/ca/support/topic10_122).

The table assumes one buy and one sell, both at US$10 per share, no promotion, and no price move:

| Position notional | Shares | Round-trip commission | Round-trip platform | Broker-only total | Broker-only bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| US$100 | 10 | 1.98 | 2.00 | **3.98** | **398.0** |
| US$400 | 40 | 1.98 | 2.00 | **3.98** | **99.5** |
| US$2,000 | 200 | 1.98 | 2.00 | **3.98** | **19.9** |

These are examples under the cited tariff, not a universal flat fee. At US$5/share, a US$2,000 position contains 400 shares and costs **US$7.92** round trip in commission/platform fees. Thus the study's 100-bps stress is already below this broker's explicit cost on a US$100 ticket; it is not an all-in worst case. Share price and quantity both matter.

The broker schedule also lists a sell-side SEC fee of max(US$0.01, sale proceeds × 0.0000206). For those three flat US$10 examples it is 0.01 / 0.01 / 0.0412 USD before carrying-broker rounding. The SEC confirms US$20.60/million effective April 4, 2026; this does not establish identical fees throughout older history. [SEC rate advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2).

For Canadian-dollar stocks/ETFs priced at least CAD1, commission is max(0.49, 0.0049 × shares), and platform is max(1.00, 0.01 × shares), in CAD per side. Below CAD1, the per-share rates are 0.0005 and 0.001 respectively with unchanged minima. The minimum two-sided broker charge is CAD2.98. Venue costs and applicable service taxes are additional. [Canada-market schedule](https://www.moomoo.com/ca/support/topic10_123?lang=en-us).

## Funding and recurring account charges

Wealthsimple lists zero commissions for listed US/Canadian securities. Existing USD cash in an active USD account avoids trade-by-trade FX conversion; CAD-funded US purchases/sales incur a 1.5% conversion fee each way plus a variable corporate-rate spread. Below $10,000, a separate cash conversion also costs 1.5%. [Legal tariff](https://www.wealthsimple.com/en-ca/legal/fees/trade).

For a flat USD position N and unchanged base rate, the CAD-funded route's FX-only round-trip loss is N × (1/0.985 - 0.985), approximately 302.28 bps of position notional. This is 2.9775% of initial CAD cash; the denominators differ. Retaining USD between trades removes repeated conversion, but does not erase initial funding, eventual conversion or account costs. CAD600–800 monthly funding incurs CAD9–12 at a one-way 1.5% rate before its rate spread.

An ordinary USD subscription is CAD10/month plus applicable tax after the trial; eligible Premium/Generation clients can opt in without that charge. This user's subscription/tier has not been established. Keep this account-level expense separate from per-trade fees. [USD account terms](https://help.wealthsimple.com/hc/en-ca/articles/4414660979355-Upgrade-to-USD-accounts-for-stock-and-crypto-trading).

Moomoo's separate CAD/USD conversion charge is currently waived, but its quoted preferred exchange rate contains a spread. No fixed spread or free all-in conversion is established; direct retrieval was unavailable and indexed primary content was used. [FX tariff](https://www.moomoo.com/ca/support/topic10_125).

## Modeling decision

Keep the existing 20/40/100-bps grid as an unchanged signal comparison. Label it proportional cost sensitivity, not a broker-ready net-return estimate. Add a separate current-tariff counterfactual with buy/sell fees charged inside the cash ledger and included in affordability; recalculation can change trades and portfolio paths. Preserve price-bracket rules, per-order/per-day minima and separate sell-side regulatory charges.

Actual user promotions, rounding, taxes, venue charges, spread, slippage and FX quotes remain unresolved. Do not silently set these to zero or claim historical bid/ask calibration from daily OHLC. A quoted spread observation must carry timestamp, venue/feed and session status; one feed or after-hours quote does not establish a market-wide historical distribution. No new paid source is assumed.

This follow-up verified tariff arithmetic and specified the next comparison. It did not change the simulator's cost model, reinterpret the completed results, or establish that either broker route is ready for automated execution.
