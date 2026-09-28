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


## September 19: measured historical quote-access fixture

Existing credentials successfully retrieved **12,338 historical SIP quote updates** in two requests, including the single required continuation page. Pagination is complete. The fixture was fixed before retrieval: AAPL, MSFT and F on **November 29, 2024, 12:59:00–13:00:00 ET**, the final minute before the verified early close. It was chosen from the earlier source-calendar test, independently of strategy profits. No account, order, live-price, transfer or subscription endpoint was queried.

The table reports **full quoted spread divided by contemporaneous midpoint**, multiplied by 10,000. Count weighting gives each mechanically valid update equal weight; duration weighting uses its elapsed time until the next update, capped at 13:00. Quantiles use the inverse weighted empirical CDF, without interpolation.

| Stock | Valid / observed quotes | Count-weighted mean / median / p95, bps | Duration-weighted mean / median / p95, bps | Crossed excluded / locked retained |
| --- | ---: | ---: | ---: | ---: |
| AAPL | 7,809 / 7,814 | 0.726 / 0.421 / 1.684 | 0.620 / 0.421 / 1.263 | 5 / 46 |
| MSFT | 4,316 / 4,317 | 1.504 / 1.416 / 2.595 | 1.477 / 1.416 / 2.596 | 1 / 0 |
| F | 207 / 207 | 8.291 / 8.989 / 8.989 | 8.986 / 8.989 / 8.989 | 0 / 16 |

Bid/ask prices and sizes are finite and positive throughout this fixture. Crossed quotes are excluded; zero-spread locked quotes remain visible. All raw condition arrays are `["R"]`, and bid/ask exchange identifiers and tape codes are retained. Sizes stay in the provider's documented round-lot units; no available-share or execution-capacity inference is made. [Quote fields](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data).

Valid observed time is 59.998268 seconds for AAPL, 59.996631 for MSFT and 59.997534 for F. The first 1.48–3.29 milliseconds are uncovered because no pre-window quote was fetched. Crossed intervals remain excluded rather than bridged; equal-timestamp updates give elapsed time only to the last provider record. Requests used explicit `feed=sip`, `asof=2024-11-29`, ascending timestamps and a 10,000-record page limit. The API's ticker `asof` parameter does not create a historical information vintage. [Historical quote contract](https://docs.alpaca.markets/us/reference/stockquotes-1).

These are **quoted spreads in one selected minute**, not measured fills, effective execution spreads, market impact, latency, broker charges or complete round-trip costs. Three stocks on an early-close day are not a representative universe or a historical liquidity distribution. A locked quote is not a guaranteed zero-cost fill, and record counts are not independent statistical observations. Current provider revisions and feed-specific filtering remain relevant. Existing-access success does not establish the owner's subscription tier or unrestricted real-time SIP access.

The concrete next step is a separately predeclared quote-sampling study across liquidity/price groups, dates and session times, followed by broker-specific fees inside the cash ledger. This fixture establishes that observed historical quotes are available; it **does not change the 20/40/100-bps experiment or choose cheaper assumptions to reverse its results**.

Evidence: [fixed request and analysis definition](../.qualification/cost-access20260919/probe-definition.json), [page summary](../.qualification/cost-access20260919/probe-summary.json), [full distributions and validity audit](../.qualification/cost-access20260919/quote-analysis.json), and [offline reproduction script](../.qualification/cost-access20260919/analyze_saved.py).

Raw SHA-256 hashes are `279bfabfd175f89924f3b44dccc68acec54c5e212eb9634d8b6783c47f0236df` for page 1 and `24672da7049153da3aba71aceb5bce0d47150a37074e4d5f39dd81a9cfd8543d` for page 2. The corresponding capture metadata preserves request parameters, response timestamps and raw filenames; credentials are not stored.


## September 19: broader predeclared historical quote sample

The [sample definition](../.qualification/daily-model-bridge/cost-definition.json) was saved before retrieval: six US stocks, first trading sessions of 2016, 2020 and 2024, and 09:30, 12:00 and 15:59 ET one-minute windows. AAPL/MSFT were high-price/activity candidates, F/T lower-price active candidates, and HRL/BANF lower-activity candidates. These are purposive hypotheses, not independently measured volume strata or random selection. No model returns were used and no empty/error cell substitutions were allowed. The installed XNYS calendar independently confirms ordinary 09:30–16:00 sessions on all three dates.

All **54 cells** returned data, with **131,655 quote updates in 17 HTTP-200 pages**, complete pagination and no request errors. Each raw page, full SHA-256, fixed request parameters, capture time and safe response date remain under `.qualification/daily-model-bridge/cost-*`. [Capture summary](../.qualification/daily-model-bridge/cost-capture-summary.json), [all 54 results](../.qualification/daily-model-bridge/cost-all-cells.md), and [full analysis](../.qualification/daily-model-bridge/cost-analysis.json) retain sparse and wide-spread observations.

| Symbol | Observed time-weighted midpoint range, USD | Updates per minute range | Range of per-cell duration-weighted mean full spread, bps |
| --- | ---: | ---: | ---: |
| AAPL | 102.15–300.44 | 742–19,906 | 0.552–4.108 |
| MSFT | 53.78–374.89 | 1,322–13,724 | 0.681–2.500 |
| F | 9.25–13.99 | 36–2,407 | 7.148–10.817 |
| T | 16.85–39.17 | 72–3,183 | 2.572–6.921 |
| HRL | 32.05–78.19 | 72–1,511 | 1.893–26.293 |
| BANF | 56.49–97.99 | 4–152 | 11.396–420.968 |

The full 3,240 sampled symbol-seconds reconcile to **3,184.489061 valid**, **0.006969 crossed**, **0 other-invalid**, and **55.503969 uncovered** seconds. BANF contributes 50.948319 uncovered seconds. Uncovered means no initial in-window quote; it is not a diagnosed provider outage. Valid quote states persist until the next observed update or window end, without a stale timeout. The longest state is 59.5 seconds (BANF, 2016 opening). Duration weighting therefore does not independently prove continuing executable liquidity in sparse cells. Quote-update activity is not traded-volume liquidity.

The analyzer preserves raw conditions/exchanges/tapes, excludes nonpositive/nonfinite prices or sizes and crossed quotes, retains locked quotes, uses `[start,end)` and last-record precedence for identical timestamps, and never bridges crossed intervals. All 54 time-weighted means were independently recomputed with Decimal arithmetic; synthetic checks cover leading gaps, empty cells, crossed/locked states, invalid sizes, equal timestamps and terminal exclusion. [Verification](../.qualification/daily-model-bridge/cost-verification.json).

This broader fixture demonstrates price/activity/time variation; it remains six selected surviving names on three January sessions, with no Canadian listings, penny stocks, delisted universe, seasonality coverage or effective-fill observations. Spreads are full quoted spreads relative to midpoint, not broker execution costs or round-trip slippage calibration. Today's provider vintage and symbol mapping are not point-in-time data vintages. In particular, BANF's wide opening quotes are retained rather than discarded as inconvenient. **The existing 20/40/100-bps scenarios and all frozen strategy results remain unchanged.**

## USD2,000 / five-slot current-fee arithmetic

The [current primary tariff recheck](../.qualification/daily-model-bridge/cost-tariff-source-review.json) agrees with the fees above. Moomoo's direct page again returned 403; its indexed Canadian-entity schedule supplied the current figures. Wealthsimple's legal fee page was retrieved directly. Neither establishes the user's actual promotions or a historical tariff archive. [Moomoo Canada](https://www.moomoo.com/ca/support/topic10_122), [Wealthsimple legal schedule](https://www.wealthsimple.com/en-ca/legal/fees/trade).

With USD2,000 NAV and five slots, each slot permits at most USD400 **including its buy fee**. This arithmetic assumes unchanged buy/sell prices, one order each way and five distinct stocks at the same example price. It applies only the published commission/platform formula when sizing; venue fees, taxes, spreads, price moves and rounding are unresolved, so it is not an executable buying-power guarantee.

| Price USD | Whole shares per slot | Notional per slot USD | Buy fee USD | Broker round trip USD | Broker round trip bps of position | Cash for five entries USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 396 | 396 | 3.9204 | 7.8408 | 198.00 | 1,999.6020 |
| 5 | 79 | 395 | 1.99 | 3.98 | 100.76 | 1,984.95 |
| 10 | 39 | 390 | 1.99 | 3.98 | 102.05 | 1,959.95 |
| 50 | 7 | 350 | 1.99 | 3.98 | 113.71 | 1,759.95 |
| 100 | 3 | 300 | 1.99 | 3.98 | 132.67 | 1,509.95 |
| 400 | 0 | 0 | 0 | 0 | n/a | 0 |

At USD10, forty shares plus USD1.99 would exceed the slot cap, so only 39 fit. Five completed positions cost USD19.90 in broker fees, or 99.5 bps of starting NAV, **plus USD0.05 sell SEC minima** before other charges. At USD1, broker fees total USD39.204 (196.02 bps of NAV), plus USD0.05 SEC. USD400 shares cannot fit the Moomoo cap after fees. These are independent calculations, not production ledger changes. [Reproducible fee checks](../.qualification/daily-model-bridge/cost-verify.py).

For Wealthsimple with existing USD cash and an active USD account, the published commission and trade FX charges are zero: five USD400 positions nominally fit USD2,000 before execution uncertainty; USD400 shares fit one per slot. The ordinary CAD10/month plus tax USD-account charge is separate and the owner's waiver eligibility is unknown. If USD400 positions instead trade from CAD, the published conversion formula implies about USD12.0914 equivalent FX-only loss per flat round trip, USD60.4569 across five, or 302.28 bps of USD2,000 position notional, before the variable exchange-rate spread. Funding, ongoing account expense, explicit order fees and quoted spreads must remain separate.

## September 28: the intraday strategy's entry and exit windows

A separately declared sample adds **144 symbol/window cells** at 10:46 and 12:46 ET on the second Tuesdays of February, May, August and November in 2017, 2021 and 2025. Dates and the same six source-fixture stocks were fixed before any new intraday strategy result was read. These twelve independent dates add seasonal and execution-clock coverage to the earlier January sample; no empty or wide-spread cell was replaced.

All 24 requested windows completed in 29 HTTP200 pages, preserving 130,584 retained quote updates. Independent Decimal calculations verified all 144 cells' duration/count-weighted spread means, midpoint means, interval classifications, counts, raw hashes, pagination, SIP feed and session-asof parameters. Four wrapper checks cover preserved access failures, incomplete pagination and transport failures; the original verified capture and analyzer were reused unchanged.

| Symbol | Cells with valid quoted time / 24 | Range of duration-weighted mean full spread, bps |
|---|---:|---:|
| AAPL | 24 | 0.609–1.472 |
| MSFT | 24 | 0.538–3.191 |
| F | 24 | 5.023–10.859 |
| T | 24 | 2.465–4.056 |
| HRL | 24 | 2.193–8.251 |
| BANF | 18 | 12.004–105.315 |

The 8,640 requested symbol-seconds reconcile to 7,894.659755585 valid, 745.339400882 uncovered and 0.000843533 crossed seconds, with no other-invalid duration. Six empty BANF cells remain in the denominator. Locked states remain visible. Uncovered/empty time is not proof that the market had no quote.

This evidence reinforces stock-specific cost differences; **40 bps is not a measured universal trading cost**. It also does not supply a replacement all-in fee. These are full quoted spreads during the minute after each clock time, without a pre-window quote or stale timeout. They do not establish exact minute-open executable prices, realized slippage, price impact, fill capacity or broker routing costs. No frozen account, threshold or fee assumption was changed.

The Wealthsimple primary legal schedule was rechecked on September 28: zero listed-security commission and no trade FX for existing USD cash remain conditional on the USD-account route; its ordinary CAD10/month plus tax and funding FX remain separate. The owner's waiver is unverified. Moomoo direct retrieval again returned403; the earlier preserved tariff evidence remains the stated source, rather than claiming a new complete tariff retrieval. [Wealthsimple tariff](https://www.wealthsimple.com/en-ca/legal/fees/trade).

Evidence: `.qualification/intraday-cost-windows20260928`, definition `3dca6aa658167a658d908edf0f3b9b685785de8d313f3980abf631628c28d794`, [independent report](../.qualification/intraday-cost-windows20260928/independent-verification/report.md) and its `verification.json`. All 144 outcomes and original request/implementation/source identities remain preserved.
