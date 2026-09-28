# Saved-model daily account rehearsal

Completed account paths: September 28, 2026. This tests persistent historical account operation and the economic effect of declared order costs. **Neither account qualifies for promotion.** No active paper policy was migrated.

The predeclared comparison uses saved candidate `a46d3876559b4374924e884c712e1ed7`, frozen capture `814780d48b4141b9a82a3fb917d1b85a` / original `90af4c840aad48f7ab58fba7a682f96a`, USD2,000, calibrated ensemble, five-session independent holdings and 40bps round-trip modeled friction. First signal is September 17, 2025; final session is September 18, 2026. Fitting/calibration outcomes end before the first signal. The historical period has already been studied; it is not an untouched holdout.

| Scenario | Ending equity | Return | Max drawdown | Completed trades | Declared costs | Profitable weeks / months |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Proportional 40bps | $1,873.88 | -6.31% | 17.39% | 248 | $29.29 | 16/53; 4/13 |
| Moomoo explicit charges plus 40bps | $891.25 | -55.44% | 56.07% | 247 | $1,008.03 | 3/53; 1/13 |

Both accounts screen every eligible completed session and hold each filled position for five sessions. The evaluation span measures repeated trades, not a year-long position. The first/last reporting weeks and months can be partial. Both finish with no positions or pending orders; proportional has $14.1616 in sale proceeds still awaiting settlement. No margin or early spending of receivables is assumed. Independent reconstruction also verifies 19 Moomoo sales whose fees exceed sale value: shortfalls are paid from settled cash immediately, rather than treated as negative future receivables.

Median entry notionals are only $22.40 and $15.28. Moomoo's mean modeled round-trip fee is $4.081; the median fee-to-entry-notional ratio is 26.47%. The existing model score includes proportional friction but not fixed broker minima, which affect sizing and accounting. This deliberately isolates their effect and exposes a poor selection objective for small orders. Gross P&L before declared fees is already negative ($96.83 and $100.73 lost), so cheaper execution alone does not establish an edge. Proportional mean equity exposure is 7.15%.

Whole-share SPY buy-and-hold over the matched next-close interval returns 15.75% / 15.55% under the corresponding scenarios. It invests much more of the account and has different risk and holding duration; this is a comparison, not a recommended portfolio or a risk-matched baseline. Cash without interest returns zero.

## Reproducibility and independent checks

- Proportional journal `35ec05080c68404ebd826ceb6b3ef015`: one 21-session chunk was saved before the owner paused; it retained five holdings and five pending orders. The same journal resumed in 17-session chunks, completed with 15 chunks and retained each invocation.
- Moomoo journal `29af0cd2df57424094a6969268ade8e5`: 13 chunks. The saved model was loaded, never refitted, for both scenarios. All 701,318 date-stock forecasts and their scores are retained per account.
- A separate auditor imports no Frontier financial code. It independently checks journal/source/model hashes, chronological boundaries, every saved score, source-priced entries/exits and daily marks, whole shares, risk/position budgets, ordered reservations, cash settlement, Decimal tariff arithmetic and all weekly/monthly outcomes. It checks 182 / 184 raw instruments including SPY. Largest daily-curve difference from independent arithmetic is approximately $2.05e-12.
- Software checks: 491 tests passed, 96 existing dependency deprecation warnings; 19 focused replay tests passed. The default engine remains exactly equal to the previous implementation in 240 comparisons containing 69,491 trades. Independent review added dependency-version and settlement-map identity checks before the real rehearsal. Ruff passes.

The one-pass real-engine comparison initially stopped because its external checker compared JSON list receivables with native tuples. All four daily curves had already matched exactly. The failed checker and diagnosis are retained; expected structures are now normalized through JSON without rounding or changing production data. The corrected repeat check passed: all four curves, every trade, activity counts and JSON-normalized final state match the one-pass run exactly. Fee accumulation differs by only USD1.066e-14. The completed replay retained 15 chunks and 248 trades on the repeat invocation, confirming idempotence. Evidence is in `resumed-vs-one-shot.json`.

Evidence is under `.qualification/stateful-daily-agent/`: `rehearsal-definition.json`, `independent_replay_audit.py`, both `independent-ledger-audit-<replay_id>-1261.json` files, `independent-economic-diagnostics.json`, `independent-ledger-report.md`, and validation records. Complete journals and report views are under `artifacts/candidate-replays/<replay_id>`.

## Limits and next decision

These are current-member, revised-vintage, synthetic adjusted-return accounts. Audit agreement proves arithmetic against recorded data, not complete issuer/action economics. No AIXI trade was executed, but [the confirmed AIXI unit error](aixi-source-continuity.md) affects source features/labels and the separate latest-model diagnostic. Reported split-crossing trades include WNW, EZGO and PAVS, plus INLF in the Moomoo path. Original-share quantities and synthetic exit values do not establish cash-in-lieu, depositary fees, dividend receipt dates or actual action-adjusted broker shares.

[Moomoo charges](execution-cost-model.md) are a current-tariff counterfactual with unverified components excluded; 40bps is a declared sensitivity, not calibrated realized slippage. Taxes, FX, account subscriptions and actual impact remain excluded. These results are not all-in broker returns.

Next: complete source/action-unit validation and preserve a separately versioned correction before economic interpretation of affected data. Then test the already declared quantity-aware positive-net-return ranking against the unchanged score, using the same risk limits, all models, source versions and cost profiles. Retain all losses and abstentions. Do not tune fees or thresholds to manufacture a winner.

The historical journal handles atomic simulated next-close fills. Reconciled broker positions, durable partial-fill remainders and a separately versioned daily paper migration remain unfinished. The eleven-stock weekly-entry paper baseline remains a separate operating trial.
