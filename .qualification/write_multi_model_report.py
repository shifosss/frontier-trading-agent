"""Render the complete, independently summarized multi-model result for review."""
import json
import math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN='814780d48b4141b9a82a3fb917d1b85a'
A=ROOT/'.qualification/multi-model-economics-full'
a=json.loads((A/'analysis.json').read_bytes())
s=json.loads((ROOT/'artifacts/historical-lab/runs'/RUN/'summary.json').read_bytes())
rows=a['all_accounts']
def pct(v): return 'incomplete' if v is None else f'{v*100:.2f}%'
def num(v): return 'unavailable' if v is None else f'{v:,.2f}'
def selected(currency,budget=2000,cost=40): return [r for r in rows if (r['currency'],r['budget'],r['cost_bps'])==(currency,budget,cost)]
def account(currency,strategy,h,budget=2000,cost=40): return next(r for r in selected(currency,budget,cost) if (r['strategy'],r['horizon'])==(strategy,h))
lines=['# Daily multi-model historical research results','',
f'Completed 2026-09-19 at 19:26:08 UTC. Run `{RUN}`. This is the first full run of the [declared model comparison](superpowers/plans/2026-09-19-multi-model-study.md).','',
'**This run does not establish a strategy ready for real-money trading.** Of 720 declared accounts, 569 completed and 151 became incomplete because required prices were missing. Among the complete accounts, 59 gained money and 510 lost money; none beat its matched equity ETF in cumulative return. At the 2,000-native-unit / 40-bps reference setting, all 21 US learned-model/hold combinations lost money. Smaller losses than the rule controls are an improvement in the research comparison, not a demonstrated trading edge.','',
'The Canadian five-session histogram-gradient-boosting account shows a positive full-period result, but its recent returns are weak and a large winning trade contains unresolved historical share/price continuity. That gain is not verified economic alpha. The saved result is preserved, with no silent price repair or subtraction of the questionable trade.','',
'## Scope and interpretation','',
f'The run reused the original `{s["definition"]["source_reuse"]["run_id"]}` capture, cutoff **{s["as_of"]}**, without new source repair: **{s["capture"]["usable"]:,} usable histories, {s["capture"]["rows"]:,} daily observations**, from 8,434 requested instruments. The original 200 failed captures remain recorded. Available history starts in 2000; individual instruments have shorter histories. Current membership and current adjusted-data vintage do not reconstruct the securities available to an investor on every historical date.','',
'Twenty strategy families × 1/3/5-session holds × 2,000/10,000 native balances × 20/40/100-bps proportional-cost settings × US/Canadian books produce 720 continuous account attempts, plus 24 matched ETF/cash references. Seven learned variants comprise Ridge, ExtraTrees, HistGradientBoosting, shared-hidden six-output MLP, equal ensemble, calibrated ensemble and diversified calibrated ensemble. Thirteen rule controls use identical trading dates and cash-account mechanics.','',
'Each market has 23 chronological refits: 504 prior sessions fit the models; the next 252 calibrate weights; the following 252 test them. Labels crossing fit/calibration/test boundaries are purged. Screening occurs every completed session; entries fill at the next close and independent positions exit after 1, 3 or 5 sessions. Folds close positions, with settled and unsettled cash carried into the next fold. Whole-share sizing, five positions, 20% entry caps and dated settlement are modeled.','',
'**These balances are separate simulated accounts, not the owner’s current cash or monthly contribution schedule.** The 40-bps reference is one declared sensitivity setting, not a measured Wealthsimple/moomoo all-in fee. None of the three settings includes fixed broker charges, FX, subscriptions, taxes, interest or contributions. Cash earns zero. A 30% observed-drawdown comparison is descriptive; it does not enforce a future loss cap.','',
'## Every account group','',
'Each row contains 60 attempted accounts: 21 learned and 39 rule controls. Positive and drawdown counts use complete paths only; failures stay in the attempted denominator. Repeated models and overlapping history are not independent statistical tests.','',
'| Market | Native start | Cost setting (bps) | Complete / 60 | Incomplete | Positive / complete | Positive learned / 21 attempted | Positive rules / 39 attempted | Complete paths above 30% drawdown |',
'| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for currency in ['USD','CAD']:
 for budget in [2000,10000]:
  for cost in [20,40,100]:
   group=selected(currency,budget,cost); complete=[r for r in group if r['status']=='complete']
   learned=[r for r in complete if r['model_class']=='learned']; rules=[r for r in complete if r['model_class']=='rule']
   lines.append(f'| {currency} | {budget:,} | {cost} | {len(complete)} | {60-len(complete)} | {sum(r["total_return"]>0 for r in complete)} | {sum(r["total_return"]>0 for r in learned)} | {sum(r["total_return"]>0 for r in rules)} | {sum(r["max_drawdown"]>.3 for r in complete)} |')
lines += ['',
'Across all settings, 474 of the 569 complete paths exceeded 30% drawdown. Thirty-seven complete paths were positive with drawdown at or below 30%; that screen does not resolve data quality, costs or selection bias. None of the complete paths was entirely cash, although 182 averaged less than 10% invested exposure. Their lower market exposure helps explain some lower drawdowns.','',
'Of 240 strategy/hold/balance/market groups, 168 completed at all three cost settings; none was profitable at all three. The other 72 groups have incomplete cost comparisons. This is evidence of sensitivity, **not a requirement that every strategy must survive 100 bps regardless of the actual broker**. Realistic execution costs must be measured before a promotion decision.','',
'## Primary reference: 2,000 native units and 40 bps','',
'Each cell below is **cumulative account return / maximum drawdown**. Incomplete means the full-period metrics are unavailable; an observed prefix is not substituted. All 20 families and three holds are included. The [720-account CSV](../.qualification/multi-model-economics-full/all_accounts.csv) contains trade counts, fees, expectancy, exposure, turnover, weekly/monthly results and exact failures for every setting.','']
for currency in ['USD','CAD']:
 b=next(b for b in a['benchmarks'] if b['currency']==currency and b['budget']==2000 and b['cost_bps']==40 and b['symbol']!='CASH')
 lines += [f'### {currency}', '',
 f'Evaluation: **{b["first_session"]} through {b["last_session"]}**. Matched {b["symbol"]} buy-and-hold: **{pct(b["total_return"])} cumulative return**, {pct(b["max_drawdown"])} drawdown; zero-interest cash: 0%. These ETF paths carry substantially more exposure and exceed the owner’s 30% loss tolerance; their returns are comparison references, not a recommended allocation.','',
 '| Strategy | 1 session: return / drawdown | 3 sessions: return / drawdown | 5 sessions: return / drawdown |',
 '| --- | ---: | ---: | ---: |']
 for strategy in s['methodology']['strategies']:
  cells=[]
  for h in [1,3,5]:
   r=account(currency,strategy,h)
   cells.append('incomplete' if r['status']!='complete' else pct(r['total_return'])+' / '+pct(r['max_drawdown']))
  lines.append('| '+strategy.replace('_',' ')+' | '+' | '.join(cells)+' |')
 lines.append('')
lines += ['## Learned models versus controls, exposure and time stability','',
'At the primary setting, learned models beat matched rule controls in 229 of 259 available US pair comparisons and 120 of 126 Canadian comparisons. All 546 declared primary pairs remain in the [full pair CSV](../.qualification/multi-model-economics-full/all_learned_rule_pairs.csv), including unavailable comparisons caused by incomplete paths. Beating a losing control is not evidence of positive expected returns. None of the complete accounts beats its matched ETF in cumulative return.','',
'Both calibrated and diversified ensembles lose money at all three primary holds in both markets. Combining models and enforcing a correlation ceiling did not establish net profitability. The reference ExtraTrees five-session accounts lost 1.97% in USD and 5.28% in CAD while averaging only 4.78% and 3.80% invested, respectively; their relatively low drawdowns should not be interpreted as strong risk-adjusted performance without that cash context.','',
'All complete accounts span 24 calendar-year segments, including partial 2003 and 2026, and 23 test folds. Every saved year and fold is retained in the [year CSV](../.qualification/multi-model-economics-full/all_years.csv) and [fold CSV](../.qualification/multi-model-economics-full/all_folds.csv). Incomplete-account fold prefixes are explicitly labeled and are not treated as full-period performance.','',
'### Canadian HistGradientBoosting five-session observation','']
r=account('CAD','hist_gradient_boosting',5)
ys=[y for y in a['all_years'] if all(y[k]==r[k] for k in ['currency','budget','cost_bps','strategy','horizon'])]
recent={y:math.prod(1+t['return'] for t in ys if int(t['year'])>=y)-1 for y in [2010,2017,2020]}
lines += [f'The primary account ends at C${r["ending_equity"]:,.2f}: **{pct(r["total_return"])} cumulative return, {pct(r["cagr"])} CAGR, {pct(r["max_drawdown"])} drawdown** over nearly 23 years. It completed {r["completed_trades"]:,} trades, with C${r["net_expectancy_native"]:.3f} mean net P&L per trade, {pct(r["win_rate"])} winning trades, {pct(r["mean_exposure_fraction"])} mean invested exposure and {pct(r["mean_settled_cash_fraction"])} mean settled cash. These are retrospective selected results, not a forecast or promotion.','',
'**Material unresolved source event:** its largest positive TPX-B.TO trade, February 7–14, 2005, uses five shares and a price move from C$34.59 to C$87.01, producing approximately C$260.884 net P&L, about 34% of this account’s total net gain. The retained provider series jumps approximately 177.0455% on February 8 in both nominal and adjusted prices, with an approximately constant 0.3176047 adjusted-to-reconstructed-nominal ratio and no nearby provider-reported action. Current ticker/company mapping does not establish dated share continuity. The [source-tail evidence](../.qualification/multi-model-review/cad-hgb5-source-tail.json) and [SEC-based continuity review](tpx-source-continuity.md) identify material share-conversion and cash-entitlement terms. The predecessor share class, provider date mapping and cash flows remain unreconciled; a simple split-factor repair is not established. No correction has been inserted into this frozen run.','',
 f'Even taking the saved series literally, only {r["positive_years"]}/{r["year_count"]} calendar-year segments and {r["positive_folds"]}/{r["fold_count"]} folds were positive. The worst calendar year returned {pct(r["worst_year"])}. Profitable weeks were {pct(r["weekly_profitable_fraction"])} and profitable months {pct(r["monthly_profitable_fraction"])}; the worst month was {pct(r["monthly_worst_return"])}.','',
 '| Subperiod, including 2026 through September 18 | Compounded account return |',
 '| --- | ---: |']
for year,value in recent.items(): lines.append(f'| {year}–2026 YTD | {pct(value)} |')
con=next(c for c in a['activity_and_concentration'] if c['account_id']==r['account_id'])['profit_concentration_top_bottom_only']
top=con['best_symbols'][:5]
lines += ['',f'The five largest saved net symbol contributors ({", ".join(symbol for symbol,pnl in top)}) sum to {100*sum(pnl for symbol,pnl in top)/r["net_pnl_total"]:.2f}% of total net gain; the remaining symbols collectively detracted. This uses saved cumulative symbol attribution, not five individual trades. The overall gain is concentrated and largely predates 2010.','',
 '| CAD starting cash | Cost setting (bps) | Cumulative return | Drawdown | Trades | Mean invested |',
 '| ---: | ---: | ---: | ---: | ---: | ---: |']
for budget in [2000,10000]:
 for cost in [20,40,100]:
  v=account('CAD','hist_gradient_boosting',5,budget,cost)
  lines.append(f'| {budget:,} | {cost} | {pct(v["total_return"])} | {pct(v["max_drawdown"])} | {v["completed_trades"]:,} | {pct(v["mean_exposure_fraction"])} |')
lines += ['',
'The 40-bps path can exceed the 20-bps path because the modeled cost also changes the learned entry threshold, rankings, fills and subsequent account trajectory. These are different executed paths, not a fee-only subtraction from identical trades. It would be invalid to select the favorable cost setting or interpolate a break-even fee from these outcomes. The 100-bps losses and higher drawdowns are sensitivity evidence; they are not asserted to be the owner’s actual brokerage cost.','',
'## Forecast calibration and convergence','',
'Each cell counts folds, out of 23. A fallback means no base model improved return-MSE over the training-mean baseline for that horizon, so the ensemble used equal weights. Return prediction accuracy and downside prediction accuracy are different diagnostics; neither establishes trading profit.','',
'| Market | Hold | Equal-weight fallbacks | Ridge return-MSE wins | ExtraTrees wins | HGB wins | MLP wins |',
'| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for d in a['diagnostics']:
 for h in d['horizons']:
  wins=h['models_beating_training_mean_return_mse']
  lines.append(f'| {d["currency"]} | {h["horizon"]} | {h["equal_weight_fallbacks"]}/23 | {wins["ridge"]}/23 | {wins["extra_trees"]}/23 | {wins["hist_gradient_boosting"]}/23 | {wins["multi_head_mlp"]}/23 |')
lines += ['',
'All 46 MLP fits retained a convergence warning after reaching the declared 60-iteration limit: 23 US and 23 Canadian. No warning was discarded and no failed model was silently removed. This limits conclusions about that fixed training configuration; it does not show that neural prediction is universally ineffective. The UI now renders the warning’s model, category and message rather than converting the structured object to an unreadable string.','',
'The run recorded 8,521,800 US and 1,171,421 Canadian eligible test forecasts. These are stock/session processing counts, not unique independent observations. Rolling fitting and calibration reuse historical data; the summary retains sample sizes, purged/excluded-label counts, sample digests and per-head MSE/weights.','',
'## Missing paths and source limitations','',
'USD: 350 complete and 10 incomplete accounts. CAD: 219 complete and 141 incomplete. Required price failures below invalidate the entire affected account result. Counts are failure occurrences, so one account can contribute more than one symbol/reason. The listing/capture failures are an additional limitation, not included in these account-path counts.','',
'| Required missing observation | Account-path occurrences |','| --- | ---: |']
for missing,count in sorted(a['missing_reasons'].items()): lines.append(f'| `{missing}` | {count} |')
lines += ['',
'No WJX issuer overlay or other historical repair was applied to this comparison. It intentionally retains the same raw sources as the earlier study. Future source repairs should be separately versioned and rerun with all variants; a favorable repair must not be applied only to a selected winner.','',
'Provider-reported split reconstruction supports nominal sizing, but synthetic adjusted-return marks are not a complete issuer-action/share-conversion, cash-distribution or tax ledger. Hash agreement and arithmetic reconciliation verify what was calculated from the saved data; they do not establish economic continuity of every ticker. Current-member survivorship, ticker history, revised data and missing observations remain material.','',
'## Verification and reproducibility','',
'The independent [compact-result analyzer](../.qualification/analyze_multi_model_economics.py) reconciled ending equity, realized net P&L, yearly and fold compounding, trade counts and holding clocks for all complete accounts. It retained all 720 attempted rows and correctly withheld incomplete profitability. Its deliberate-error self-checks verify that leaked incomplete metrics and corrupted fold returns are detected.','',
'The separate [full audit](../.qualification/multi-model-review/full-audit-814780d48b4141b9a82a3fb917d1b85a.json) passed: 8,234 raw-source hashes; 744 full/compact account/reference rows; all 42 retained learned trade ledgers; and 192,113 source-priced completed trades across 4,463 source symbols. It checked fees, whole shares, 20% entry caps and settlement across folds. This audit shares the source adjustment normalizer; it does not independently establish complete issuer actions. Sample digests and purge boundaries were verified, but exact sampled-row membership was not reconstructed.','',
'The [actual completed UI check](../.qualification/historical-ui/multi-model-actual-completed-report.json) passed 48 filter contexts across 1440, 768, 390 and 320 pixel widths, including all 720 account rows at each width, matching references, incomplete cases, structured warnings and forecasts. A one-byte ranged request verified the 691,108,930-byte evidence download without fetching the whole file. No POST, new study, paper mutation or live broker action was performed by these checks.','',
'Artifacts:','',
 f'- [Frozen run definition](../artifacts/historical-lab/runs/{RUN}/definition.json), [compact result](../artifacts/historical-lab/runs/{RUN}/summary.json) and [full audit result](../artifacts/historical-lab/runs/{RUN}/result.json).',
 '- [All 720 accounts](../.qualification/multi-model-economics-full/all_accounts.csv), [all yearly rows](../.qualification/multi-model-economics-full/all_years.csv), [all fold rows](../.qualification/multi-model-economics-full/all_folds.csv), [all 3,276 learned/rule comparisons](../.qualification/multi-model-economics-full/all_learned_rule_pairs.csv).',
 '- [Economic analysis](../.qualification/multi-model-economics-full/analysis.json) and [compact economic summary](../.qualification/multi-model-economics-full/summary.json).','',
'Frozen identities:','',
 f'- Historical financial code: `{s["definition"]["code_identity"]}`.',
 f'- Data-source identity: `{s["definition"]["data_source_identity"]}`.',
 f'- Capture-index SHA256: `{s["definition"]["capture_index_sha256"]}`.',
 f'- Model configuration signature: `{s["methodology"]["model_signature"]}`.',
 f'- Published summary SHA256: `{a["provenance"]["source_sha256"]}`.',
 f'- Analysis script SHA256: `{a["provenance"]["script_sha256"]}`.','',
'The definition also freezes Python 3.13.7, NumPy 2.5.3, pandas 3.0.6, scikit-learn 1.7.2, SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.7.0, and dependency-manifest hashes. Results are reproducible to floating tolerance within the declared environment, not promised bitwise identical across parallel math libraries.','',
'## Research decision','',
'Keep this study as a completed, reproducible comparison and preserve the negative evidence. It supports further historical development, not automatic paper/live promotion. Next experiments should be separately declared around verified issuer continuity, actual execution-cost measurement, recent-period robustness and targeted model/feature or refit changes. The current fixed-configuration MLP and ensembles have not earned operational promotion; a favorable historical row is insufficient. The owner’s existing paper policy and reserved ETF portfolios remain separate.','']
(ROOT/'docs/multi-model-research-results.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'doc':'docs/multi-model-research-results.md','lines':len(lines),'source_run':RUN,'accounts':len(rows),'integrity':a['integrity']}))
