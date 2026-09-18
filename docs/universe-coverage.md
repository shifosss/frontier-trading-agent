# Research universe coverage

The research universe is discovered from public exchange files without a ticker-count cap. It is separate from the starter scanner and frozen Alpaca paper policy. Discovery makes a name eligible for data collection, not for an order. Historical liquidity, data quality, strategy ranking, position sizing, and broker eligibility remain separate decisions.

## Verified snapshot

Snapshot `20260918T201012673731Z-2da49ecfd9bb`, captured September 18, 2026 at 20:10 UTC, contains **8,434 candidates**: **5,661 US stocks**, **2,753 Canadian equity candidates**, and the existing **20 reference ETFs**. It retains 59 official source responses and explicit exclusions. Of these, 8,358 have exchange-published security symbols; 76 remain clearly labeled monthly issuer roots requiring provider validation.

| Listing venue | Research candidates, including baseline ETFs |
| --- | ---: |
| Nasdaq | 3,376 |
| NYSE | 2,029 |
| NYSE American | 258 |
| NYSE Arca | 11 |
| Cboe BZX | 1 |
| TSX | 668 |
| TSXV | 1,350 |
| CSE | 720 |
| Cboe Canada | 21 |

Counts change with exchange publications. The exact manifest, raw bytes, source URLs, publication dates, hashes, and exclusion reasons are under `data/research/universe/`; a compact verification record is at `artifacts/research-lab/expanded-universe-check.json`.

## What the exchange counts mean

Canada has thousands of exchange-listed issuers, not hundreds of thousands of distinct stocks. TMX reported **2,275 TSX issuers** and **1,706 TSXV issuers including NEX** for August 2026; the totals include ETFs and other products. Its listed *issues* counts were larger, because one issuer can have several share classes or other securities. These counts must not be equated with strategy-eligible ordinary equities. [TMX August 2026 statistics](https://www.newsfile-prod.tmx.cloud/release/313613/TMX-Group-Equity-Financing-Statistics-August-2026)

The captured US directories contained 13,258 rows, of which 7,515 were non-test and non-ETF. That second count still includes preferred shares, warrants, rights, debt, funds, and units. A claimed US total such as 6,700 depends on the date and whether ADRs, funds, OTC securities, and share classes are counted. The system reports its actual sources and classifications instead of treating that estimate as a target or cap.

## Sources and classification

- [Nasdaq-listed directory](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt) and [other US exchange listings](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt), using the [published field definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs). Include explicit common/ordinary shares, equity ADRs, and New York registry shares. Singular and plural share descriptions are accepted. Preserve current Nasdaq financial-status flags instead of using today's distress status to prefilter historical research.
- [TMX monthly issuer workbook](https://www.tsx.com/en/resource/571), linked from [current market statistics](https://www.tsx.com/en/listings/current-market-statistics), supplies TSX and TSXV issuer metadata. Current security classes are resolved through all 27 alphabet/numeric queries on each exchange's [official company directory](https://www.tsx.com/en/listings/listing-with-us/listed-company-directory). Root and issuer-name joins recover actual classes such as `CTC.A` and trust units such as `REI.UN`. Monthly-only roots remain explicit candidates; current-directory-only new issuers are retained with missing-monthly-metadata labels.
- [CSE listed securities feed](https://thecse.com/api/webapi/listed-companies/), used by its [public directory](https://thecse.com/listing/listed-companies/), supplies security type, status, currency and exact share classes. The captured feed has 739 records including suspended and delisted records. Equity candidates are retained for historical research; explicit delisted records are excluded from current membership. Suspended/halted flags are preserved and are not permission to trade.
- [Cboe Canada listing feed](https://www-api.cboe.com/ca/equities/listing-directory-data/), used by its [public directory](https://www.cboe.com/markets/ca/equities/market-activity/listing-directory/), distinguishes common/subordinate-voting equities from ETFs, CDRs, warrants and debt. The captured feed has 398 records, mostly funds and depositary receipts, not 398 distinct ordinary stocks.

Canadian exchange-to-provider mappings use `.TO`, `.V`, `.CN` and `.NE`, replacing class punctuation with hyphens. Actual free-provider responses were checked for `CTC-A.TO`, `REI-UN.TO`, `AAG.V`, `URB-A.CN` and `ALGO.NE`; each returned the requested symbol, CAD currency and equity type. Every history still undergoes its normal provider identity/currency validation.

Preferred securities, warrants, rights, debentures, capital-pool securities, unverified funds, unsupported symbol forms, and unknown share types have explicit exclusion reasons. Income-trust `.UN` equity units are included. New ETFs are not called unleveraged without evidence. Canadian USD-quoted listings are excluded until the research books support mixed exchange calendars in the same currency.

## Remaining coverage limits

- Current membership still introduces survivorship and selection bias. More current tickers do not reconstruct delisted historical membership. A source is not represented as point-in-time data merely because its bytes were saved today.
- NEX coverage is incomplete; OTC US listings are absent. There is no complete historic security-master claim.
- Some US exchange names omit a share-type label, such as AAP and ACEL. Those remain in `common_share_type_not_explicit`, rather than being silently identified as common shares through a name-only guess. That bucket also contains many funds and unit packages. A security-type resolution source is needed to recover the genuine stocks reliably.
- Current official TMX directories and monthly workbooks can disagree after listings, delistings, renames or migrations. Both vintages and unresolved roots are retained. Provider capture failures remain visible.
- Cross-listed issuers are not deduplicated by issuer identity. Candidate counts are securities, not necessarily unique businesses.
- Free daily history may be sparse, short or unusable for small companies. Broad discovery does not relax liquidity or execution-cost assumptions to manufacture trades.

## Verification

Eight offline regression tests cover exchange flags, equity ADRs versus preferred/package securities, all Canadian feeds, singular share labels, income-trust units, TSXV parsing, share-class resolution, source hashing, and preservation of active scanner/paper state. Ruff passes. Discovery was run against the actual official endpoints and the resulting manifest was loaded with all source-hash checks.
