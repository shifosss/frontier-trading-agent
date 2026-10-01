# Completed cash-backed earnings comparison: read-only economic analysis

Attempt: `7487019bf15a4eb89e1a3702f5a0f7fb`. Definition SHA: `518039219b5b7be3935fb788f14ffacc23b90cb73033411414d7fb1d70a1859f`. Analysis verified all111 manifest-listed output files plus the terminal completion identity. No fitted model, forecast, source, fee, threshold, account path or bound code was changed or rerun.

All 10 scheduled family/year fits and all 20 accounts completed. Six accounts had positive net returns; fourteen lost. All ten Moomoo+40 bps scenarios lost. The highest whole-period percentage return was +4.6095% (USD 92.19) for the USD 2,000 S>=1 account under the proportional 40 bps scenario. None reached 5%,10%or 15% in any reported week. These are five-year repeated five-session trades, not weekly rates, and no strategy qualifies for promotion.

## Full account matrix

The new-entry window is 2021–2025; marks/settlements continue through 2026-01-16.40 bps is the frozen round-trip execution sensitivity, not measured fills. Moomoo adds the preserved current tariff counterfactual. Taxes, CAD/USD funding, fixed subscriptions, unverified venue costs and complete corporate-action cash accounting are outside net returns.

| Recipe | Starting USD | Costs | Net return | Gross P&L | Fees | Net P&L | Drawdown | Trades | Mean exposure |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| All filings | 10000 | 40 bps | -2.6468% | 1,122.61 | 1,387.28 | -264.68 | 7.5495% | 477 | 13.8549% |
| All filings | 10000 | Moomoo+40 bps | -20.8027% | 1,032.95 | 3,113.22 | -2,080.27 | 22.5635% | 469 | 13.5213% |
| All filings | 2000 | 40 bps | +2.7925% | 236.52 | 180.67 | 55.85 | 4.9567% | 354 | 8.7367% |
| All filings | 2000 | Moomoo+40 bps | -59.7063% | 150.71 | 1,344.84 | -1,194.13 | 59.8147% | 309 | 7.7023% |
| S>=1 | 10000 | 40 bps | +2.8625% | 858.95 | 572.70 | 286.25 | 4.4828% | 185 | 5.5542% |
| S>=1 | 10000 | Moomoo+40 bps | -4.6283% | 819.99 | 1,282.82 | -462.83 | 7.3264% | 183 | 5.5195% |
| S>=1 | 2000 | 40 bps | +4.6095% | 154.15 | 61.96 | 92.19 | 2.6090% | 119 | 3.0171% |
| S>=1 | 2000 | Moomoo+40 bps | -18.5839% | 140.56 | 512.24 | -371.68 | 18.5839% | 115 | 2.9027% |
| S>=1 and Q>0 | 10000 | 40 bps | -0.8403% | 113.10 | 197.13 | -84.03 | 3.7953% | 64 | 1.9600% |
| S>=1 and Q>0 | 10000 | Moomoo+40 bps | -3.8850% | 55.32 | 443.83 | -388.50 | 5.3235% | 63 | 1.9328% |
| S>=1 and Q>0 | 2000 | 40 bps | -0.1892% | 13.76 | 17.54 | -3.78 | 1.9584% | 33 | 0.8709% |
| S>=1 and Q>0 | 2000 | Moomoo+40 bps | -6.2280% | 20.03 | 144.59 | -124.56 | 6.3173% | 32 | 0.8649% |
| Ridge | 10000 | 40 bps | -0.1667% | 171.87 | 188.54 | -16.67 | 4.5037% | 63 | 1.8710% |
| Ridge | 10000 | Moomoo+40 bps | -0.0852% | 147.60 | 156.12 | -8.52 | 2.1734% | 20 | 0.7508% |
| Ridge | 2000 | 40 bps | +1.2008% | 48.68 | 24.67 | 24.02 | 2.8985% | 52 | 1.2135% |
| Ridge | 2000 | Moomoo+40 bps | -0.2462% | -0.42 | 4.50 | -4.92 | 0.4867% | 1 | 0.0256% |
| Boosted trees | 10000 | 40 bps | +1.3826% | 598.93 | 460.67 | 138.26 | 5.2789% | 150 | 4.5725% |
| Boosted trees | 10000 | Moomoo+40 bps | -6.9200% | -41.38 | 650.62 | -692.00 | 7.1336% | 89 | 2.9983% |
| Boosted trees | 2000 | 40 bps | +1.1126% | 74.86 | 52.60 | 22.25 | 3.3656% | 105 | 2.6069% |
| Boosted trees | 2000 | Moomoo+40 bps | -0.5432% | -0.26 | 10.60 | -10.86 | 0.5528% | 2 | 0.1300% |

The USD 2,000 all-filings Moomoo scenario lost 59.7063% and reached 59.8147% drawdown, breaching the 30% qualification limit. The predeclared comparison has no automatic drawdown halt; this observed breach is retained, and no halt was retrospectively inserted. All accounts ended without held or pending positions; trade gross-minus-fees and final cash P&L reconcile within USD 0.000001. There are 2,885 trade observations across overlapping account variants, not 2,885 independent opportunities.

## Weekly returns and year boundaries

Independent reconstruction used standard-library date.isocalendar, contiguous groups of saved daily NAV, and Decimal ratios from the previous week-end NAV. All 20 saved weekly series, target counts and losing streaks agree. The 264 distinct ISO weeks comprise one initialization-only partial week 2020-W 53,260 entry-only weeks, one mixed entry/tail week 2026-W 01, and two tail-only weeks. There are 261 weeks overlapping the 2021–2025 entry window. The mixed week correctly spans Dec 29–31,2025 and Jan 2,2026; no calendar-year prefix split or duplicate ISO week was found. All targets are 0/264 full-window and 0/261 entry-overlap for every account.

| Recipe | USD | Costs | Idle / losing / winning weeks | Median | Worst | Best | Longest losing run |
|---|---:|---|---:|---:|---:|---:|---:|
| All filings | 10000 | 40 bps | 48 / 127 / 89 | +0.0000% | -2.2482% | +1.8622% | 5 |
| All filings | 10000 | Moomoo+40 bps | 51 / 138 / 75 | -0.0179% | -2.3087% | +1.7836% | 7 |
| All filings | 2000 | 40 bps | 73 / 109 / 82 | +0.0000% | -2.4153% | +1.4734% | 6 |
| All filings | 2000 | Moomoo+40 bps | 84 / 161 / 19 | -0.1522% | -2.9231% | +0.8167% | 8 |
| S>=1 | 10000 | 40 bps | 133 / 72 / 59 | +0.0000% | -1.2578% | +1.5562% | 4 |
| S>=1 | 10000 | Moomoo+40 bps | 136 / 83 / 45 | +0.0000% | -1.4300% | +1.4425% | 6 |
| S>=1 | 2000 | 40 bps | 170 / 51 / 43 | +0.0000% | -1.0130% | +1.1149% | 5 |
| S>=1 | 2000 | Moomoo+40 bps | 170 / 80 / 14 | +0.0000% | -1.3647% | +0.7729% | 6 |
| S>=1 and Q>0 | 10000 | 40 bps | 197 / 40 / 27 | +0.0000% | -1.2214% | +0.8577% | 4 |
| S>=1 and Q>0 | 10000 | Moomoo+40 bps | 200 / 46 / 18 | +0.0000% | -1.2497% | +0.8093% | 4 |
| S>=1 and Q>0 | 2000 | 40 bps | 228 / 20 / 16 | +0.0000% | -0.5868% | +0.5348% | 4 |
| S>=1 and Q>0 | 2000 | Moomoo+40 bps | 229 / 26 / 9 | +0.0000% | -0.9575% | +0.4549% | 3 |
| Ridge | 10000 | 40 bps | 217 / 24 / 23 | +0.0000% | -1.1667% | +0.8985% | 3 |
| Ridge | 10000 | Moomoo+40 bps | 238 / 16 / 10 | +0.0000% | -1.2030% | +0.5851% | 3 |
| Ridge | 2000 | 40 bps | 222 / 23 / 19 | +0.0000% | -1.0957% | +1.6400% | 3 |
| Ridge | 2000 | Moomoo+40 bps | 262 / 2 / 0 | +0.0000% | -0.1334% | +0.0000% | 2 |
| Boosted trees | 10000 | 40 bps | 161 / 56 / 47 | +0.0000% | -1.5143% | +2.5986% | 6 |
| Boosted trees | 10000 | Moomoo+40 bps | 197 / 40 / 27 | +0.0000% | -1.4322% | +1.2843% | 6 |
| Boosted trees | 2000 | 40 bps | 178 / 48 / 38 | +0.0000% | -0.9610% | +1.1715% | 4 |
| Boosted trees | 2000 | Moomoo+40 bps | 260 / 4 / 0 | +0.0000% | -0.4384% | +0.0000% | 2 |

## Annual stability

Each row preserves the five annual returns; initialization 2020 and liquidation-tail 2026 returns are zero in these completed paths. Idle years are not evidence of stable active profitability.

| Recipe | USD | Costs | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---|---:|---:|---:|---:|---:|
| All filings | 10000 | 40 bps | -0.4461% | +0.7855% | -1.6998% | -1.7968% | +0.5112% |
| All filings | 10000 | Moomoo+40 bps | -4.1504% | -2.5731% | -4.9758% | -6.1014% | -4.9510% |
| All filings | 2000 | 40 bps | +1.7308% | +1.9081% | -2.4497% | -0.3163% | +1.9642% |
| All filings | 2000 | Moomoo+40 bps | -12.6583% | -12.4438% | -17.4047% | -20.2236% | -20.0354% |
| S>=1 | 10000 | 40 bps | +2.6914% | +0.7301% | -3.7894% | +0.8707% | +2.4651% |
| S>=1 | 10000 | Moomoo+40 bps | +0.6273% | -0.6952% | -4.9214% | -0.1400% | +0.5215% |
| S>=1 | 2000 | 40 bps | +0.8201% | +0.7414% | -2.1144% | +2.6227% | +2.5307% |
| S>=1 | 2000 | Moomoo+40 bps | -5.8496% | -3.8289% | -4.9120% | -2.7201% | -2.7936% |
| S>=1 and Q>0 | 10000 | 40 bps | -0.2204% | -0.2185% | -2.3292% | +1.6279% | +0.3380% |
| S>=1 and Q>0 | 10000 | Moomoo+40 bps | -1.2934% | -0.3018% | -2.9256% | +1.3053% | -0.6837% |
| S>=1 and Q>0 | 2000 | 40 bps | -0.7942% | -0.1406% | -0.7652% | +0.9543% | +0.5687% |
| S>=1 and Q>0 | 2000 | Moomoo+40 bps | -2.9887% | -0.3495% | -1.4570% | -0.4811% | -1.0901% |
| Ridge | 10000 | 40 bps | +0.7220% | +0.0000% | -1.5918% | -0.9770% | +1.7147% |
| Ridge | 10000 | Moomoo+40 bps | +0.3956% | +0.0000% | -0.9755% | +0.0000% | +0.5015% |
| Ridge | 2000 | 40 bps | +0.6149% | +0.0000% | +0.1036% | -0.7846% | +1.2729% |
| Ridge | 2000 | Moomoo+40 bps | -0.2462% | +0.0000% | +0.0000% | +0.0000% | +0.0000% |
| Boosted trees | 10000 | 40 bps | +0.7054% | -0.8729% | -1.3010% | +1.5260% | +1.3511% |
| Boosted trees | 10000 | Moomoo+40 bps | +0.2273% | -0.2746% | -4.2969% | -0.1910% | -2.5080% |
| Boosted trees | 2000 | 40 bps | +0.3360% | -0.1319% | -1.0449% | +1.0332% | +0.9298% |
| Boosted trees | 2000 | Moomoo+40 bps | +0.0000% | +0.0000% | -0.5432% | +0.0000% | +0.0000% |

## Model samples, warnings and source denominators

Every fit exceeded the frozen 256-row/25-issuer fitting and 64-row/16-issuer calibration floors. Both families used identical retained samples in each year. All fit and prediction warning lists are empty, and no family/year abstained for insufficient samples or fitting failure.

| Test year | Fit rows / issuers | Calibration rows / issuers | Eligible predictions / issuers | Original test-clock rows |
|---|---:|---:|---:|---:|
| 2021 | 479 / 77 | 211 / 74 | 208 / 71 | 253 |
| 2022 | 690 / 82 | 208 / 71 | 209 / 71 | 264 |
| 2023 | 898 / 82 | 209 / 71 | 210 / 75 | 264 |
| 2024 | 1107 / 83 | 210 / 75 | 228 / 79 | 266 |
| 2025 | 1317 / 87 | 228 / 79 | 232 / 81 | 269 |

All 4,057 originals and all 100 requested issuers remain. Each family generated 1,087 eligible test forecasts; none of those had a missing joint test label.190 source-incomplete originals and 423 calendar-unavailable rows remain among the 613 unassigned decision-clock records. Across all retained years, missing causal-feature reasons overlap:1,721 missing S,1,182 missing Q,2,047 unavailable source eligibility, and 4 missing prior-return/4 missing activity windows. No future label failure removed a test candidate. All issuer/year rows, including zero-event years, remain in report.json.

There are 14,912 overlapping scheduled label-interval pairs across test years, concentrated by reporting season. No same-issuer overlapping pair was found, but repeated issuers and cross-issuer calendar overlap remain; these are not independent trial counts. No confidence claim based on IID event sampling is made.

## Forecast errors and calibration

Pooled errors below are weighted by each fold's eligible event count (1,087 per family/head). MAE is percentage points of the five-session fractional target; training-mean baselines are fitted only on the corresponding historical fitting rows and evaluated on identical forecast rows. Lower is better.

| Family | Head | Raw MAE | Corrected MAE | Fit-mean MAE | Corrected MSE beats mean in years |
|---|---|---:|---:|---:|---:|
| Ridge | return_5 | 4.0855 | 4.0899 | 4.0504 | 2/5 |
| Ridge | downside_5 | 2.5005 | 2.6054 | 2.4363 | 2/5 |
| Boosted trees | return_5 | 4.1841 | 4.1717 | 4.0504 | 1/5 |
| Boosted trees | downside_5 | 2.5827 | 2.6022 | 2.4363 | 1/5 |

Both corrected families are worse than their fitting-mean baseline on pooled MAE and MSE for both heads. Ridge return MAE 4.0899 pp versus 4.0504 pp baseline; boosted return 4.1717 pp. Corrected downside MAE is about 2.60 pp versus 2.4363 pp baseline. Correction improved return mean bias, but did not establish useful ranking or economic value; downside correction worsened pooled squared error for both families.

| Family | Year | Head | Raw MAE pp | Corrected MAE pp | Fit-mean MAE pp | Corrected MSE vs mean |
|---|---:|---|---:|---:|---:|---:|
| Ridge | 2021 | return_5 | 3.3463 | 3.1542 | 3.2074 | -0.808% |
| Ridge | 2021 | downside_5 | 2.1976 | 2.5763 | 2.2262 | +10.012% |
| Boosted trees | 2021 | return_5 | 3.3657 | 3.2760 | 3.2074 | +4.951% |
| Boosted trees | 2021 | downside_5 | 2.2248 | 2.5350 | 2.2262 | +7.847% |
| Ridge | 2022 | return_5 | 4.3619 | 4.4549 | 4.2457 | +9.769% |
| Ridge | 2022 | downside_5 | 3.0612 | 3.2937 | 2.6969 | +15.222% |
| Boosted trees | 2022 | return_5 | 4.4625 | 4.4767 | 4.2457 | +8.466% |
| Boosted trees | 2022 | downside_5 | 3.2668 | 3.1334 | 2.6969 | +10.239% |
| Ridge | 2023 | return_5 | 3.6332 | 3.8341 | 3.6227 | +0.260% |
| Ridge | 2023 | downside_5 | 2.1795 | 2.1062 | 2.1447 | -5.286% |
| Boosted trees | 2023 | return_5 | 3.7701 | 3.9293 | 3.6227 | +7.743% |
| Boosted trees | 2023 | downside_5 | 2.2554 | 2.2037 | 2.1447 | +12.252% |
| Ridge | 2024 | return_5 | 4.6093 | 4.6157 | 4.5409 | +1.931% |
| Ridge | 2024 | downside_5 | 2.6600 | 2.6159 | 2.6786 | +1.406% |
| Boosted trees | 2024 | return_5 | 4.6408 | 4.6403 | 4.5409 | +0.209% |
| Boosted trees | 2024 | downside_5 | 2.6536 | 2.5965 | 2.6786 | -1.524% |
| Ridge | 2025 | return_5 | 4.3937 | 4.3145 | 4.5354 | -8.889% |
| Ridge | 2025 | downside_5 | 2.4005 | 2.4530 | 2.4156 | -3.035% |
| Boosted trees | 2025 | return_5 | 4.5930 | 4.4589 | 4.5354 | -4.425% |
| Boosted trees | 2025 | downside_5 | 2.5140 | 2.5502 | 2.4156 | +5.538% |

Calibration-only bin counts and realized target means show unstable discrimination. In 2021 Ridge's top return bin held only 4 test events; in 2024 its top bin averaged−3.119% while lower bins were mostly positive.2022 downside forecasts shifted almost entirely into the highest prior-calibration bin (Ridge 208/209, boosted 192/209);2023 shifted mostly into the lowest (191/210 and 196/210). This is evidence of year-to-year distribution/calibration instability, not permission to alter thresholds or drop unfavorable bins. Full edges, counts, target/prediction means, errors and zero-count bins are preserved in report.json.

## Selection, costs and concentration

Under the primary USD 10,000 proportional 40 bps case, all-filings supplies 1,087 causal candidates and 477 trades; S>=1 reduces this to 220 candidates and 185 trades; adding Q>0 leaves 68 candidates and 64 trades. The Q filter did not improve economics: net changes from+USD 286.25 to−USD 84.03, and positive entry years fall from 4/5 to 2/5. This does not prove cash backing is universally uninformative; it rejects this fixed confirmation recipe on this cohort/timing/cost convention.

The learned models forecast every 1,087 eligible events. At USD 10,000, recorded planner evaluations reject 988 Ridge and 819 boosted candidates for nonpositive utility, producing 63 and 150 completed trades; affordability/ATR rejects only 16 planner evaluations for each. Their mean exposures are 1.8710% and 4.5725%, and 217/264 or 161/264 weeks have exactly zero account return. Thus lack of money alone is not the main obstacle atUSD 10,000; weak estimated utility and sparse reporting events dominate. Planner evaluation counts are not asserted to be a disjoint unique-event census.

Moomoo+40 bps at USD 2,000 yields only one Ridge and two boosted trades, with 262 or 260 zero-return weeks. Whole-share affordability and per-order fees materially affect the attainable opportunity set. AtUSD 10,000, S>=1 produces grossUSD 858.95 but modeled costsUSD 572.70; boosted trees grossUSD 598.93 but costsUSD 460.67. These gross profits are not net tradable edge. The Moomoo cases use different selected/sized trades, so subtracting a fee delta from the proportional path would not reproduce them.

| Positive account | USD | Net P&L | Largest issuer contribution | Share of net gain |
|---|---:|---:|---|---:|
| All filings / 40 bps | 2000 | 55.85 | KBH 28.37 | 50.79% |
| S>=1 / 40 bps | 10000 | 286.25 | WDC 141.42 | 49.40% |
| S>=1 / 40 bps | 2000 | 92.19 | BJRI 18.25 | 19.79% |
| Ridge / 40 bps | 2000 | 24.02 | WDC 25.43 | 105.88% |
| Boosted trees / 40 bps | 10000 | 138.26 | VSH 120.24 | 86.97% |
| Boosted trees / 40 bps | 2000 | 22.25 | VSH 21.44 | 96.34% |

These contribution ratios describe concentration, not corrected accounts with an issuer removed. VSH supplies 86.97% of theUSD 10,000 boosted gain and 96.34% of itsUSD 2,000 gain; WDC supplies 49.40% of theUSD 10,000 S>=1 gain and more than 100% of the smallUSD 2,000 Ridge gain. No issuer was pruned or replaced. Full top/bottom trades and issuer totals are retained in report.json.

The costless fully invested SPY adjusted-price reference gains 98.1788% with 24.4964% maximum drawdown over the identical 2020-12-31–2026-01-16 marks; cash with zero interest returns 0%. This is an exposure-different reference, not a feasible fee/dividend/cash-account replication or a new recommendation. Every active path trails this SPY reference, and fourteen also trail zero-interest cash.

## Next research decision

Do not promote a model, increase risk to force weekly targets, weaken utility thresholds, resweep presets, or rerun the unchanged comparison. The completed evidence separates four problems: genuinely weak forecast/ranking evidence versus training means, unstable transferred calibration, modeled small-account execution costs, and low exposure from a sparse filing event stream. Missing test labels and failed fits did not cause these economic outcomes. Source coverage/current-member and adjusted-price accounting limits remain independently material.

A useful next step is a source-only novelty/timing audit using already preserved SEC discovery roots/history for the same 100 issuers: determine whether an original 8-K Item 2.02 candidate precedes each 10-Q, preserve every unmatched/ambiguous/late case, and compare metadata coverage before requesting new documents. Freeze matching rules and all requested events before any new outcome comparison. Do not choose issuers or dates by returns.

An earlier 8-K timestamp, same CIK or Item 2.02 tag alone does not prove that the same fiscal period or cash-flow/earnings components were disclosed. Validate original document/exhibit content and period linkage before calling it an earnings release. Crucially, an earlier release cannot inherit S/Q from the later 10-Q: an earlier decision may use only facts actually present and public at that earlier time. Earlier disclosure is a hypothesis to verify, not an established explanation or an assumed rescue. Keep this 10-Q study intact; no new source audit, earlier-time strategy or threshold variant was executed by this analysis.
