# Historical SIP quote-access fixture


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

Evidence: [fixed request and analysis definition](probe-definition.json), [page summary](probe-summary.json), [full distributions and validity audit](quote-analysis.json), and [offline reproduction script](analyze_saved.py).

Raw SHA-256 hashes are `279bfabfd175f89924f3b44dccc68acec54c5e212eb9634d8b6783c47f0236df` for page 1 and `24672da7049153da3aba71aceb5bce0d47150a37074e4d5f39dd81a9cfd8543d` for page 2. The corresponding capture metadata preserves request parameters, response timestamps and raw filenames; credentials are not stored.
