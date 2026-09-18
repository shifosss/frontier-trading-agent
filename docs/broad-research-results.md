# First broad strategy study - September 18, 2026

Completed run `114df178722046bebaca0db1e3c7d8e7` at 2026-09-18T19:47:46.383843+00:00. All 5,640 discovered candidates were attempted; 5,592 histories supplied **6,086,359 daily rows**. The saved report retains 48 failed captures rather than silently treating them as successful coverage.

Twelve declared strategy/horizon hypotheses produced 11,840 cohort audit records and 864 summary rows across currencies, cash budgets, periods and costs. Those rows are related comparisons, not 864 independent discoveries. All results are available under Strategy lab in the local workstation.

## What the first comparison says

The following is a fixed view: 100,000 native-currency starting cash per independent cohort, five-session holding period, and the evaluation interval September 18, 2025 to September 17, 2026. Every row has 49 completed cohorts and one not yet mature. Percentages are **mean cash-weighted cohort returns**, not realized account returns or annualized performance.

| Book | Family | Return at 20 bps | Return at 100 bps | Excess vs ETF at 20 bps | Mean invested |
| --- | --- | ---: | ---: | ---: | ---: |
| USD | momentum | -0.254% | -0.593% | -0.357% | 42.454% |
| USD | trend pullback | 0.209% | -0.105% | 0.107% | 39.238% |
| USD | mean reversion | 0.185% | -0.117% | 0.083% | 37.792% |
| USD | breakout | -0.972% | -1.115% | -1.074% | 17.891% |
| CAD | momentum | -0.089% | -0.477% | -0.299% | 48.523% |
| CAD | trend pullback | 0.352% | 0.007% | 0.142% | 43.089% |
| CAD | mean reversion | 0.110% | -0.210% | -0.100% | 39.936% |
| CAD | breakout | -0.023% | -0.315% | -0.233% | 36.496% |

The cost-matched SPY cohort benchmark averaged 0.102% at 20 bps; XIU averaged 0.210%. The benchmark represents repeated same-horizon ETF cohorts, not a continuous passive buy-and-hold account. Its approximately full investment differs from the strategies' partial investment. Under higher cost assumptions, a strategy can outperform that benchmark while still losing money; positive excess alone is not a promotion criterion.

In this view, trend pullback and US mean reversion warrant further observation. US pullback and reversion averages turn negative at the 100-bps stress. Momentum and breakout do not justify promotion from these results. Longer horizons, smaller budgets and earlier periods remain visible in the UI; no row was hidden because its result was unfavorable. This is a research prioritization judgment, not a selected profitable strategy. The operating paper policy also has different regime and exit rules, so these cohorts do not measure that account's performance.

Changing cash changes the affordable selection and invested weights even though ranking formulas and discovered coverage stay fixed. At USD500 the same-period SPY whole-share benchmark holds cash because one share does not fit. That makes its zero return an affordability result, not a claim that SPY itself had no return.

## Coverage and forward evidence

Capture failures comprised 34 missing-symbol responses, four currency mismatches, five empty/duplicate histories and five non-positive-price histories. Canadian issuer roots and share classes explain an important portion of the missing-symbol cases; the original records are preserved for targeted resolution. Current membership and current-vintage adjusted prices still carry survivorship/revision bias. Historical whole-share prices around splits are not qualified.

The completed study froze **96 prospective cohort plans** at 2026-09-18T19:47:46.384867+00:00, before their first eligible entry close. All 96 are pending; no future outcomes, fills or profits have been invented. Later scheduled captures evaluate the same names and quantities. The paper trading account remains a separate, unchanged baseline.

## Evidence

- Full study: `artifacts/research-lab/runs/114df178722046bebaca0db1e3c7d8e7/result.json`
- Frozen input and source identity: `artifacts/research-lab/runs/114df178722046bebaca0db1e3c7d8e7/definition.json` and `evaluation-definition.json`
- Prospective snapshot: `artifacts/forward-studies/snapshots/374906c0f24eb6790a0f8eb4410fdd48aeb4a6ca658a75259034b4cbf44d4dcd.json`
- Initial forward observation: `artifacts/forward-studies/evaluations/6f305e0eb0ca4de6adea39d15cca843e.json`
- Source discovery, raw capture and failed attempts remain local; generated market data is not committed to git.
- Software validation: 231 tests passed, Ruff passed, TypeScript/Vite build passed. The 96 warnings are existing upstream deprecations.

See [methodology and operation](broad-research.md) for the experiment definition and automated follow-up schedule.
