# Daily multi-model historical research results

Completed 2026-09-19 at 19:26:08 UTC. Run `814780d48b4141b9a82a3fb917d1b85a`. This is the first full run of the [declared model comparison](superpowers/plans/2026-09-19-multi-model-study.md).

**This run does not establish a strategy ready for real-money trading.** Of 720 declared accounts, 569 completed and 151 became incomplete because required prices were missing. Among the complete accounts, 59 gained money and 510 lost money; none beat its matched equity ETF in cumulative return. At the 2,000-native-unit / 40-bps reference setting, all 21 US learned-model/hold combinations lost money. Smaller losses than the rule controls are an improvement in the research comparison, not a demonstrated trading edge.

The Canadian five-session histogram-gradient-boosting account shows a positive full-period result, but its recent returns are weak and a large winning trade contains unresolved historical share/price continuity. That gain is not verified economic alpha. The saved result is preserved, with no silent price repair or subtraction of the questionable trade.

## Scope and interpretation

The run reused the original `90af4c840aad48f7ab58fba7a682f96a` capture, cutoff **2026-09-18T20:43:15.256344+00:00**, without new source repair: **8,234 usable histories, 28,621,250 daily observations**, from 8,434 requested instruments. The original 200 failed captures remain recorded. Available history starts in 2000; individual instruments have shorter histories. Current membership and current adjusted-data vintage do not reconstruct the securities available to an investor on every historical date.

Twenty strategy variants × 1/3/5-session holds × 2,000/10,000 native balances × 20/40/100-bps proportional-cost settings × US/Canadian books produce 720 continuous account attempts, plus 24 matched ETF/cash references. Seven learned variants comprise Ridge, ExtraTrees, HistGradientBoosting, shared-hidden six-output MLP, equal ensemble, calibrated ensemble and diversified calibrated ensemble. Thirteen rule controls use identical trading dates and cash-account mechanics.

Each market has 23 chronological refits: 504 prior sessions fit the models; the next 252 calibrate weights; the following 252 test them. Labels crossing fit/calibration/test boundaries are purged. Screening occurs every completed session; entries fill at the next close and independent positions exit after 1, 3 or 5 sessions. Folds close positions, with settled and unsettled cash carried into the next fold. Whole-share sizing, five positions, 20% entry caps and dated settlement are modeled.

**These balances are separate simulated accounts, not the owner’s current cash or monthly contribution schedule.** The 40-bps reference is one declared sensitivity setting, not a measured Wealthsimple/moomoo all-in fee. None of the three settings includes fixed broker charges, FX, subscriptions, taxes, interest or contributions. Cash earns zero. A 30% observed-drawdown comparison is descriptive; it does not enforce a future loss cap.

## Every account group

Each row contains 60 attempted accounts: 21 learned and 39 rule controls. Positive and drawdown counts use complete paths only; failures stay in the attempted denominator. Repeated models and overlapping history are not independent statistical tests.

| Market | Native start | Cost setting (bps) | Complete / 60 | Incomplete | Positive / complete | Positive learned / 21 attempted | Positive rules / 39 attempted | Complete paths above 30% drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| USD | 2,000 | 20 | 60 | 0 | 7 | 3 | 4 | 52 |
| USD | 2,000 | 40 | 58 | 2 | 0 | 0 | 0 | 54 |
| USD | 2,000 | 100 | 55 | 5 | 0 | 0 | 0 | 54 |
| USD | 10,000 | 20 | 60 | 0 | 7 | 3 | 4 | 54 |
| USD | 10,000 | 40 | 59 | 1 | 1 | 1 | 0 | 55 |
| USD | 10,000 | 100 | 58 | 2 | 0 | 0 | 0 | 57 |
| CAD | 2,000 | 20 | 34 | 26 | 18 | 9 | 9 | 17 |
| CAD | 2,000 | 40 | 39 | 21 | 3 | 2 | 1 | 27 |
| CAD | 2,000 | 100 | 37 | 23 | 0 | 0 | 0 | 29 |
| CAD | 10,000 | 20 | 33 | 27 | 19 | 9 | 10 | 17 |
| CAD | 10,000 | 40 | 36 | 24 | 3 | 3 | 0 | 25 |
| CAD | 10,000 | 100 | 40 | 20 | 1 | 1 | 0 | 33 |

Across all settings, 474 of the 569 complete paths exceeded 30% drawdown. Thirty-seven complete paths were positive with drawdown at or below 30%; that screen does not resolve data quality, costs or selection bias. None of the complete paths was entirely cash, although 182 averaged less than 10% invested exposure. Their lower market exposure helps explain some lower drawdowns.

Of 240 strategy/hold/balance/market groups, 168 completed at all three cost settings; none was profitable at all three. The other 72 groups have incomplete cost comparisons. This is evidence of sensitivity, **not a requirement that every strategy must survive 100 bps regardless of the actual broker**. Realistic execution costs must be measured before a promotion decision.

## Primary reference: 2,000 native units and 40 bps

Each cell below is **cumulative account return / maximum drawdown**. Incomplete means the full-period metrics are unavailable; an observed prefix is not substituted. All 20 variants and three holds are included. The [720-account CSV](../.qualification/multi-model-economics-full/all_accounts.csv) contains trade counts, fees, expectancy, exposure, turnover, weekly/monthly results and exact failures for every setting.

### USD

Evaluation: **2003-10-23 through 2026-09-18**. Matched SPY buy-and-hold: **997.28% cumulative return**, 54.71% drawdown; zero-interest cash: 0%. These ETF paths carry substantially more exposure and exceed the owner’s 30% loss tolerance; their returns are comparison references, not a recommended allocation.

| Strategy | 1 session: return / drawdown | 3 sessions: return / drawdown | 5 sessions: return / drawdown |
| --- | ---: | ---: | ---: |
| momentum | -98.74% / 98.77% | -87.74% / 88.71% | -63.02% / 64.88% |
| trend pullback | -98.46% / 98.46% | -89.82% / 89.94% | -43.37% / 54.07% |
| mean reversion | -97.32% / 97.33% | -90.22% / 90.62% | -64.03% / 69.10% |
| breakout | -98.29% / 98.32% | -87.41% / 88.02% | -80.04% / 81.51% |
| momentum 12 1 | -98.81% / 98.82% | -80.94% / 82.94% | -52.75% / 60.48% |
| momentum market trend | -98.56% / 98.60% | -88.06% / 88.86% | -60.77% / 64.45% |
| trend pullback market trend | -98.24% / 98.24% | -84.60% / 84.86% | -49.77% / 54.00% |
| mean reversion market trend | -96.84% / 96.85% | -86.62% / 87.08% | -59.38% / 66.48% |
| breakout market trend | -97.90% / 97.93% | -81.07% / 81.60% | -68.84% / 70.48% |
| momentum 12 1 market trend | -98.37% / 98.39% | -65.88% / 69.72% | -37.57% / 56.69% |
| relative reversal 2 | incomplete | -80.64% / 82.29% | -52.24% / 64.35% |
| relative reversal 5 | incomplete | -75.69% / 79.96% | -35.14% / 50.67% |
| relative volume continuation 5 | -98.47% / 98.51% | -86.79% / 88.27% | -66.56% / 69.92% |
| ridge | -69.37% / 69.60% | -56.75% / 60.01% | -50.82% / 58.30% |
| extra trees | -21.02% / 23.28% | -15.63% / 24.81% | -1.97% / 18.25% |
| hist gradient boosting | -51.25% / 54.87% | -36.86% / 42.98% | -5.85% / 29.93% |
| multi head mlp | -95.26% / 95.36% | -74.28% / 75.61% | -74.37% / 77.60% |
| equal ensemble | -64.75% / 65.28% | -53.74% / 57.20% | -59.63% / 62.80% |
| calibrated ensemble | -56.64% / 57.26% | -51.37% / 55.01% | -46.91% / 53.02% |
| diversified ensemble | -60.07% / 60.67% | -49.20% / 53.00% | -46.31% / 52.55% |

### CAD

Evaluation: **2003-10-22 through 2026-09-18**. Matched XIU.TO buy-and-hold: **771.58% cumulative return**, 47.77% drawdown; zero-interest cash: 0%. These ETF paths carry substantially more exposure and exceed the owner’s 30% loss tolerance; their returns are comparison references, not a recommended allocation.

| Strategy | 1 session: return / drawdown | 3 sessions: return / drawdown | 5 sessions: return / drawdown |
| --- | ---: | ---: | ---: |
| momentum | incomplete | incomplete | incomplete |
| trend pullback | -97.84% / 97.86% | incomplete | -24.11% / 51.98% |
| mean reversion | incomplete | -73.67% / 80.49% | -39.22% / 61.28% |
| breakout | incomplete | incomplete | incomplete |
| momentum 12 1 | incomplete | incomplete | incomplete |
| momentum market trend | incomplete | incomplete | -51.77% / 58.82% |
| trend pullback market trend | -97.17% / 97.21% | incomplete | -29.42% / 48.93% |
| mean reversion market trend | incomplete | -70.63% / 77.71% | -34.14% / 56.20% |
| breakout market trend | incomplete | incomplete | -72.93% / 75.04% |
| momentum 12 1 market trend | incomplete | incomplete | 31.25% / 33.50% |
| relative reversal 2 | -98.33% / 98.44% | -78.13% / 86.40% | -38.01% / 58.14% |
| relative reversal 5 | -98.25% / 98.53% | -67.90% / 78.96% | -50.54% / 67.18% |
| relative volume continuation 5 | incomplete | incomplete | -41.70% / 46.02% |
| ridge | -16.18% / 20.82% | -46.98% / 47.79% | -15.29% / 40.87% |
| extra trees | -15.66% / 20.63% | -19.15% / 22.27% | -5.28% / 16.26% |
| hist gradient boosting | -30.24% / 32.05% | -6.39% / 21.98% | 38.38% / 22.77% |
| multi head mlp | -90.90% / 90.94% | -58.03% / 66.28% | 12.82% / 40.70% |
| equal ensemble | -13.12% / 16.70% | -30.78% / 36.73% | -10.84% / 29.43% |
| calibrated ensemble | -34.21% / 34.41% | -11.92% / 19.12% | -19.09% / 27.71% |
| diversified ensemble | -32.98% / 33.12% | -12.49% / 18.02% | -17.52% / 27.47% |

## Learned models versus controls, exposure and time stability

At the primary setting, learned models beat matched rule controls in 229 of 259 available US pair comparisons and 120 of 126 Canadian comparisons. All 546 declared primary pairs remain in the [full pair CSV](../.qualification/multi-model-economics-full/all_learned_rule_pairs.csv), including unavailable comparisons caused by incomplete paths. Beating a losing control is not evidence of positive expected returns. None of the complete accounts beats its matched ETF in cumulative return.

Both calibrated and diversified ensembles lose money at all three primary holds in both markets. Combining models and enforcing a correlation ceiling did not establish net profitability. The reference ExtraTrees five-session accounts lost 1.97% in USD and 5.28% in CAD while averaging only 4.78% and 3.80% invested, respectively; their relatively low drawdowns should not be interpreted as strong risk-adjusted performance without that cash context.

All complete accounts span 24 calendar-year segments, including partial 2003 and 2026, and 23 test folds. Every saved year and fold is retained in the [year CSV](../.qualification/multi-model-economics-full/all_years.csv) and [fold CSV](../.qualification/multi-model-economics-full/all_folds.csv). Incomplete-account fold prefixes are explicitly labeled and are not treated as full-period performance.

### Canadian HistGradientBoosting five-session observation

The primary account ends at C$2,767.60: **38.38% cumulative return, 1.43% CAGR, 22.77% drawdown** over nearly 23 years. It completed 2,158 trades, with C$0.356 mean net P&L per trade, 47.03% winning trades, 9.67% mean invested exposure and 85.39% mean settled cash. These are retrospective selected results, not a forecast or promotion.

**Material unresolved source event:** its largest positive TPX-B.TO trade, February 7–14, 2005, uses five shares and a price move from C$34.59 to C$87.01, producing approximately C$260.884 net P&L, about 34% of this account’s total net gain. The retained provider series jumps approximately 177.0455% on February 8 in both nominal and adjusted prices, with an approximately constant 0.3176047 adjusted-to-reconstructed-nominal ratio and no nearby provider-reported action. Current ticker/company mapping does not establish dated share continuity. The [source-tail evidence](../.qualification/multi-model-review/cad-hgb5-source-tail.json) and [SEC-based continuity review](tpx-source-continuity.md) identify material share-conversion and cash-entitlement terms. The predecessor share class, provider date mapping and cash flows remain unreconciled; a simple split-factor repair is not established. No correction has been inserted into this frozen run.

Even taking the saved series literally, only 14/24 calendar-year segments and 13/23 folds were positive. The worst calendar year returned -16.16%. Profitable weeks were 33.19% and profitable months 41.67%; the worst month was -9.80%.

| Subperiod, including 2026 through September 18 | Compounded account return |
| --- | ---: |
| 2010–2026 YTD | 0.70% |
| 2017–2026 YTD | -17.62% |
| 2020–2026 YTD | -14.87% |

The five largest saved net symbol contributors (TPX-B.TO, WEED.TO, HUT.TO, TXP.TO, TCW.TO) sum to 103.94% of total net gain; the remaining symbols collectively detracted. This uses saved cumulative symbol attribution, not five individual trades. The overall gain is concentrated and largely predates 2010.

| CAD starting cash | Cost setting (bps) | Cumulative return | Drawdown | Trades | Mean invested |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2,000 | 20 | 32.82% | 17.59% | 2,486 | 12.24% |
| 2,000 | 40 | 38.38% | 22.77% | 2,158 | 9.67% |
| 2,000 | 100 | -3.62% | 35.03% | 1,450 | 4.93% |
| 10,000 | 20 | 31.30% | 18.70% | 2,490 | 12.85% |
| 10,000 | 40 | 36.80% | 23.69% | 2,165 | 10.12% |
| 10,000 | 100 | -5.01% | 34.75% | 1,461 | 5.25% |

The 40-bps path can exceed the 20-bps path because the modeled cost also changes the learned entry threshold, rankings, fills and subsequent account trajectory. These are different executed paths, not a fee-only subtraction from identical trades. It would be invalid to select the favorable cost setting or interpolate a break-even fee from these outcomes. The 100-bps losses and higher drawdowns are sensitivity evidence; they are not asserted to be the owner’s actual brokerage cost.

## Forecast calibration and convergence

Each cell counts folds, out of 23. A fallback means no base model improved return-MSE over the training-mean baseline for that horizon, so the ensemble used equal weights. Return prediction accuracy and downside prediction accuracy are different diagnostics; neither establishes trading profit.

| Market | Hold | Equal-weight fallbacks | Ridge return-MSE wins | ExtraTrees wins | HGB wins | MLP wins |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CAD | 1 | 15/23 | 1/23 | 7/23 | 1/23 | 1/23 |
| CAD | 3 | 15/23 | 1/23 | 8/23 | 1/23 | 0/23 |
| CAD | 5 | 16/23 | 1/23 | 7/23 | 2/23 | 0/23 |
| USD | 1 | 18/23 | 1/23 | 5/23 | 1/23 | 0/23 |
| USD | 3 | 18/23 | 3/23 | 4/23 | 2/23 | 0/23 |
| USD | 5 | 18/23 | 3/23 | 5/23 | 2/23 | 0/23 |

All 46 MLP fits retained a convergence warning after reaching the declared 60-iteration limit: 23 US and 23 Canadian. No warning was discarded and no failed model was silently removed. This limits conclusions about that fixed training configuration; it does not show that neural prediction is universally ineffective. The UI now renders the warning’s model, category and message rather than converting the structured object to an unreadable string.

The run recorded 8,521,800 US and 1,171,421 Canadian eligible test forecasts. These are stock/session processing counts, not unique independent observations. Rolling fitting and calibration reuse historical data; the summary retains sample sizes, purged/excluded-label counts, sample digests and per-head MSE/weights.

## Missing paths and source limitations

USD: 350 complete and 10 incomplete accounts. CAD: 219 complete and 141 incomplete. Required price failures below invalidate the entire affected account result. Counts are failure occurrences, so one account can contribute more than one symbol/reason. The listing/capture failures are an additional limitation, not included in these account-path counts.

| Required missing observation | Account-path occurrences |
| --- | ---: |
| `ARX.TO:2026-07-20:entry` | 2 |
| `ARX.TO:2026-07-20:mark` | 1 |
| `AUXX.V:2026-09-17:mark` | 15 |
| `BEP-UN.TO:2026-09-17:mark` | 1 |
| `BIG.V:2026-09-17:mark` | 1 |
| `BIP-UN.TO:2026-09-17:mark` | 1 |
| `CPH.TO:2014-12-24:entry` | 1 |
| `CPH.TO:2014-12-24:mark` | 16 |
| `CRON.TO:2018-05-24:mark` | 4 |
| `CTC-A.TO:2006-05-08:mark` | 2 |
| `DIR-UN.TO:2026-09-17:entry` | 1 |
| `HG.CN:2026-09-17:mark` | 2 |
| `KMP-UN.TO:2026-09-17:mark` | 1 |
| `LGN.V:2026-09-17:entry` | 8 |
| `MAXX.CN:2026-09-17:mark` | 3 |
| `MGA.TO:2006-09-06:mark` | 1 |
| `PHOS.CN:2026-09-17:mark` | 11 |
| `REI-UN.TO:2026-09-17:mark` | 3 |
| `SPB.TO:2009-01-07:entry` | 18 |
| `TECK-B.TO:2026-09-17:mark` | 1 |
| `TFII.TO:2008-05-20:entry` | 7 |
| `TNMG:2026-09-08:entry` | 3 |
| `TNMG:2026-09-08:mark` | 7 |
| `WJX.TO:2005-06-15:entry` | 20 |
| `WJX.TO:2005-06-15:mark` | 23 |
| `WTE.TO:2012-07-05:entry` | 6 |

No WJX issuer overlay or other historical repair was applied to this comparison. It intentionally retains the same raw sources as the earlier study. Future source repairs should be separately versioned and rerun with all variants; a favorable repair must not be applied only to a selected winner.

Provider-reported split reconstruction supports nominal sizing, but synthetic adjusted-return marks are not a complete issuer-action/share-conversion, cash-distribution or tax ledger. Hash agreement and arithmetic reconciliation verify what was calculated from the saved data; they do not establish economic continuity of every ticker. Current-member survivorship, ticker history, revised data and missing observations remain material.

## Verification and reproducibility

The independent [compact-result analyzer](../.qualification/analyze_multi_model_economics.py) reconciled ending equity, realized net P&L, yearly and fold compounding, trade counts and holding clocks for all complete accounts. It retained all 720 attempted rows and correctly withheld incomplete profitability. Its deliberate-error self-checks verify that leaked incomplete metrics and corrupted fold returns are detected.

The separate [full audit](../.qualification/multi-model-review/full-audit-814780d48b4141b9a82a3fb917d1b85a.json) passed: 8,234 raw-source hashes; 744 full/compact account/reference rows; all 42 retained learned trade ledgers; and 192,113 source-priced completed trades across 4,463 source symbols. It checked fees, whole shares, 20% entry caps and settlement across folds. This audit shares the source adjustment normalizer; it does not independently establish complete issuer actions. Sample digests and purge boundaries were verified, but exact sampled-row membership was not reconstructed.

The [actual completed UI check](../.qualification/historical-ui/multi-model-actual-completed-report.json) passed 48 filter contexts across 1440, 768, 390 and 320 pixel widths, including all 720 account rows at each width, matching references, incomplete cases, structured warnings and forecasts. A one-byte ranged request verified the 691,108,930-byte evidence download without fetching the whole file. No POST, new study, paper mutation or live broker action was performed by these checks.

Artifacts:

- [Frozen run definition](../artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/definition.json), [compact result](../artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/summary.json) and [full study result](../artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/result.json).
- [All 720 accounts](../.qualification/multi-model-economics-full/all_accounts.csv), [all yearly rows](../.qualification/multi-model-economics-full/all_years.csv), [all fold rows](../.qualification/multi-model-economics-full/all_folds.csv), [all 3,276 learned/rule comparisons](../.qualification/multi-model-economics-full/all_learned_rule_pairs.csv).
- [Economic analysis](../.qualification/multi-model-economics-full/analysis.json) and [compact economic summary](../.qualification/multi-model-economics-full/summary.json).

Frozen identities:

- Historical financial code: `498b4f6415923abcedb9987cb5a05caf009bfcf5bd10a61e43b3b8f4d5e0bc91`.
- Data-source identity: `930923cbbab8c7152b769f76034a7ef502a0fbc163c9c0344be2702a2a19379d`.
- Capture-index SHA256: `85202315acbf06dbdde838c98077bea198177617b0ef88a7584a7a9b1a0d6966`.
- Model configuration signature: `sha256:1f9b0e8c467905c15b549eac09cf474ff2cb7b57f62aa81b9c6c9f72dbc99cff`.
- Published summary SHA256: `107195ef703901cf3b5dc4971579c02e046cbe6a67c0beddaca965b7b236751d`.
- Analysis script SHA256: `b096d86ec028647eab8758b4cfdcf97051db255082c24c12442465f7d9f6f883`.

The definition also freezes Python 3.13.7, NumPy 2.5.3, pandas 3.0.6, scikit-learn 1.7.2, SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.7.0, and dependency-manifest hashes. Results are reproducible to floating tolerance within the declared environment, not promised bitwise identical across parallel math libraries.

## Research decision

Keep this study as a completed, reproducible comparison and preserve the negative evidence. It supports further historical development, not automatic paper/live promotion. Next experiments should be separately declared around verified issuer continuity, actual execution-cost measurement, recent-period robustness and targeted model/feature or refit changes. The current fixed-configuration MLP and ensembles have not earned operational promotion; a favorable historical row is insufficient. The owner’s existing paper policy and reserved ETF portfolios remain separate.
