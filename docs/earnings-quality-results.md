# Cash-backed earnings: completed strategy comparison

**September 29, 2026: all 10 scheduled model fits and 20 historical accounts completed. Six paths gained and fourteen lost. No account reached 5%, 10% or 15% in any reported week. No strategy is promoted.**

These are repeated five-session trades with new entries in 2021-2025, continuous positions/cash, and a January 16, 2026 settlement tail. The [fixed specification](../.qualification/earnings-quality20260928/cohort/model-specification.json) was declared before the new financial capture and outcomes. USD10,000 is the primary simulated balance; USD2,000 remains the comparison. The comparison does not change the existing paper account.

## Every declared account

P is the unchanged 40-basis-point round-trip sensitivity. M adds the frozen Moomoo Canada US-equity tariff. These are modeled execution costs and a current-tariff counterfactual, not measured historical fills. Funding, FX, taxes, fixed subscriptions and complete corporate-action cash flows remain outside the reported net results.

| Recipe | USD10,000 P | USD10,000 M | USD2,000 P | USD2,000 M |
|---|---:|---:|---:|---:|
| All eligible filings | -2.6468% | -20.8027% | +2.7925% | -59.7063% |
| Income signal S >= 1 | +2.8625% | -4.6283% | +4.6095% | -18.5839% |
| Income signal plus Q > 0 | -0.8403% | -3.8850% | -0.1892% | -6.2280% |
| Two-output Ridge | -0.1667% | -0.0852% | +1.2008% | -0.2462% |
| Two-output boosted trees | +1.3826% | -6.9200% | +1.1126% | -0.5432% |

Returns in this table cover the **entire five-year test**, not one week. The best primary-balance path is the income signal at +USD286.25 (+2.8625%). The best percentage path is its USD2,000 version at +USD92.19 (+4.6095%). All ten Moomoo-cost paths lose. The USD2,000 Moomoo all-filings control loses 59.7063% with 59.8147% maximum drawdown, failing the 30% qualification limit. The frozen research comparison has no automatic halt; that loss remains visible rather than being retrospectively stopped.

The [full report](../.qualification/earnings-quality20260928/economic/actual-analysis/report.md) supplies every account's trades, gross P&L, fees, exposure, yearly returns, concentration and weekly statistics. Its [machine-readable analysis](../.qualification/earnings-quality20260928/economic/actual-analysis/report.json) and the [20 complete ledgers](../.qualification/earnings-quality20260928/economic/attempts/7487019bf15a4eb89e1a3702f5a0f7fb/accounts/summary.json) retain all outcomes and source references.

## Weekly target and practical activity

Each path retains 264 distinct ISO weeks: one initialization-only partial week, 260 entry-only weeks, one mixed entry/tail week, and two tail-only weeks. Every 5/10/15% target is **0/264**, also **0/261** when restricted to weeks overlapping the entry window. All 5,280 account-week rows retain losing and idle weeks. Week grouping and returns were independently reconstructed; year boundaries do not split an ISO week.

The primary income path has 133 zero-return weeks, 72 losing weeks and 59 winning weeks. Its median week is zero, worst week -1.2578%, best week +1.5562%, and longest losing run four weeks. Its mean invested exposure is 5.5542%. The primary boosted path has 161 zero-return weeks, mean exposure 4.5725%, worst week -1.5143%, and best week +2.5986%. The broader all-filings primary path averages 13.8549% exposure. Low drawdown or quiet years here cannot be read as dependable active returns.

All accounts trail the costless fully invested SPY adjusted-price reference (+98.1788%, 24.4964% sampled maximum drawdown over identical marks); fourteen also trail zero-interest cash. SPY has different exposure and does not reproduce the active account's fees, share actions, cash settlement or dividend payments. It is a reference, not a proposed replacement trade.

## What the richer model taught us

Both model families cleared every sample floor. Fitting samples expand from 479 events / 77 issuers to 1,317 / 87; calibration has 208-228 events over 71-79 issuers. Each family saves 1,087 eligible test forecasts. All scheduled fits completed without fit warnings, and none of the eligible test forecasts lacked its required outcome. Failed fitting or missing test labels therefore does not explain the weak performance.

| Family / head | Corrected mean absolute error | Training-only mean baseline | Years beating baseline MSE |
|---|---:|---:|---:|
| Ridge five-session return | 4.0899 percentage points | 4.0504 pp | 2 / 5 |
| Boosted five-session return | 4.1717 pp | 4.0504 pp | 1 / 5 |
| Ridge daily-close downside | 2.6054 pp | 2.4363 pp | 2 / 5 |
| Boosted daily-close downside | 2.6022 pp | 2.4363 pp | 1 / 5 |

Pooled corrected MAE and MSE are worse than the fitting-only mean baseline for both families and both outputs. Calibration shifts average return bias but does not establish useful economic selection. Downside correction worsens pooled squared error. Calibration-defined bins shift sharply across years; neither bin edges nor thresholds were retuned.

The income rule admits 220 causal candidates and fills 185 trades in the primary proportional account. Adding cash backing leaves 68 candidates and 64 trades, turns +USD286.25 into -USD84.03, and reduces positive years from four to two. This rejects this particular confirmation rule under these conventions; it is not evidence that all cash-flow information is useless.

At USD10,000, recorded Ridge/boosted planner evaluations reject 988/819 candidates for nonpositive estimated utility, versus only 16 affordability/ATR rejections each. These evaluation counts are not a disjoint census of unique events. More starting cash alone does not solve the weak forecasts and sparse event stream. At USD2,000, minimum fees and whole-share sizing also matter: Moomoo Ridge and boosted paths trade just once and twice.

Small positive gains are concentrated. VSH contributes 86.97% of the primary boosted gain and 96.34% of its USD2,000 counterpart. WDC contributes 49.40% of the primary income gain and more than 100% of the small USD2,000 Ridge gain. These are descriptive contributions, not corrected accounts with a stock removed. No issuer or unsuccessful variant was deleted.

## Source coverage and verification

The fixed 100-issuer capture terminated after all 4,057 registered originals. It preserves 3,867 captured originals and 190 unavailable ones: 173 outside-original-accession mappings, nine unavailable unique original XBRL instances, seven HTTP503 responses and one timeout. Completed failures were not retried or replaced. Source status `incomplete` denotes terminal completion with those retained failures.

Terminal qualification retains every original and every issuer. It produces 2,875 qualified Q values, 2,336 qualified S histories and 2,010 events jointly eligible under the financial/timing/original-header gate. All 2,010 also have the five causal price/context inputs. No eligible same-issuer/decision collision occurred. Eleven issuers have no source-qualified event; their denominators remain. Current-member selection, current profile classification, original entity/share continuity, revised vendor prices and incomplete corporate-action cash accounting remain limitations.

Independent checks covered all 13,937 raw files, 4,057 manifests, 2,875 exact rational Q formulas, 2,336 S histories and 3,444 event clocks. The sole initial source-audit flag was a timeout resource without a bytes field versus an intentional zero-byte journal value; its initial report and explicit reconciliation are preserved. Q and the header gate did not rewrite the existing eight-event S history.

The execution runner passed eight generated integration checks plus nine independent boundary checks. Its actual ledger audit passed all 20 accounts, 2,885 trade observations, 25,340 daily states, 12,262 source-price comparisons, 14,425 held marks and 7,507 learned planner projections. All 18,223 bound inputs and 111 completion-listed outputs matched. Four intentional audit corruptions were detected. Overlapping account variants and clustered reporting dates are not independent observations. Verification supports the stated arithmetic and chronology, not executable fills or profitability.

The independent actual model/feature audit passed 126,444 checks: all 4,057 events and five causal inputs, 1,463 issuer-year denominators, fold membership, labels, fitting-only preprocessing, calibration and both-family forecast barriers. All ten saved models reloaded with exactly matching calibration and test forecasts, without refitting. Each family preserves 1,316 test requests and 1,087 eligible predictions. No actual row crossed a purge boundary; strict boundary checks still applied. The initial checker-only omission of an optional unavailable-event field and its correction are preserved. See the [model audit](../.qualification/earnings-quality20260928/economic/actual-review-model/model-chronology-review.json) and [account audit](../.qualification/earnings-quality20260928/economic/actual-review-account/audit-20260929T215839Z.json).

Attempt `7487019bf15a4eb89e1a3702f5a0f7fb` is bound by definition `518039219b5b7be3935fb788f14ffacc23b90cb73033411414d7fb1d70a1859f`. The 191-member code/model/result archive is byte-verified: `earnings-comparison-20260929.zip`, SHA `51a620b50b7462d04887d6317fc9b8a6b68ebafc8fb07e2e8386510c3f122c97`. Original raw sources remain separately preserved at their bound paths.

## Next research decision

Preserve this completed comparison without rerunning its grid, increasing risk to force targets or weakening thresholds. The next question is whether the 10-Q signal contains news that was already available in an earlier earnings disclosure. That is an unverified timing hypothesis, not an established explanation of these losses.

First examine saved original SEC discovery roots/history for the same 100 issuers, before requesting more documents. Freeze candidate-matching rules and retain every unmatched, multiple, late or unavailable case. An earlier 8-K Item 2.02 entry is only a candidate until its original document, fiscal period and disclosed contents are linked. Never backdate the later 10-Q's S/Q values to that earlier time. Any subsequent strategy must use only facts actually disclosed before its decision and get a separate predeclared comparison.

The active eleven-stock paper baseline remains separate. Its existing worker was resumed once after process/journal verification; no daily-model migration, new account initialization, live order or option order occurred.
