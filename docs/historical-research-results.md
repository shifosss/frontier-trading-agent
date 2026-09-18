# First extended historical study

Completed September 18, 2026. This study substantially expands the historical evidence, but **does not qualify a strategy for live trading**. The US rolling selector loses money in the representative cost/account comparisons below. The Canadian rolling results are incomplete because held securities have missing historical marks. Those failures remain in the report instead of disappearing from the sample.

## Evidence and scope

Run: `577a24e71a844022b3ac86ca66e32c34`.
Universe snapshot: `20260918T201012673731Z-2da49ecfd9bb`.
Financial source identity: `b6d78507a6781e9a42c045192453ab93502e5a04a33b36e53fe7f7955d697037`.
Model signature: `sha256:92569a27318793ddab52f3805531f60cff95a66c667318e00382d270e92e7c29`.

| Coverage | US / USD | Canada / CAD | Total |
| --- | ---: | ---: | ---: |
| Declared stock candidates | 5,661 | 2,753 | 8,414 |
| Reference ETFs | 14 | 6 | 20 |
| Usable captured histories, including ETFs | 5,664 | 2,570 | 8,234 |
| Accepted daily bars | 19,800,186 | 8,821,064 | 28,621,250 |
| Failed captures | 11 | 189 | 200 |

Requested history starts January 2000; actual market coverage begins January 3 in the US and January 4 in Canada, ending September 18, 2026. Only 2,034 captured securities reach January 2000, and 521 have fewer than 201 observations. IPOs and available data limit each name's history. The universe is broad current membership, not a reconstructed list of all stocks that existed during those years. See [universe coverage](universe-coverage.md).

Capture failures comprise 151 invalid OHLCV series, 24 with nonpositive prices, 19 missing close arrays, and six HTTP 404 responses. Failure records are retained. Eight saved series end more than a week before the capture date. An accepted series can still contain a historical gap that later makes a particular held portfolio incomplete.

Thirty declared strategy/horizon hypotheses were evaluated at four initial cash balances and three proportional trading costs, separately in each currency: **720 fixed-rule portfolios**, **24 rolling-selection portfolios**, and **48 ETF/cash references**. These combinations are sensitivity checks, not 720 statistically independent discoveries. [Methodology](historical-research.md) describes the five rule families, market-trend variants, historical training, whole-share accounting, daily drawdowns, settlement and costs.

## US rolling selection

Selections use the preceding three years at the 100-basis-point stress cost and remain fixed for the following year. The resulting continuous test interval is **October 23, 2003 to September 18, 2026**. All 12 US rolling portfolios completed.

| Initial USD | Round-trip cost | Ending USD | Total return | Annualized return | Maximum daily drawdown |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | 0.40% | 460.53 | -7.89% | -0.36% | 20.04% |
| 500 | 1.00% | 377.58 | -24.48% | -1.22% | 26.37% |
| 100,000 | 0.40% | 91,159.43 | -8.84% | -0.40% | 21.65% |
| 100,000 | 1.00% | 71,657.03 | -28.34% | -1.44% | 31.18% |

These are total-period returns, not annual returns. The USD100,000 stress-cost portfolio exceeds the user's 30% drawdown tolerance. The account-size comparisons differ because nominal historical prices, whole shares, cash, fees and position limits affect actual sizing.

The selector chose cash in **15 of 23 test folds**. Average invested exposure was about 10.7% for USD500 and 11.7% for USD100,000. Thus its comparatively low drawdown largely reflects limited market exposure, not demonstrated profitable timing. Cash earns zero interest in this model.

At 0.40% costs, the same-period SPY reference returned +839.82% for USD500 and +1,010.93% for USD100,000, with daily drawdowns of 49.01% and 55.17%. Whole-share residual cash explains much of the size difference. SPY is a comparison, not a recommendation: its observed drawdown also exceeds the stated tolerance.

Across all 360 fixed US cost/budget combinations, 95 had positive total returns and 283 exceeded 30% drawdown. At 1.00% costs, **all 30 fixed hypotheses lost money at both USD500 and USD100,000**. At 0.40%, 11/30 and 8/30 respectively were positive. These full-history comparisons were inspected after the run and cannot establish a strategy selected without seeing the evaluation period. Only two of 12 rolling cost/budget views had positive returns; the four representative views above did not.

## Canadian results and missing evidence

All **12 Canadian rolling portfolios are incomplete**. Each reaches a held `WJX.TO` position with missing marks on June 15, 16 and 17, 2005. Full-period ending equity, return, annualized return and drawdown are withheld. A valid early prefix is not substituted for a complete 2003-2026 strategy result.

The saved XIU reference spans the full intended interval. It must not be compared as though it shares the incomplete strategy's observed duration. The interface suppresses that comparison for incomplete portfolios and identifies the missing marks.

Of 360 fixed Canadian portfolios, **263 completed and 97 were incomplete**. Among the completed rows, 135 had positive total returns and 185 exceeded 30% drawdown. The 97 incomplete attempts remain visible in the denominator; their outcomes are unknown. At 1.00% costs, starting balances of CAD500 and CAD100,000 each had six positive completed hypotheses, but respectively seven and eight incomplete hypotheses. These are CAD accounts with no currency conversion.

The 97 incomplete fixed portfolios first fail on five names: `CRON.TO` (35 portfolios, May 24, 2018), `BIG.V` (24, September 17, 2026), `WJX.TO` (24, June 15-17, 2005), `SPB.TO` (12, January 7, 2009) and `CPH.TO` (two, December 24, 2014). These are shared source gaps, not 97 independent incidents.

The retained Wajax response explicitly contains null OHLC, volume and adjusted close for all three dates. Its [2010 annual report](https://www.annualreports.com/HostedData/AnnualReportArchive/w/TSX_WJX_2010.pdf) says fund units began trading June 15, 2005 at an opening price of CAD19.40. That supports a security-history discontinuity around the income-trust conversion, but an opening quote cannot substitute for missing daily closes or a complete corporate-action ledger.

Positive surviving fixed-rule rows are exploratory leads, not grounds to select a winner while omitting failed rows or ignoring drawdowns. Missing data cannot be repaired by dropping a held stock or assigning it a convenient future return.

## A concrete lead for further research

The Canadian 20-session trend-pullback rule completed October 18, 2000 through September 18, 2026. At 0.40% costs it returned +287.23% total for CAD500 (5.36% annualized, 19.17% drawdown) and +377.45% for CAD100,000 (6.22% annualized, 16.59% drawdown). At 1.00% costs those annualized returns fell to 2.40% and 2.63%; the larger account's drawdown rose to 31.79%, beyond the stated tolerance.

This is a useful lower-turnover hypothesis to investigate, **selected retrospectively from the complete grid**. It is not a validated winner: current-membership bias, reused test periods, cost sensitivity and the failed Canadian rolling selector still apply. The full report retains every competing rule and incomplete attempt so this lead cannot replace the denominator.

## Decisions after inspecting the results

1. **Do not promote these historical candidates.** The US rolling evidence does not establish a cost-resistant advantage. The Canadian rolling evidence cannot support a full-period conclusion.
2. **Investigate source gaps and security histories before ranking Canadian winners.** Preserve original bytes and record any independently supported repair. Current membership, renamed securities and delisted prices remain material limitations.
3. **Make further strategy changes testable hypotheses.** Cost sensitivity and cash-heavy selection justify investigating turnover, execution and exposure. They do not justify simply lowering modeled costs or searching repeatedly until a positive number appears. Retain every failed experiment; reused historical periods are no longer untouched evaluation data.
4. **Continue historical development without waiting for new market observations.** The existing automation now prioritizes this work, with weekly listing/history refreshes. Prospective observations and the separate frozen paper operator remain execution evidence, not substitutes for historical study.

This model excludes monthly contributions, FX, tax, fixed commissions and interest. It uses current-vintage adjusted prices and reported split reconstruction, not a complete historical corporate-action payment ledger. It is a different research policy from the active paper operator, so these results are not the paper account's performance.

## Reproduce and inspect

Open **Strategy lab > Historical strategy development** to choose currency, account size and cost; inspect annual selections, daily-derived metrics and every fixed hypothesis. The download retains full daily equity, cash, trade batches, training candidates, source definitions and coverage.

Local evidence lives under `artifacts/historical-lab/runs/577a24e71a844022b3ac86ca66e32c34/`: `result.json` (503,091,620 bytes), per-currency results, `summary.json`, the capture index/failures, definitions and normalization audit. The JSON summary is an interface projection; the full download contains the detailed audit paths. Original raw histories are retained under `data/historical/`.

Software validation, independent reviews and browser verification are documented in [code-quality review](code-quality-review.md). Passing software tests verifies specified accounting and behavior; it does not turn negative or incomplete research into a profitable trading system.
