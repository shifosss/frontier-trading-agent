# Strategy interaction economic results

Completed 54 of 54 declared accounts; 0 failed or incomplete. All results below use USD 2,000, every-session screening, next-close entries, and repeated 1/3/5-session holds from 2016-01-04 to 2026-09-18. These are exploratory current-member, revised-source simulations; no promotion or future-profit claim.

Positive accounts: 0 of 54. Positive accounts with modeled drawdown at most 30%: 0 of 54. These counts do not establish stability or source correctness.

## All policies and holding periods

Each cell is net cumulative return / maximum drawdown. Failed paths remain labeled.

| Policy | Proportional 1 | Proportional 3 | Proportional 5 | Moomoo 1 | Moomoo 3 | Moomoo 5 |
|---|---:|---:|---:|---:|---:|---:|
| relative_reversal_2 | -92.8% / 92.8% | -54.0% / 58.9% | -43.6% / 51.3% | -99.5% / 99.5% | -99.5% / 99.5% | -99.6% / 99.6% |
| relative_reversal_5 | -91.5% / 91.5% | -25.5% / 39.9% | -17.8% / 27.4% | -99.5% / 99.5% | -99.5% / 99.5% | -99.6% / 99.6% |
| trend_pullback | -95.5% / 95.5% | -68.7% / 68.7% | -40.7% / 48.8% | -99.5% / 99.5% | -99.6% / 99.6% | -99.6% / 99.6% |
| relative_volume_continuation_5 | -96.5% / 96.5% | -74.0% / 76.8% | -72.0% / 73.4% | -99.6% / 99.6% | -99.7% / 99.7% | -99.7% / 99.7% |
| beta_residual_reversal_2 | -91.5% / 91.5% | -47.4% / 55.1% | -29.6% / 44.4% | -99.7% / 99.7% | -99.6% / 99.6% | -99.7% / 99.7% |
| trend_conditioned_reversal_5 | -93.7% / 93.7% | -64.0% / 66.2% | -32.8% / 40.6% | -99.6% / 99.6% | -99.6% / 99.6% | -99.6% / 99.6% |
| compression_continuation_5 | -91.1% / 91.2% | -55.0% / 59.9% | -10.2% / 29.8% | -99.6% / 99.6% | -99.5% / 99.5% | -99.5% / 99.5% |
| equal_percentile_blend | -93.7% / 93.7% | -51.2% / 51.3% | -35.6% / 47.0% | -99.6% / 99.6% | -99.5% / 99.5% | -99.6% / 99.6% |
| volatility_regime_selector | -93.9% / 93.9% | -46.1% / 47.8% | -34.3% / 36.1% | -99.7% / 99.7% | -99.5% / 99.5% | -99.7% / 99.7% |

## Predeclared paired contrasts

The six primary contrasts each cover three holds and two fee profiles. The tables separate proportional strategy comparisons from the Moomoo minimum-fee depletion paths. Positive differences mean smaller losses here. Every detailed delta remains in the JSON.

### proportional

| New policy | Control | Better equity / 3 | Lower drawdown / 3 | Better net USD expectancy / 3 | Equity delta at 1 / 3 / 5 sessions, USD |
|---|---|---:|---:|---:|---:|
| beta_residual_reversal_2 | relative_reversal_2 | 3 | 3 | 3 | +26.88 / +132.94 / +280.37 |
| trend_conditioned_reversal_5 | relative_reversal_5 | 0 | 0 | 0 | -43.54 / -770.02 / -299.06 |
| compression_continuation_5 | relative_volume_continuation_5 | 3 | 3 | 2 | +106.82 / +379.62 / +1235.36 |
| equal_percentile_blend | relative_reversal_5 | 0 | 0 | 0 | -43.33 / -514.18 / -355.45 |
| equal_percentile_blend | relative_volume_continuation_5 | 3 | 3 | 3 | +56.27 / +455.37 / +726.93 |
| volatility_regime_selector | equal_percentile_blend | 2 | 2 | 2 | -3.92 / +102.38 / +26.54 |

### moomoo_ca_us

| New policy | Control | Better equity / 3 | Lower drawdown / 3 | Better net USD expectancy / 3 | Equity delta at 1 / 3 / 5 sessions, USD |
|---|---|---:|---:|---:|---:|
| beta_residual_reversal_2 | relative_reversal_2 | 0 | 0 | 2 | -2.55 / -0.71 / -1.64 |
| trend_conditioned_reversal_5 | relative_reversal_5 | 0 | 0 | 3 | -1.78 / -0.90 / -1.15 |
| compression_continuation_5 | relative_volume_continuation_5 | 3 | 3 | 1 | +0.64 / +2.40 / +3.07 |
| equal_percentile_blend | relative_reversal_5 | 1 | 1 | 1 | -0.76 / +0.42 / -0.76 |
| equal_percentile_blend | relative_volume_continuation_5 | 3 | 3 | 3 | +1.09 / +3.06 / +0.84 |
| volatility_regime_selector | equal_percentile_blend | 0 | 0 | 3 | -1.79 / -0.28 / -1.19 |

## Economic interpretation

**None of these 54 accounts justifies trading capital or automatic promotion.** The experiment nevertheless separates useful interactions from added complexity that made decisions worse. All account paths completed; there are no failed paths silently excluded from this result. The following strategy comparisons use the proportional 40-bps scenario; the Moomoo paths have a separate minimum-fee problem.

- **Beta-adjusted reversal improves its direct control, but remains fragile.** Ending cash improves by USD 27 / 133 / 280 at 1 / 3 / 5 sessions, and drawdown and net dollar expectancy improve at all three holds. Exposure rises slightly, so these smaller losses do not come from sitting out more. The three-session variant has only one positive year, 2023; its largest recorded trade is a USD 350 PSQH gain. The five-session variant still loses 29.57% with 44.44% drawdown. This is evidence to investigate conditional reversal, not a qualified replacement.
- **The trend gate fails its primary comparison.** Adding the long-trend and relative-trend conditions makes reversal5 worse at every hold: ending equity falls another USD 44 / 770 / 299, with higher drawdown and worse net dollar expectancy. At five sessions it increases exposure by 7.83 percentage points and annual turnover by 8.30 times. Filtering the candidate list did not reduce deployment: the different ATR-sized positions were larger. A favorable comparison with the weaker trend-pullback baseline would not rescue the failed predeclared reversal comparison.
- **Compression is the most informative continuation interaction, but still loses overall.** At five sessions it changes the continuation account from −71.95% to −10.19%, improves maximum drawdown from 73.44% to 29.77%, and changes recorded gross P&L from −USD 676 to +USD 1,032. It actually pays USD 473 more fees and has 6.96 percentage points more exposure than its control. At one session, fewer trades and lower costs explain part of the smaller account loss while net dollar expectancy per trade deteriorates. The three- and five-session improvements include better net dollar expectancy; this distinction matters.
- **Equal blending dilutes the stronger component.** It beats volume continuation at all three holds but loses to reversal5 at all three. The five-session blend returns −35.61% with 47.02% drawdown, versus reversal5's −17.84% and 27.37%. Merely adding a second strategy head does not improve the resulting decision.
- **The fixed regime selector is inconsistent.** Against the equal blend it worsens the one-session endpoint and improves the three- and five-session endpoints. Its five-session return remains −34.28%, with only two positive years out of eleven. Drawdown improves to 36.09%, but its worst week is worse than the blend's, and exposure is slightly higher. This particular binary switch is not an established timing edge.

### Costs, sizing and return averages

On the actual fee-affected position paths, 23 of 27 proportional accounts and 17 of 27 Moomoo accounts have positive gross dollar P&L before subtracting recorded costs; all have negative net P&L. Those counts are **not profitable fee-free counterfactual accounts**: removing costs would also change later cash, quantities and trades.

At the proportional scenario, every one-session account loses 91.1–96.5%. Annual turnover is roughly 126–140 times average equity, despite average invested exposure around 23–30%. Five-session holds reduce annual turnover to about 29–38 times; they still need economically selective entries. For five-session compression, gross P&L is USD 1,031.62, recorded fees USD 1,235.34, and net loss USD 203.72. Mean gross/net trade returns are +0.38285% / −0.01792%; mean gross/net dollar P&L is +USD 0.38407 / −USD 0.07585 per trade.

An instructive mismatch is five-session reversal5: its unweighted mean net trade return is **+0.10057%**, while average net dollar P&L is **−USD 0.13260** and the account loses **USD 356.70**. Differing trade notionals, path-dependent cash and timing mean the average percentage trade is not the return earned by the money actually allocated. Follow-up selection must judge expected dollars after costs at the proposed whole-share quantity, alongside percentage forecasts and downside.

All 27 Moomoo scenarios finish with only USD 6.27–9.74. Their mean round-trip fee is USD 4.18–4.37 across the account paths, which exhausts a small account making hundreds of small transactions. Later flat, zero-return years reflect capital depletion and inability to fund more orders; they are not stable risk management. Comparing a few remaining dollars between these failed paths should not be mistaken for a meaningful strategy win.

The 40-bps scenario remains a controlled sensitivity, not a verified minimum market-wide cost. The retained quote study spans very different securities and times, and cannot calibrate all fills. These losses do not prove impossibility at a commission-free USD route. Broker-specific fees and independent execution evidence should set later assumptions; favorable P&L must never select the tariff. The user's 30% loss preference is not enforced as a stop in this research, so the catastrophic paths are not deployable policies.

### Stability and concentration

Five-session compression has 5 positive years out of 11, 66 positive months out of 129 and 286 positive weeks out of 559. Its worst year is −11.88% and worst week −5.47%. Its largest winning trade is 0.93% of total positive trade P&L and its five largest winners are 3.95%, so this particular result is not dominated by one recorded winning trade. Nevertheless, positive months and dispersed winners do not offset its cumulative loss.

Five-session reversal5 also has only 5 positive years and 66 positive months. The blend and selector each have only 2 positive years. Beta reversal's three-session result is particularly concentrated in its single positive year. All yearly, monthly and weekly series, including partial first/last periods and the post-depletion Moomoo periods, are preserved for every account in the JSON. No period or tail trade was removed.

The same-window whole-share SPY reference ends around USD 8,299 under proportional costs (+314.96%, 31.93% maximum drawdown), with a very different holding duration and invested exposure. It highlights the economic opportunity cost; it is not an equal-risk, equal-turnover strategy comparison.

### Observed regime attribution

The frozen binary rule labels 1,416 account sessions as continuation state (SPY above its 200-session mean and volatility at or below its previous 252-observation median), and 1,277 as reversal state; none is unknown. These are definitions of the tested switch, not independently established economic regimes. The table covers five-session proportional accounts. Exposure is averaged on dates currently in each state; completed trade P&L is grouped by the state known on its signal date.

| Policy | Exposure: continuation / reversal state | Net trade P&L: continuation / reversal signal cohort, USD |
|---|---:|---:|
| relative_reversal_2 | 31.43% / 24.93% | -567.91 / -303.86 |
| relative_reversal_5 | 33.08% / 24.81% | -603.96 / +247.26 |
| trend_pullback | 40.13% / 32.67% | -710.07 / -104.28 |
| relative_volume_continuation_5 | 28.96% / 25.23% | -940.51 / -498.57 |
| beta_residual_reversal_2 | 31.50% / 25.74% | -379.34 / -212.06 |
| trend_conditioned_reversal_5 | 40.23% / 33.40% | -662.62 / +6.86 |
| compression_continuation_5 | 36.27% / 31.80% | -377.70 / +173.98 |
| equal_percentile_blend | 31.30% / 23.56% | -698.17 / -13.98 |
| volatility_regime_selector | 31.24% / 25.90% | -1,082.02 / +396.40 |

The selector's continuation cohort loses USD 1,082.02 while its reversal cohort gains USD 396.40. Reversal5 and compression likewise have positive reversal-state cohorts and negative continuation-state cohorts. This is a useful reason to test learned conditional selection. It does **not** establish that deleting a losing state would reproduce the positive cohort P&L: changed cash, overlapping positions and future sizes would create a different account. All 54 accounts retain the same attribution dimensions in the JSON.

### What to test next

The separately declared [entry-timing diagnostic](strategy-timing-study-2026-09-28.md) has now answered the first follow-up question: all nine primary next-open versus next-close common-exit contrasts have negative equal-date mean log effects, approximately −6.35 to −90.74 bps. Earlier entry did not recover a broadly missed entry-day gain in these fixed cohorts. These are gross event comparisons, not portfolio returns or executable opening fills. Keep next-close timing for the next controlled strategy study.

The next question is whether a model can learn **when reversal, continuation or compression is worth trading**, then decline candidates whose expected return cannot cover the declared costs at their actual proposed size. Compare conditional percentage ranking with conditional dollar-utility ranking using the same predictions, candidates, capital and risk limits. This addresses both the weak fixed regime switch and the positive-average-percentage/negative-account-dollar mismatch. The [bounded follow-up design](conditional-strategy-selection-plan.md) is a reviewed design whose execution request is not yet frozen; it is not a running experiment or a chosen trading policy.

Source continuity, current-member survivorship and revised historical vintages remain unresolved. Independent arithmetic validates accounting relationships, not economic data completeness. Known action-crossing attribution is retained separately under `.qualification/strategy-action-attribution20260928`; no account prices, eligibility, trades or P&L have been changed to improve these results.

## Reading the evidence

Gross and net expectancy, annual turnover, fee burden, all yearly/weekly/monthly returns, largest positive/negative contributors, and every failed path are retained in `economic-results.json`. The CSV contains one row for each of 54 accounts. No thresholds or running signals were adjusted from these results.

Arithmetic checks independently verified complete flat accounts against initial capital plus net trade P&L, gross minus fees, daily compounding, period returns, drawdown, exposure and turnover. These checks do not resolve missing corporate actions, security mappings or executable price quality.

The same-window SPY reference has substantially different exposure and holding duration; its return is a reference, not proof of equal-risk outperformance. First and last yearly/weekly/monthly periods may be partial.

Evidence: `.qualification/strategy-interactions20260928/economic-results.json`, `economic-results.csv`, all 54 account JSONs and the frozen request/formula documentation. This report preserves every comparison; follow-up questions are identified explicitly after the results.
