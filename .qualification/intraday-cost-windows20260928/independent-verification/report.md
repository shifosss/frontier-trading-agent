# Independent verification of intraday quote windows

All144 predeclared symbol/window cells passed. No network requests, strategy returns, fee changes or source edits were made. The independent Decimal implementation follows the earlier cost-verify interval method but does not import or invoke the saved float analyzer.

Verified29 HTTP200 response pages and raw hashes, the complete page-token chain, requested SIP/asof/symbol/time parameters,24 completed windows, all5 frozen implementation hashes and the source-analysis definition identity. Exact exchange-calendar checks confirm12 second Tuesdays in February/May/August/November2017,2021,2025 at10:46ET and12:46ET, each60seconds. These add dates and the actual proposed entry/exit clocks to the earlier54-cell sample.

For all144 cells, the duration-weighted and count-weighted full-spread means, valid-state midpoint mean, quote/invalid/locked/crossed/equal-time/duplicate counts, terminal exclusions and coverage intervals match independently recomputed values. Absolute comparison tolerance is1e-9 seconds/bps/USD for saved float rounding. Nanosecond interval sums exactly cover all8,640 requested symbol-seconds. Synthetic empty, duplicate-time, terminal, crossed, locked and invalid-size cases also passed.

- Retained updates:130,584.
- Valid observed duration:7,894.659755585seconds.
- Uncovered leading/empty duration:745.339400882seconds.
- Crossed duration:0.000843533seconds; other-invalid duration:0.
- Locked duration:8.920066111seconds, included in valid duration.
- Six empty BANF cells remain in the144-cell denominator; each has no spread estimate.

| Symbol | Cells with valid time /24 | Min–max duration-weighted full spread, bps |
|---|---:|---:|
| AAPL | 24 | 0.608882–1.472155 |
| MSFT | 24 | 0.537681–3.190874 |
| F | 24 | 5.022944–10.858867 |
| T | 24 | 2.465179–4.056359 |
| HRL | 24 | 2.192643–8.250599 |
| BANF | 18 | 12.004294–105.315031 |

The range table describes this fixed sample, not a universe-wide tariff or a recommended replacement for a sensitivity assumption. A full quoted spread is not a per-side fee. Duration-weighted states after10:46/12:46 do not prove the quote available at the exact minute-open trade reference; no pre-window state was requested or carried. An empty cell does not prove there was no market quote. No stale timeout or condition-specific executability qualification was introduced. Spread data do not establish fills, price impact, order-routing costs or full round-trip costs. Six surviving pilot names and12 fixed dates remain limited coverage.

Evidence: `verification.json` retains every cell result and source-page identity; `verify_cost_windows.py` reproduces the audit from saved files. The original capture, analyzer and definition remain unchanged.
