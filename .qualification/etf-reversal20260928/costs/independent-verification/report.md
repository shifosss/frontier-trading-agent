# ETF quote-cost qualification

All 33 predeclared cells passed source/statistic and 59-second valid-state coverage gates. The uniform allowance is **15 bps round trip (7.5 bps per side)** before the unchanged Wealthsimple USD or Moomoo Canada explicit order-fee profiles. It follows ceiling(4.266721023169631984781013402)+10; the maximum mean was XLF on 2016-01-04.

The single capture completed all three windows in 23 HTTP200 pages, retaining 220,121 in-window quotes and 24,691,046 bytes. No errors, retries, alternate dates or replacement instruments occurred. Both observed capture PIDs exited and the dedicated capture lock is available.

Independent Decimal arithmetic verified every quoted-state interval, quote count, full-spread and midpoint mean, source hash, pagination token, fixed SIP feed and session-asof parameter. All 33 original analysis cells and raw sources remain unchanged. The derived allowance independently matches the saved result.

Of 1,980 requested symbol-seconds: valid 1,979.842031722; crossed 0.044286336; other-invalid 0; uncovered 0.113681942. Locked states account for 10.517485181 valid seconds. Minimum cell valid duration was 59.966000000s; longest carried quote state was 1.544160175s.

| ETF | 2016 mean spread bps | 2020 | 2024 |
|---|---:|---:|---:|
| DIA | 1.056453 | 0.429850 | 0.533463 |
| IWM | 0.962835 | 0.627768 | 0.501000 |
| QQQ | 0.915340 | 0.466247 | 0.255775 |
| XLE | 1.819068 | 1.650480 | 1.166209 |
| XLF | 4.266721 | 3.219915 | 2.645075 |
| XLI | 1.915005 | 1.205527 | 0.881714 |
| XLK | 2.311076 | 1.071229 | 0.595929 |
| XLP | 2.006659 | 1.600492 | 1.372908 |
| XLU | 2.294803 | 1.568059 | 1.557023 |
| XLV | 1.380334 | 0.974764 | 0.723313 |
| SPY | 0.501252 | 0.322149 | 0.211491 |

These are three purposive January sessions at15:59-16:00ET, not an all-period execution distribution. Quote states have no stale-age cutoff, no pre-window carry, and no proven fill capacity. Crossed periods were excluded without bridging; locked quotes were retained. The full-spread-to-roundtrip interpretation around midpoint does not establish execution relative to a daily closing trade or closing auction.

The additional10bps is a predeclared, uncalibrated adverse allowance. Maximum-sample-plus10 is a uniform quote-informed scenario, not realized slippage calibration or an upper bound. Current broker tariffs remain a historical counterfactual; incomplete venue/tax/promotion/rounding coverage, account subscription and funding/withdrawal FX are separate. No strategy returns were read and no broker/account operation occurred.

See cost-definition.json, cost-qualification.json, cost-analysis.json, cost-all-cells.md, tariff-recheck.json and independent-verification/verification.json. The latter contains all33 independent cell results and all23 source identities.
