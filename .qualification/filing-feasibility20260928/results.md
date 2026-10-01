# SEC filing strategy: source feasibility

September 28, 2026. **A conservative post-filing experiment is feasible with free official data, but the historical event corpus is not yet qualified.** Eleven bounded, unauthenticated SEC GETs all returned HTTP200; 11,620,679 original response bytes, URLs, retrieval times, HTTP metadata and SHA256 hashes are preserved. No stock returns, strategy scores, portfolio outcomes or broker operations were calculated. AAPL, MSFT and F were source examples selected before outcomes, not a trading universe.

The strongest immediate route is the proposed same-accession quarterly earnings change scaled by assets. It adds financial-disclosure information without reconstructing EPS share units. The source examples support its three raw inputs, not the strategy's profitability or its required eight-observation history.

## What the original filings establish

Values below are USD millions, taken from non-dimensional `us-gaap:NetIncomeLoss` and `us-gaap:Assets` inline facts within each **original accession**. The extraction preserves context IDs, start/end or instant dates, numeric scale, unit XML, dimensions, fact IDs and fragment hashes; duplicate occurrences must agree.

| Original 10-Q | Current quarter NI | Prior-year comparative quarter NI | Prior fiscal year-end assets in that filing |
|---|---:|---:|---:|
| [AAPL 0000320193-20-000062](https://www.sec.gov/Archives/edgar/data/320193/000032019320000062/aapl-20200627.htm) | 11,253; March29–June27,2020 | 10,044; March31–June29,2019 | 338,516 at September28,2019 |
| [MSFT 0000950170-24-048288](https://www.sec.gov/Archives/edgar/data/789019/000095017024048288/msft-20240331.htm) | 21,939; January1–March31,2024 | 18,299; January1–March31,2023 | 411,976 at June30,2023 |
| [F 0000037996-24-000144](https://www.sec.gov/Archives/edgar/data/37996/000003799624000144/f-20240630.htm) | 1,831; April1–June30,2024 | 1,917; April1–June30,2023 | 273,310 at December31,2023 |

These are three-month facts, not the simultaneously disclosed six/nine-month totals. Fiscal dates must be retained; Apple's calendar is not a calendar-quarter convention. Ford's exact NetIncomeLoss facts occur in the equity statement. Its `ProfitLoss` values are 1,833 and 2,016 million and include noncontrolling interests; they are not interchangeable with the declared concept. Do not silently substitute a different earnings tag when one is unavailable. Selecting current-filing comparative facts is information available at that filing; it is not permission to rewrite an earlier event using a later comparative.

## The tradable clock is deliberately later than acceptance

| Filing | Index acceptance text, interpreted ET | Official filing date | Proposed next-session-close entry after D |
|---|---|---|---|
| [AAPL 10-Q index](https://www.sec.gov/Archives/edgar/data/320193/000032019320000062/0000320193-20-000062-index.html) | July30,2020 19:29:09 | July31 | August3,2020 16:00ET |
| [MSFT 10-Q index](https://www.sec.gov/Archives/edgar/data/789019/000095017024048288/0000950170-24-048288-index.htm) | April25,2024 16:06:24 | April25 | April26,2024 16:00ET |
| [F 10-Q index](https://www.sec.gov/Archives/edgar/data/37996/0000037996-24-000144-index.htm) | July24,2024 19:23:59 | July25 | July26,2024 16:00ET |

Here `D=max(acceptance ET date, filingDate)`, with information cutoff at the end of D plus one hour, then the next regular exchange-session close. Entry dates were checked against the existing frozen exchange calendar, not by assuming weekdays. These are clock examples only, not simulated trades.

Apple is independently joined across its index, [SGML header](https://www.sec.gov/Archives/edgar/data/320193/000032019320000062/0000320193-20-000062.hdr.sgml), and [submissions JSON](https://data.sec.gov/submissions/CIK0000320193.json): API `2020-07-30T23:29:09.000Z` converts to the exact 19:29:09 ET index/header value. MSFT/F acceptance here was checked on their original indexes, not independently joined to their submissions APIs.

**This is a conservative historical availability proxy, not proof of the instant a filing became public.** SEC says some submissions begun after17:30ET disseminate the next business day; indexes update nightly, and corrections/removals can occur after acceptance. Using filingDate prevents the demonstrated prior-day leakage, but does not eliminate unusual dissemination delays or later archive corrections. The current archive was retrieved in2026 and is not a historical capture from the original publication instant. [SEC access and dissemination rules](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

## Earnings releases and EPS are separate evidence

Apple's earlier [8-K accession 0000320193-20-000060](https://www.sec.gov/Archives/edgar/data/320193/0000320193-20-000060-index.htm) was accepted July30,2020 18:55:04 ET and filed July30. Its [original earnings exhibit](https://www.sec.gov/Archives/edgar/data/320193/000032019320000060/a8-kexhibit991q3202062.htm) contains diluted EPS2.58 and announces the four-for-one split, with split-adjusted trading starting August31. The release has a calendar date, not a verified first public distribution timestamp. Its SEC acceptance is also not that earlier release time. An 8-K strategy could use this exact exhibit after its own conservative clock; it cannot import later10-Q facts into the earlier event.

The saved [Apple diluted-EPS concept API](https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/EarningsPerShareDiluted.json) reports the same March29–June27,2020 period as2.58 in the original10-Q, but0.65 in a later2020 10-K and2021 10-Q. All rows say `USD/shares`. Thus the unit name alone does not encode the split basis; 2.58/4 rounds to0.65. Original2.58 was checked against the original inline fact. The later values are retained API records, not separately downloaded/reviewed later filings. This directly demonstrates why an unfiltered latest-value or frame query cannot supply earlier as-reported EPS. No split repair or return calculation was performed.

## Entity mapping and a practical acquisition path

Each original cover supplies a dated class/ticker/exchange association: Apple common stock AAPL/Nasdaq, Microsoft common stock MSFT/Nasdaq, Ford common stock F/NYSE. The same CIK can cover debt classes: Apple's notes have no ticker in this sample; Microsoft also prints MSFT for two note classes; Ford lists FPRB/FPRC/FPRD note classes. Join the security class and context, not just ticker or CIK. CIK identifies the filer and is not recycled, while SEC's current ticker files are not guaranteed complete/accurate and are not a dated listing history. These three covers establish these points in time only. [SEC mapping guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

The actual submissions response contains accessionNumber, filingDate, reportDate, acceptanceDateTime, form and primaryDocument arrays, plus additional-history file references. Apple's retained recent block includes the2020 examples; its additional file covers1994–2015. No claim is made that other issuers' recent blocks span the same interval. The API is free without keys. Companyfacts/companyconcept can locate candidate facts by accession, but original documents still resolve context, dimensions and comparability. Frames use last-filed facts and are unsuitable as a point-in-time panel. Typical API processing latency is not a public-availability guarantee. [SEC API contract](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

Next acquisition should be separately declared: first10-Qs for a fixed issuer sample and date range, submissions plus all required history pages, accession indexes/headers and original inline/XBRL documents; retain amendments and absent/conflicting contexts as failures without backfills or substitute issuers. Original quarterly NI and year-ago comparative plus previous fiscal year-end Assets must be present in USD, non-dimensional, with consistent duplicate values. No annual-minus-YTD Q4. Verify the previous eight already-known innovations before any standardized signal. A2012–2025 six-issuer proposal is a next qualification scope, not work completed here.

Marginal vendor/API cost is **USD0** at the documented public endpoints; this sample used one request/second, one attempt per URL, an honest project user-agent and no invented contact address. Larger work needs a real operator contact if required by the service and continued fair-access compliance; no contact was fabricated. Storage, bandwidth and local compute are the remaining costs. There is no need to buy consensus data for this specifically seasonal accounting hypothesis. Avoid downloading nightly whole-market bulk archives for a small issuer pilot.

## Completion and limits

`verification.json` confirms11/11 raw hashes/statuses,190 selected original fact occurrences, all nine required NI/assets values, common-stock cover mappings and Apple's API/index/header clock agreement. `requests.json` is the URL-to-raw-file/hash manifest. `inspect_sources.py` and `verify_samples.py` reproduce the bounded extraction and checks without network. These checks are local self-verification, not a separate external audit.

Early inspection attempts found lxml unavailable and full-page XML parsing invalid because the served HTML contains non-XML script attributes. No package was installed. The final small script parses isolated original context/unit fragments and targeted inline facts, including nested facts; raw source files remain unchanged. It is a sample-inspection tool, not a general-purpose XBRL parser. These tooling failures did not trigger replacement data or extra GETs.

Still unqualified: eight-innovation history, historical first-filing completeness, issuer/security continuity between sampled filings, all missing/custom/ambiguous contexts, broad small-stock coverage, actual publication-vintage completeness, price/action linkage, execution costs and predictive performance. A full causal post-filing backtest is therefore not ready today. The evidence establishes an accessible and concrete source route for the next declared historical test; it does not establish an earnings edge.
