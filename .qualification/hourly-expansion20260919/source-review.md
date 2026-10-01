# Existing-access US hourly stock data

Verified September 19, 2026 using three bounded historical-data requests. No account, order, transfer, subscription or live-price endpoint was queried. No new spending, model changes or strategy experiment occurred.

The existing Alpaca credentials returned historical **SIP individual-stock data**. This extends the evidence beyond the previous SPY-only hourly snapshot; it establishes availability for the two tested stocks and windows, not comprehensive coverage.

## Observed coverage

| Requested feed and interval | AAPL | MSFT | What was observed |
| --- | ---: | ---: | --- |
| SIP, raw 1Hour, January 4–8, 2016 | 79 bars | 73 bars | Includes regular and extended hours |
| IEX, same interval | 0 bars | 0 bars | HTTP 200 with an empty bars object |
| SIP, raw 1Min, November 29, 2024, 09:30–12:59 ET | 210 bars | 210 bars | Every expected minute in the early-close session window |

All requests returned HTTP 200 without a remaining pagination token. The oldest observed timestamp for **both stocks** was **2016-01-04T09:00:00Z**, or 04:00 ET. Nothing before that timestamp or beyond these windows was tested.

Alpaca documents free Basic historical US stock/ETF access since 2016, 200 requests per minute and exclusion of the latest 15 minutes. Basic real-time equities use IEX. The account's subscription was not inspected; the probe establishes existing credential access without an upgrade. Historical SIP and IEX are different feeds: the empty IEX result cannot substitute for the SIP history, and IEX volume cannot be treated as consolidated market liquidity. [Official access documentation](https://docs.alpaca.markets/us/docs/about-market-data-api).

## Clock and calendar checks

The provider's 1Hour timestamps start on the **top of the clock hour**. Each stock's five-day sample contains 30 bars wholly inside regular sessions and five 09:00–10:00 ET bars crossing the 09:30 opening boundary. AAPL has another 44 bars outside regular sessions; MSFT has 38. Relabeling or cropping the opening-crossing hourly bar cannot recover a pure 09:30–10:00 OHLCV bar. Alpaca defines left-edge timestamps and aggregates hours from minute bars. [Bar aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq).

The minute sample independently matches the exchange calendar's November 29, 2024 early close at 13:00 ET, confirmed by [Nasdaq's UTP notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=UTP2024-16). Offline aggregation yields these intervals for **each** stock:

- 09:30–10:30: 60 minute bars.
- 10:30–11:30: 60 minute bars.
- 11:30–12:30: 60 minute bars.
- 12:30–13:00: 30 minute bars.

There are no missing or duplicate minutes in this fixture. OHLC bounds, finite positive prices and nonnegative volume pass; aggregated volume reconciles exactly. This covers minute buckets starting before the close. A closing-auction print timestamped exactly at 13:00 needs a separately specified boundary policy; these bars are not asserted to equal official daily closing prices or daily volume.

## Recommended implementation lane

Build an isolated **SIP minute capture and session-aligned hourly aggregation** lane, initially with a bounded liquid US stock universe. Preserve raw bytes, feed, timezone, request bounds, adjustment, ticker-mapping date, pagination and response hashes. Aggregate from each actual session open, retain final partial hours and expose missing observations rather than filling them forward. All-symbol, delisted-stock and Canadian-listed hourly coverage remain unverified.

For an executable free-data workflow, explicitly model the 15-minute SIP restriction plus bar-completion/processing latency. Historical downloads are today's revised data vintage, not proof of the original publication time. Alpaca also documents late bar updates and extended-hours aggregation. [Timing and revisions](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data).

These probes used `adjustment=raw`: no split or dividend reconstruction was silently applied. The explicit `asof` dates, January 8, 2016 and November 29, 2024, control ticker/entity mapping. They do not establish historical universe membership or a point-in-time information vintage. Split/dividend-adjusted bars remain a separate requested representation with their own provenance. [Historical-bar contract](https://docs.alpaca.markets/us/reference/stockbars).

Corporate-action access and completeness were not probed. Before overnight hourly research, reconcile splits and dividend entitlement using economic effective/ex-dates. Alpaca's action endpoint filters by process-date ranges and does not guarantee immediate availability after announcements; an empty response is not evidence of no actions. [Corporate-action contract](https://docs.alpaca.markets/us/reference/corporateactions-1).

## Reproducible evidence

The original snapshots remain unchanged. The retained probe definition and response captures contain explicit request parameters, UTC capture timestamps, raw byte counts and full SHA-256 hashes:

- [Fixed three-request definition](probe-definition.json) and [result summary](probe-summary.json).
- [SIP hourly capture metadata](sip-hourly-20160104-20160108.capture.json): `5105426c917fccd4b8e4137ec5c7c79f456720bfdc4e2fe693ad989df401b266`.
- [IEX hourly capture metadata](iex-hourly-20160104-20160108.capture.json): `c700148960d500511ad0040f8b1c3c6ebbac07572176aff49cfc66b69eec9aee`.
- [SIP minute capture metadata](sip-minute-20241129-regular-early-close.capture.json): `53be89a5212a3c9fedf49b98c1e0d00547f74d4e6de52755ae444fbd539cab0f`.
- [Offline analysis](offline-analysis.json) and [reproducible validation script](analyze_saved.py), which performs no network or account access.

This is source qualification, not a profitable strategy, a live-ready hourly system or proof of complete corporate-action coverage.
