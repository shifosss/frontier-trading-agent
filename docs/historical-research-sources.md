# Historical research: sources and design decisions

Research checked September 18, 2026. These recommendations extend the existing broad study; they do not certify profitable performance or authorize a new trading mandate.

## What to improve first

1. **Use longer history now.** The first broad study has only five years, mostly after the 2020 shock. Fetch the maximum available daily history and report each instrument's actual start/end, usable sessions, missing sessions and source. Evaluate several market regimes and keep recent years visible separately. More years of today's survivors do not resolve survivorship bias.
2. **Select strategies using past data only.** Predeclare a small, reasoned family of models and parameter neighborhoods. Use rolling or expanding training windows followed by calendar test windows. At each selection date, training trades must have exited before the test window; all training transforms, thresholds and rankings must use information available then. Include cash as a selectable alternative. Preserve the selected model and every losing attempt in an immutable research record.
3. **Separate signal diagnostics from account performance.** The existing `strategy_study.py` resets cash for independent cohorts. Keep it for comparison, but do not compound those cohort averages into account CAGR or drawdown. A portfolio replay must carry cash, positions, fees, holdings, settlement constraints, corporate actions and exits through time. Test the intended daily/weekly execution policy, not an unrelated holding-period proxy.
4. **Use failure-sensitive comparisons.** Retain missing selected outcomes, terminal gaps and rejected histories in coverage statistics. Dropping them from averages can select away bad investments. For unresolved exits, report explicit adverse scenarios or incomplete evidence; do not invent a delisting return from an ordinary missing bar. Compare with cash, a passive benchmark, and an exposure-matched benchmark so a low-investment strategy does not appear successful merely by paying fewer costs.
5. **Choose robustness over the best backtest row.** Look for neighboring parameters, multiple years, both cost stresses and different liquid-stock tiers to agree. Use paired resampling in calendar blocks, preserving market-wide correlation; do not treat thousands of stocks on the same day as independent observations. Record all tried variants and apply multiple-testing-aware inference when a claim of statistical significance is made.

The prior study's development, validation and evaluation results have already been exposed. Repeatedly revising a strategy against those dates makes them research data. A retrospective walk-forward run is valuable, but must not be described as an untouched holdout. Future observations are a final independent check; research improvement does not need to wait for them.

## Practical data sources

| Source | What is useful now | Limitation and next action |
| --- | --- | --- |
| [Alpaca market data](https://docs.alpaca.markets/us/docs/about-market-data-api) | Existing paper-account access has a documented free Basic tier, US stock/ETF history since 2016, and 200 historical requests/minute. | Probe the existing entitlement with delayed SIP data. Real-time Basic equities are IEX only. Do not silently mix IEX volume with consolidated SIP liquidity thresholds. |
| [Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbars) | Daily/weekly bars, explicit raw/split/dividend/spin-off adjustments, pagination and ticker mapping. | Save the feed, requested interval, adjustment and mapping date. `asof` resolves the entity behind a ticker; it does **not** make the result a historical data vintage or a complete delisting database. Page until `next_page_token` is empty. |
| Existing Yahoo capture | Extending the existing capture to all available history can give older observations for US and Canadian instruments without adding a paid dependency. | Verify actual returned dates and corporate actions empirically. Current adjusted history and current membership are exploratory inputs, not a point-in-time historical investable universe. Avoid interpreting split-adjusted past prices as historical whole-share affordability. |
| [Ken French data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) and [factor definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html) | Free market, size, value, momentum, reversal and industry research series. The US three-factor daily/weekly history starts in 1926. Useful for factor attribution, long-run stress regimes and independent benchmark controls. | These are aggregate research returns, not per-stock OHLCV or an executable small-account portfolio. The library explicitly revises full histories; retain downloaded bytes and vintage. Treat missing-value sentinels as missing. |
| [Nasdaq symbol directory](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs) | Authoritative current issue classification, test-issue flags, listing status and creation timestamps. | It is current membership. Preserve snapshots, classify common shares/ADRs/REITs/ETFs separately, and avoid counting warrants, preferreds, test symbols and duplicate listings as distinct common stocks. |
| [TMX current statistics and issuer lists](https://www.tsx.com/en/listings/current-market-statistics) | TSX and TSXV current lists, historical reports and dated issuer snapshots. | Add TSXV rather than treating the existing TSX-only subset as Canada. Issuer roots are not always price-provider share-class tickers. Archived lists alone do not supply delisting returns. |
| [CSE activity summaries](https://thecse.com/market-activity/activity-summaries/) | Official daily, weekly, monthly and annual tab-delimited summaries, worth probing for coverage and reconciliation. | The public archive's historical depth and corporate-action completeness have not been established in this review. CSE also sells enhanced files; do not assume paid enhanced data are included in the public summaries. |
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Free, unauthenticated filing histories and XBRL facts, with bulk downloads. Useful later for filing-time fundamentals and earnings-event hypotheses. | Align to the actual acceptance/publication timestamp and historical accession. A later restatement cannot replace the information originally available. Filing data do not replace stock price/delisting histories. |

No comprehensive, delisting-complete, freely accessible US-and-Canada daily stock database was validated in this review. That is an identified data gap, not a reason to stop research. Existing-access Alpaca plus the current free capture can extend the exploratory history immediately. The following paid sources describe the missing capability and are **not purchased or assumed available**:

- [CRSP US Stock Database](https://www.crsp.org/research__trashed/crsp-us-stock-databases/) includes active/inactive securities, permanent identifiers, corporate actions and delisting information; NYSE history begins in 1925. Existing institutional access could help if the user already has it.
- [Norgate content tables](https://norgatedata.com/data-content-tables.php) and [packages](https://norgatedata.com/stockmarketpackages.php) describe US and Canadian delisted coverage and historical index constituents. Canadian Platinum specifies history back to 1990. This requires a subscription or verified existing access; no spending is authorized.

Stooq and the discontinued WIKI dataset are possible secondary cross-check candidates, but their current practical access, delisting completeness and suitability were not validated here. Do not promise them as a complete replacement for either of the above.

## Market size: define the denominator

There are thousands of Canadian equity listings, not hundreds of thousands of distinct Canadian stocks. TMX's [August 2026 financing release](https://www.newsfile-prod.tmx.cloud/release/313613/TMX-Group-Equity-Financing-Statistics-August-2026) reports **2,275 TSX issuers / 2,930 issues**, and **1,706 TSXV issuers / 1,760 issues**, the latter including NEX. These totals include funds and other security types; they are not common-stock counts. CSE and Cboe Canada add coverage, while cross-listings require deduplication. The release is dated September 9, 2026.

The user's approximately 6,700 US figure should be treated as a coverage target to reconcile, not a number to manufacture. Common stocks, foreign ADRs, REITs, funds, share classes, OTC securities and historical delistings yield different totals. Report discovered, classified, requested, valid-history and currently eligible counts separately, with exclusion reasons.

An option series is also not another company: its underlying, expiry, strike and call/put type define a separate contract. Montréal Exchange publishes [underlying option classes separately](https://www.m-x.ca/en/trading/data/options-list). Contract counts cannot be used as counts of Canadian stocks.

## Research-backed hypotheses worth testing

These are candidate hypotheses, not conclusions about this user's account:

- Add medium-term momentum that skips the most recent month, alongside the existing 20/60-session rule. It separates longer-run persistence from short-run reversal. Compare the same universe, costs, risk and turnover rather than treating a new formula as a new independent dataset.
- Test risk reduction after elevated trailing volatility and market stress using a capped, long-only exposure rule. [Moreira and Muir](https://www.nber.org/papers/w22208) motivate volatility scaling; [Cederburg et al.](https://doi.org/10.1016/j.jfineco.2020.04.015) find weaker real-time benefits in broad out-of-sample comparisons. This supports testing, not assuming, improvement.
- Evaluate momentum and pullbacks separately during market rebounds after drawdowns. [Daniel and Moskowitz](https://www.nber.org/papers/w20439) document momentum crash states. Their result concerns portfolios with different construction from the present long-only account, so it is a stress-test motivation, not a directly transferable rule.
- Add an explicitly low-turnover rank-buffer variant: hold a name until it leaves a wider rank band, and compare it with immediate replacement. Costs have already erased promising averages in the initial study, making turnover reduction a reasoned engineering target.
- Only after return accounting and walk-forward selection are stable, test filing-time quality/earnings filters using EDGAR. Current fundamentals or retrospective news summaries should not be injected into old decision dates.

## Statistical primary references

[Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explains why selecting from many attempted strategies creates false positives and proposes an overfitting diagnostic. [Bailey and Lopez de Prado, The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) addresses selection and non-normal-return effects. Neither method repairs biased source data, unrealistic executions, or a test window repeatedly used for design.

[Shumway, The Delisting Bias in CRSP Data](https://doi.org/10.1111/j.1540-6261.1997.tb03818.x) establishes why missing terminal returns matter. A broader current survivor list and a longer adjusted-price series alone do not fix that problem.


## Existing connector probes

Actual requests on September 18, 2026 established more than documentation alone:

- Alpha Vantage listing_status for January 1, 2020, state delisted, supplied a downloadable CSV with **3,762 delisted securities**, latest delisting December 31, 2019. Its Stock classification includes preferreds, warrants and ticker changes, so this is a candidate identity source requiring classification, not 3,762 additional common companies. The connector return_full_data=true call unexpectedly returned an empty object; the preview mode data_url worked.
- Alpha Vantage daily adjusted BBBYQ data was premium-blocked. A sequential retry confirmed daily raw outputsize=full is also premium for this access. No subscription was purchased.
- Raw daily compact BBBYQ data did work: 100 observations ending September 29, 2023. Neither its final quoted price nor the last bar establishes ultimate shareholder recovery.
- Longbridge raw daily AAPL January 2000 data worked: 20 observations, including a January 3 close of 111.938. This is a useful independent historical nominal-price check. LEH.US and BBBYQ.US were invalid symbols. Complete inactive-security coverage and bulk access are not established.

- Financial Datasets `get_stock_prices` was tested on BBBYQ for September 2023 and LEH for September 1-19, 2008. Both returned an error requiring a ticker from the current SEC company-tickers list, with no OHLC or terminal-price data. These two known-delisted histories are therefore unavailable through this connector's exposed ticker validation. No new spending was requested or made. Exact responses: `.qualification/historical-source-probes/financial-datasets-delisted-probes.json`.

Raw evidence is under .qualification/historical-source-probes/: the Alpha Vantage delisted CSV, BBBYQ compact OHLCV, Longbridge AAPL bars and probe summary. These samples help now; a complete free survivor-bias-free daily dataset remains unverified.


The Ken French daily three-factor ZIP was also downloaded and inspected successfully: **26,296 daily rows from July 1, 1926 through July 31, 2026**, source vintage 202607. The archive and hash summary are saved with the connector probes. This is verified accessible history for later factor attribution, not an additional stock-price universe.


## Implemented historical nominal-price reconstruction

The separate historical normalizer now multiplies Yahoo split-adjusted OHLC by the product of reported split ratios effective strictly after each bar's session, and divides volume by that factor. Adjusted close remains unchanged for return ratios. Same-session splits do not adjust the already post-split bar. Forward and reverse splits are supported; invalid ratios are rejected. Raw captures stay immutable.

For AAPL on January 3, 2000, the four later reported splits yield a factor of 112. Yahoo close 0.9994419813 becomes 111.9375019, matching independent Longbridge raw close 111.938 within 0.001. Reconstructed volume 4,783,900 differs from Longbridge 4,784,100 by about 0.0042%, consistent with a small vendor difference. Under a USD500 balance and 20% position cap, the adjusted price falsely allowed 99 shares while the then-price permits zero. The historical path now uses the reconstructed price for sizing.

To avoid omitted later actions in old query windows, capture requests fetch through the current request time and apply an older experiment cutoff locally. Cached sources whose requested end precedes their own metadata quote date are rejected for recapture. This establishes price units using reported splits; it does not prove the event history is complete or implement a full dividend/corporate-action cash ledger.

New captures retain a split-reconstruction audit; normalized cached frames expose the same audit in frame attributes. Calendar bounds now share a stable cache across companies. A 100-history check normalized 373,041 rows in 4.64 seconds, with exact frame equality against the previous calendar bounds for three sampled instruments. Evidence: .qualification/historical-source-probes/split-reconstruction-review.json. Eight focused historical-data tests passed.
