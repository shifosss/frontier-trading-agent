# AIXI source-continuity audit

Completed September 28, 2026. The August 28 five-session label of **+548.11% is a verified ADS-unit discontinuity**, not usable evidence of that investment return. Frozen sources, historical results and models remain unchanged. No corrected account or strategy fit was produced.

## Evidence and exact interval

The frozen source is run `90af4c840aad48f7ab58fba7a682f96a`, reused by `814780d48b4141b9a82a3fb917d1b85a`. AIXI's Yahoo payload, captured September 18 at 20:19:16 UTC, has SHA-256 `78718566befb39a31c0bd12742a0a8c1d64bbe0dd7cfa456703b564cff37207e`. The audit independently verified those bytes and reproduced the saved float32 label exactly.

The August 28 signal enters at the August 31 close. Its five subsequent sessions are September 1, 2, 3, 4 and 8; September 7 is excluded by the saved exchange calendar. Yahoo adjusted close is 0.50300002098 at entry and 3.25999999046 at exit. The payload already reports a September 8 one-for-seven split, but its close and adjusted-close fields are identical across all 886 rows.

[Nasdaq's September notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-643), the [issuer's SEC release](https://www.sec.gov/Archives/edgar/data/1935172/000121390026096964/ea030426001ex99-1.htm) and the [Citibank depositary notice](https://depositaryreceipts.citi.com/adr/common/file.aspx?idf=7973) agree: seven old ADSs become one new ADS on September 8, 2026. Each ADS changes from 60 to 420 underlying ordinary shares. The ticker stays AIXI, while CUSIP changes from 98423X308 to 98423X407. This is an ADS ratio change; ordinary shares are unaffected.

Two data-only requests through existing Alpaca access returned 886 raw and 886 split-adjusted SIP daily bars for the same sessions, with pagination complete. Requests explicitly set `asof=2026-09-18`, USD, and raw versus split adjustment. These are September 28 revised-vintage observations; they do not establish historical information availability. [Alpaca's documented conventions](https://docs.alpaca.markets/us/reference/stockbarsingle-1) distinguish raw prices from split-adjusted prices and entity-date mapping.

| Session | Frozen Yahoo adjusted close | Independent raw close | Independent split-adjusted close |
| --- | ---: | ---: | ---: |
| August 31 | 0.50300002 | 0.503 | 3.521 |
| September 4 | 0.47200000 | 0.4715 | 3.301 |
| September 8 | 3.25999999 | 3.26 | 3.26 |

The action-consistent gross price arithmetic is `3.26 / (7 * 0.503) - 1 = -7.412666856%`. This illustrates the unit mismatch; it is **not a corrected account return**. Citibank specifies a $0.05 fee per canceled old ADS. The issuer specifies aggregated sale and cash distribution for fractional entitlements after applicable fees, taxes and expenses. Actual cash-in-lieu proceeds, timing and broker pass-through are unverified.

## Scope and both directions

All 877 pre-September-8 Yahoo adjusted prices are approximately one seventh of the independently split-adjusted prices; the nine later rows agree within float precision. The existing normalizer assumes Yahoo OHLC already incorporates every reported split and reverses those adjustments. Here that assumption also makes pre-event reconstructed nominal prices approximately one seventh of the independent raw prices. This affects sizing, price filters and per-share fee assumptions beyond the single target. It does not justify multiplying every issuer's history by a guessed factor.

Earlier reported actions are separately corroborated: [August 23, 2024](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-396), one new ADS for nine old, new CUSIP 98423X209; [May 11, 2026](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-312), one for twenty, new CUSIP 98423X308. All three boundary comparisons are retained.

The 12 largest and 12 smallest frozen daily moves were compared, with all 886 rows also retained. The September 8 apparent +590.68% becomes approximately -1.24% on the independent adjusted series. Other extreme moves remain: April 6 is approximately +514.92%, August 25 +186.29%, June 22 -51.12%, and August 26 -38.58%. Large magnitude alone is insufficient evidence for deleting or repairing data. Minor provider price/volume differences and both signs are preserved.

Evidence resides in `.qualification/aixi-source-audit20260926/`: `definition.json`, `capture.py`, `analyze.py`, original response bytes and metadata, `issuer-action-map.json`, `findings.json`, `all-886-session-comparison.csv`, both-direction tails, surrounding window, action boundaries and SHA-256 inventory. Source timestamps, exchange-session labels, identities and failures are retained.

A future correction must be a separately declared, reproducible action-aware dataset and ledger comparison. Preserve the original experiment and evaluate all affected dates, holdings, labels, price filters and costs. This issuer audit neither establishes all-universe completeness nor qualifies any model or paper migration.

## Predeclared follow-up scope

Before any new economic run, freeze one action-aware comparison against the untouched original capture, with the same universe, dates, account balances, models, policy and costs. Record every affected and unresolved row; do not select repairs, tolerance values or exclusions using strategy returns.

1. Separate common-unit synthetic labels from actual dated nominal ADS prices and quantities. Use independently documented action factors and original share units for sizing. A ratio-consistent price series alone cannot simulate cash-in-lieu, depositary charges or their settlement.
2. Audit every reported split/action boundary across the source capture in both directions. Compare reported factors, provider price/volume conventions and independent raw/adjusted observations. Fix tolerances from tick precision, rounding and declared session conventions before reviewing economic results. Retain ordinary large market moves; unresolved boundaries remain explicit failures rather than guessed repairs.
3. Save a new immutable dataset version with issuer/security mapping, effective-session evidence, original and proposed values, rationale and unresolved accounting. Rebuild any affected fitting/calibration features or targets and rerun preprocessing, every base model, ensembles and calibration as new candidates. Never patch saved model metadata to claim compatibility. Where samples are unaffected, demonstrate that directly rather than assume it.
4. Report all original-versus-new metrics, changed eligibility, fees, trade counts, missing paths, losses and abstentions. Qualify actual action-aware cash accounting separately before a paper-policy migration.
