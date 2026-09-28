# Bounded corporate-action source validation

September 28, 2026. The fixed batch is complete: **24 USD events across 23 symbols** from the previously frozen 91-event sample. The other **67 remain pending**, with no replacements. This is source evidence for strategy research, not a trading-policy qualification or a reason to suspend broader strategy experiments.

The audit retained 48 Alpaca SIP daily-bar responses (raw and split-adjusted) and 25 primary notice responses, all HTTP 200. Successful HTTP status did not imply coverage: LINK and both QXL windows were empty; ALM returned four later bars but neither required boundary. No original history, production code, model or account journal was changed. Strategy outcomes and account journals were not read for this audit. AIXI remains separate evidence and was not downloaded again.

## Findings that matter for strategies

Five provider entries categorized as splits describe **distributions or composite actions**. Their factors cannot be treated as actual share-quantity multipliers:

| Event | Provider new/old factor | Primary action terms |
| --- | ---: | --- |
| DHR, July 5, 2016 | 1.319 | One FTV share distributed per two DHR shares. [Issuer](https://investors.danaher.com/2016-07-02-Danaher-Corporation-Completes-Separation-of-Fortive-Corporation) |
| IP, October 1, 2021 | 1.056 | One SLVM share distributed per 11 IP shares. [SEC](https://www.sec.gov/Archives/edgar/data/51434/000005143422000040/ip-20220630.htm) |
| OLOX predecessor, September 28, 2023 | 2.133 | SG DevCorp distribution dated September 27, at 0.930886 shares per five parent shares; exact market ex-session remains unresolved. [SEC](https://www.sec.gov/Archives/edgar/data/1023994/000121390026073749/ea0295463-10k_olenox.htm) |
| ENOV, April 5, 2022 | 0.581 | One ESAB per three old parent shares, followed by an actual **1-for-3** parent reverse split. [Issuer](https://ir.enovis.com/news-releases/news-release-details/enovis-formerly-colfax-completes-spin-esab-corporation) |
| HON, June 29, 2026 | 0.9535 | One HONA per two old HON shares plus an actual **1-for-2** HON reverse split. [SEC](https://www.sec.gov/Archives/edgar/data/773840/000077384026000084/exhibit991-pressrelease629.htm) |

For all five, the frozen normalizer's reconstructed nominal closes agree with independent raw closes at both tested boundaries under the declared precision. That agreement **does not establish complete economic returns or action accounting**. Blindly substituting actual share ratios into a price reconstruction that also incorporates a distribution could create another error. Labels need consistent security units and distribution treatment; actual positions additionally need the correct parent/child quantities, fractional rights, cash and settlement.

EVO is a separate material convention problem: independent pre-IPO boundary bars both report 12.62 with zero volume, while frozen reconstructed nominal closes are approximately 99.90 and 25.63. The retained annual report establishes the later November 2021 ADS offering, but not the alleged October 20 ratio change or the earlier independent bar representation. Neither series is certified as correct. TOPS has a smaller effective-close disagreement, 0.53 versus 0.5325, outside declared precision. These remain unresolved source comparisons, not automatic repairs.

For immediate experiments, preserve the original baseline and predeclare a paired sensitivity using **action information alone**: mark examples whose feature or target windows intersect unresolved/composite boundaries, and separately assess candidate holding windows crossing them. Apply the same rule to every model and both directions; report affected sample counts, eligibility, abstention and all outcomes. Do not exclude entire companies, select windows from profitability, or interpret this small sample as a complete action blacklist. If labels or features change, refit preprocessing, models and calibration as new artifacts. This supports exploratory strategy iteration now; cash-account qualification still needs actual action entitlements and settlement.

## Separate evidence dimensions

| Dimension | Result |
| --- | ---: |
| Price adjustment factor consistent with original declared interval | 8 |
| Price adjustment factor outside that interval | 11 |
| Missing price boundaries | 4 |
| Price interval too wide to accept | 1 |
| Basic action ratio and stated market/effective date corroborated by a primary notice | 11 |
| Partial notice evidence, including legal/record versus market-date uncertainty | 6 |
| Provider factor contradicted **as a split-only quantity interpretation** | 5 |
| Notice insufficient to establish the event | 2 |
| Full action accounting qualified | **0** |

The 11 price-factor mismatches are not 11 proved corporate-action errors. The original engineering interval was fixed before requests: each price gets uncertainty `max(0.0005 USD, abs(price) × 0.0000005)`; positive intervals are propagated through the before/after adjustment-factor ratio. Acceptance also requires relative interval width at most 2%. These tolerances were not widened after seeing failures.

For MRBK, NTES, ODFL and DIT, the small differences are compatible with cent rounding of adjusted prices: for example, MRBK's exact half of 26.75 is 13.375 while the API returns 13.38. DHR also has a small factor difference, with distribution semantics and a rounded provider ratio. These observations explain why failure of the strict test is not proof of a bad action. They do not replace the declared result with a retrospectively relaxed pass.

The observed WOK price factor is exactly 100, but its interval width is approximately 3.67%, so it remains precision-insufficient. TOPS adjusted volumes are one share at both boundaries; allowing one-share rounding produces a zero lower bound, so its volume ratio is unidentifiable. Independent review corrected an initial derived classification of that volume case; the original intermediate files and review note are retained.

Across 40 available nominal boundary comparisons, 37 agree within declared precision and three differ (EVO twice, TOPS once). Volume differences, zero-volume bars and integer rounding are recorded separately; they do not prove liquidity or executable fills.

## Remaining cases in the attempted batch

The five composite cases are detailed above. The table below completes all 24 attempted events. “Consistent” refers only to the price-factor calculation.

| Event | Price-factor result | Primary evidence and remaining limit |
| --- | --- | --- |
| LINK, 2016-04-04 | Missing | [Proxy](https://www.sec.gov/Archives/edgar/data/828146/000155837016004899/link-20160620xdef14a.htm) identifies the issuer but does not verify this event. |
| MRBK, 2023-03-21 | Outside interval | [Issuer](https://investor.meridianbanker.com/documents/meridian-corporation-declares-two-for-one-stock-split/) confirms 2-for-1 after March 20 close; March 21 is a next-session inference. |
| NTES, 2020-10-02 | Outside interval | [Issuer](https://ir.netease.com/node/12531) confirms ADS underlying shares 25→5 effective October 1 close; October 2 is a next-session inference. |
| EVO, 2021-10-20 | Outside interval | [SEC](https://www.sec.gov/Archives/edgar/data/1412558/000110465922049929/evo-20211231x20f.htm) confirms later ADS terms; historical representation unresolved. |
| CZFS, 2024-06-14 | Outside interval | [Issuer release](https://www.nasdaq.com/press-release/citizens-financial-services-inc-reports-unaudited-second-quarter-2024-financial) confirms 1% stock dividend, June 14 record and June 28 payment; exact ex-session unresolved. |
| ODFL, 2024-03-28 | Outside interval | [SEC](https://www.sec.gov/Archives/edgar/data/878927/000095017024040017/odfl-20240402.htm) explicitly confirms 2-for-1 and adjusted trading March 28. |
| DIT, 2026-03-23 | Outside interval | [SEC](https://www.sec.gov/Archives/edgar/data/928465/000110465926045515/dit-20260331x10q.htm) confirms 3-for-2 effected March 20; exact market ex-session unresolved. |
| BRAI, 2026-04-29 | Consistent | [Issuer SEC exhibit](https://www.sec.gov/Archives/edgar/data/2076975/000149315226016061/ex99-1.htm) announces 3-for-1 and April 29 adjusted trading. |
| WMT, 2024-02-26 | Consistent | [Issuer](https://corporate.walmart.com/news/2024/01/30/walmart-announces-3-for-1-stock-split) confirms 3-for-1 and February 26 trading. |
| TOPS, 2017-10-06 | Consistent | [SEC](https://www.sec.gov/Archives/edgar/data/1296484/000091957419002626/d8214366_20-f.htm) confirms 1-for-2; nominal close and volume precision limits remain. |
| CRVO, 2023-08-17 | Consistent | [Issuer SEC exhibit](https://www.sec.gov/Archives/edgar/data/1053691/000143774923024064/ex_562007.htm) confirms 1-for-1.5 with DFFN→CRVO and EIP merger. Complete merger entitlements unverified. |
| CYPH predecessor, 2023-06-21 | Consistent | [Issuer SEC exhibit](https://www.sec.gov/Archives/edgar/data/1509745/000110465923072982/tm2319198d1_ex99-1.htm) confirms ten old LPTX shares into one, trading June 21; [later filing](https://www.sec.gov/Archives/edgar/data/1509745/000110465925109820/tm2530735d1_8k.htm) establishes the November 2025 rename. |
| NUWE, 2022-12-12 | Consistent | [Nasdaq](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-421) confirms 1-for-100; CUSIP 67113Y405. |
| QXL predecessor, 2022-09-06 | Missing | [SEC](https://www.sec.gov/Archives/edgar/data/797542/000149315226037811/form10-q.htm) confirms 1-for-28 with August 31 legal effectiveness; September 6 market ex-session unresolved. |
| ALM, 2025-07-07 | Missing | [SEC](https://www.sec.gov/Archives/edgar/data/1670061/000149315226037264/ex99-3.htm) confirms 1.5 old→1 and July 7 TSX trading. Selected USD predecessor/venue mapping unresolved. |
| WHLR, 2024-11-19 | Consistent | [Nasdaq](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-561) confirms 1-for-2; zero-volume boundary prevents volume conclusion. |
| STKH, 2025-04-28 | Consistent | [SEC](https://www.sec.gov/Archives/edgar/data/1828098/000121390026050174/ea0287480-20f_steakholder.htm) confirms five old ADS→one, underlying shares 100→500 per ADS. |
| WOK, 2025-12-29 | Precision insufficient | [Nasdaq](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-708) confirms 1-for-100 and par-value change; observed ratio alone does not satisfy precision rule. |
| QXL predecessor, 2025-03-14 | Missing | [SEC](https://www.sec.gov/Archives/edgar/data/797542/000149315226037811/form10-q.htm) confirms 1-for-4 effective March 14. [Issuer mapping](https://www.globenewswire.com/news-release/2026/04/30/3284966/0/en/after-successful-acquisition-quantum-x-labs-commences-trading-under-new-name-and-new-nasdaq-ticker-symbol-qxl-today.html) dates VBIX→QXL to April 30, 2026; requested historical data still empty. |

## Evidence and reproducibility

All evidence is under `.qualification/action-validation20260928/`: declaration and frozen sample hash; saved discovery queries/results; request manifests; every response, URL, timestamp and SHA-256; exact bar windows; Decimal factor intervals; notice assessments; `all91-status.csv`; and scripts. The unchanged source sample is from `action-inventory20260928`. Independent verification reproduced all 91 sample identities/minimum ranks, the 24-event scope, 48 requests and 584 returned bar representations, 23 original raw-source hashes, all Decimal comparisons, 25 notice payload hashes and the complete status ledger. Five material distribution/composite interpretations were spot-checked. The report is in this batch's `independent-verification/` folder.

Daily source and Alpaca timestamps are interpreted in America/New_York. The exact preceding source session and exact effective session are compared without forward-filling. Alpaca used SIP, raw/split representations and entity `asof=2026-09-18`; this parameter does not freeze the retrieval vintage or establish point-in-time symbol coverage. Later split factors cancel in the within-source boundary comparison, while absolute adjusted values and volumes can still reflect later actions.

This purposive, stratified sample is not an estimate of the universe's error rate. It does not detect every omitted action, establish historical listing completeness, or resolve the original capture's unavailable instruments and current-member survivorship. No correction, model refit or favorable strategy result is claimed.

