# Scanner study and dividend repair

Completed September 18, 2026. The local scanner and repaired replay are usable for
research. **This study did not establish a profitable strategy or a system ready
for live trading.** Current operating conclusion: retain cash under the CAD700
illustrative scenario; keep candidates available for further evaluation.

[Open scanner](http://127.0.0.1:8765/) ·
[Open repaired study](http://127.0.0.1:8765/?study=ba3ba6dd186c4201b7d1a151dd2be024) ·
[Account costs and options permissions](active-account-readiness.md)

A subsequent user clarification permits planned CAD-to-USD funding. See the
[USD funding study](usd-funding-study.md) for the new funded-US scenario. The CAD-only
results below remain the original dated comparison, not a permanent country limit.

## Mandate applied

- CAD600–800 additional active funding monthly; CAD700/USD0 is an illustrative first
  contribution, not a reconciled account balance. No automatic monthly credit or FX.
- Wealthsimple taxable account; moomoo cash is an alternative needing its own fee
  profile. Stocks and potential options, no borrowing.
- The stated 30% loss tolerance is recorded as an active-sleeve drawdown parameter.
  It is not permission to risk 30% on a trade and is not an enforced account control.
  Cash-flow-adjusted account equity and live positions are needed for monitoring.
- CA$1,200 XGRO and the separate CA$1,000 regular ETF portfolio stay reserved.
  The regular portfolio's 70/22/8 preference and equity subweights are preserved in
  `config/mandate.json`. No allocation or brokerage transaction was changed.

## What the scanner actually covers

The declared universe is **41 instruments: 21 individual stocks and 20 ETF context
instruments**, with 11 US stocks and 10 Canadian stocks. This is a transparent
representative universe, not all listed US/Canadian equities. `config/scanner_universe.json`
contains every name, currency, exchange calendar and exposure group.

Actual capture: **41/41 successful**, 0 source failures,
**51,383 daily observations**, approximately 2021-09-20 through 2026-09-17.
The September 18 session was still open and was excluded. Raw response bytes,
content digests, request URLs, capture times and individual failures are retained.
Provider symbol, currency, price arrays and official-session completion are checked.

Yahoo adjusted close is used for retrospective features/returns; the last provider
close is the sizing reference. This does not certify raw execution prices or
historical universe membership. It is kept separate from the Nautilus raw-bar lane.

## Fixed rule and reasons

| Decision | Reason and practical limit |
| --- | --- |
| Positive 20- and 60-session momentum, above the 50-session average | A simple weeks-scale trend hypothesis with an inspectable mechanism; not an optimized alpha model. |
| Rank average momentum divided by 20-session annualized volatility | Makes the score less dominated by volatile names; score is neither expected return nor confidence. |
| 63 consecutive completed sessions and minimum native-currency turnover | Avoids incomplete lookbacks and demonstrably illiquid samples. CAD1m/USD5m are fixed screening thresholds. |
| One name per declared group, at most five per currency | Limits obvious concentration. Sector groups do not measure actual correlation. |
| Whole shares, maximum 20% of native cash, 0.5% risk distance at two ATR | Keeps example tickets sized to the small account and avoids currency borrowing. ATR is a range estimate; no stop-fill guarantee is implied. |
| Separate USD0 and CAD700; existing-currency Wealthsimple costs | Makes funding/cost assumptions explicit. The same cost profile cannot be reused for moomoo or per-trade FX. |
| Fixed 5-session forward diagnostic with 20/40 bps cost cases | Tests a declared horizon without searching for the best-looking period. Does not implement continuous holdings, exits or broker execution. |

The policy stayed fixed after seeing negative benchmark-relative evidence. No
parameter search, cherry-picked winner or automatic strategy promotion was used.

## Current funding scenarios

All scenarios use completed September 17 prices and keep USD at zero. Monthly
additions are not automatically equivalent to actual spendable balances.

| Illustrative CAD cash | Sized candidate | Interpretation |
| ---: | --- | --- |
| 600 | None | No eligible stock fits both whole-share risk and position caps. |
| 700 | None | CNQ's two-ATR distance is approximately CAD3.67, above the CAD3.50 per-name risk budget. |
| 800 | One CNQ.TO share at a CAD70.83 reference close | Approximately CAD70.87 outlay including 5 bps sizing slippage. An unvalidated watchlist item, not a buy instruction. |

TD.TO also passes the trend screen, but its approximately CAD170.37 share price
exceeds the 20% position cap throughout this funding range. US names remain visible
but cannot receive allocations from a USD0 cash book. No currency conversion is
silently assumed. Funding-scenario artifact: `artifacts/funding-scenarios.json`.

## Completed historical diagnostic

Selection uses only prior completed daily sessions. Entry is the next session's
**close**, then exit five exchange sessions later. Weekly cohorts do not overlap.
Selected candidates have equal weights within each cohort; cash decisions earn 0%.
The benchmark uses the same entry/exit dates and normal cost assumption. Missing
selection history or selected entry/exit prices makes a cohort incomplete and
excludes it from summary means. Genuine no-signal/unaffordable decisions stay in.

| CAD result | Value |
| --- | ---: |
| Complete cohorts / incomplete excluded | 238 / 0 |
| Selected-candidate / genuine-cash cohorts | 193 / 45 |
| Candidate observations, not actual fills | 312 |
| Mean net 5-session cohort return, 20 bps costs | 0.0462% |
| Matched XIU.TO cohort mean | 0.0899% |
| Mean excess over XIU.TO | -0.0437% |
| Mean cohort return at 40 bps costs | -0.1160% |
| Positive-return cohort frequency | 42.02% |

**The rule did not beat XIU on this comparison and turned negative under cost
stress.** USD is explicitly unfunded: zero studied cohorts and null return means.
These averages are not a compounded account return, CAGR, Sharpe ratio, buy-and-hold
comparison, or a forecast. The equal-weight diagnostic is distinct from the
cash-weighted current basket. Current-vintage prices, today's selected universe,
exposed history and no live fills prevent a prospective profitability claim.

## The failed dividend study now completes

Original failed run: `13f42f66654e4bb5b67b4fea82d4dbd0`. The original inputs are
unchanged. A new immutable dataset adds the retained SPY cash-dividend payment date
and five earlier, actually fetched Bank of Canada observations so starting NAV
never uses an unpublished FX rate. Original bars are byte-identical and every
original FX row is unchanged.

The original run configuration was repeated, including **simulated USD10,000 plus
CAD10,000**, passive allocation, native fee1 and 5 bps slippage. These are the failed
study's demonstration balances, not the user's funding mandate.

- SPY ex-date June18: four eligible shares × US$1.903516 = **US$7.61** rounded income.
- Pay date July31 is date-only; its time is conservatively set to New York end of day.
  Cash becomes spendable at the next replay event, August3 at 13:30 UTC.
- Receivables enter NAV before payment but cannot fund orders; terminal receivable is zero.
- The saved NAV return is 3.7368%, including recorded gross dividends.
  Canadian action coverage remains incomplete, so total return stays null. This is
  a short engineering/research replay, not evidence for the active stock rule.
- Exact replay passed across all 13 compared fields, including
  full decisions, fills, balances, curves, dividend ledger and unpaid receivables.
- Splits still reject replay: the installed engine's position quantity adjustment
  leaves incorrect average cost basis. Unsupported accounting was not bypassed.

## Evidence and reproduction

| Artifact | Identity |
| --- | --- |
| Final saved scan | `a7f07d83bbc44f0c90d23704a4d994c7` |
| Raw capture | `c9092a143ada4b0fac99b6294025c693` |
| Scanner code | `sha256:ab5d7d75709f8be82ab70711778a08f9965e75c89406be692dfdb6fd584675f0` |
| Enriched raw-bar dataset | `21fd5ae0fdc0f03b03047a4b502bcd36690e29ae11c319d9cb09601bf065746c` |
| Repaired replay | `ba3ba6dd186c4201b7d1a151dd2be024` |
| Financial code | `sha256:67ce5f115783d6ab56a3e42126051a495fd7cf715c25ad6f8f42a0a452a4ec6d` |

Local evidence: `artifacts/scans/<scan_id>/scan.json`,
`artifacts/dividend-remediation-study.json`, `artifacts/funding-scenarios.json`, and
`artifacts/scanner-browser-validation.json`. These generated captures are not
committed as a reusable licensed market-data distribution.

```powershell
& '.venv/Scripts/python.exe' -m frontier.cli scan --cad 700 --usd 0
& '.venv/Scripts/python.exe' -m frontier.cli scan --no-refresh --cad 700 --usd 0
& '.venv/Scripts/python.exe' -m frontier.cli verify-replay ba3ba6dd186c4201b7d1a151dd2be024
& './scripts/verify.ps1'
```

`--no-refresh` reuses the retained capture but checks its age against today's
completed sessions; a future rerun can properly exclude stale current candidates.
The immutable saved scan remains the dated evidence above.

## Automated follow-up and remaining delivery work

The Codex heartbeat **Frontier daily research scan** is active on weekdays at
17:15 in the host's America/Toronto schedule. It captures research snapshots and
compares material changes, staying quiet on unchanged or non-actionable results.
It does not add assumed cash, convert currency, retune the rule, or place orders.
This depends on the local Codex host being available; it is not an always-on broker
service or a guaranteed end-of-day execution process.

Remaining for trading readiness: a validated strategy with prospective net outcomes;
complete action/execution data; actual cash, holdings and cash-flow reconciliation;
cash-flow-adjusted drawdown monitoring; account-specific permissions and costs;
quote/limit-order and recovery testing; and broker-paper reconciliation. Options
also need contract, spread, expiry/exercise and maximum-loss validation. Existing
Codex tools supplied market data, but no Wealthsimple/moomoo execution connector was
available. Neither research return nor broad development permission substitutes for
live-order authority.

Validation and code quality: 114 tests passed, Ruff passed, TypeScript/build passed;
independent reviews corrected provider-symbol validation, dividend replay-verification
coverage, unfunded-currency diagnostics and incomplete-data cash misclassification.
Ponytail full/standard principles kept two scanner modules and one screen without a
new framework or product dependency. All final browser outcomes and any harness
corrections are recorded in the browser evidence and quality review.
