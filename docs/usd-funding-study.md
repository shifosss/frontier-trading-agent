# Planned USD funding — September 18, 2026

The user accepts converting CAD into USD for active trading. The system now models
that funding explicitly, while preserving the no-borrowing mandate and both reserved
ETF portfolios. A 100% conversion is an illustrative comparison, not a confirmed
capital allocation. No currency, security, account subscription or broker setting
was changed.

## Implemented behavior

The Scanner has **CAD to convert (simulation)** beside the initial CAD/USD balances.
A planned amount is deducted from CAD once and the estimated net proceeds are added
to existing USD. The saved artifact includes the original cash, post-conversion cash,
fee, FX reference time and source digest. Both ranking and historical diagnostics
receive the same post-conversion balances. Reopening or rerunning a saved plan
restores its original cash inputs; it does not convert already-converted cash again.

A zero conversion keeps the original native-currency behavior and makes no FX data
request. A requested amount above available simulated CAD is rejected before any
source fetch. The planner uses only an already published Bank of Canada observation;
a refreshed public capture avoids reusing a pre-publication response after the day's
rate is available. This is an indicative reference, not an executable broker quote.

## Funding amounts and costs

Latest available reference in this run: **1.3988 CAD per USD**, observation September 17,
availability inferred at 16:30 Toronto. The reference and its exact retained raw
capture are in `artifacts/usd-funding-study.json`.

For a CAD amount `C`, CAD-per-USD rate `r`, and percentage conversion fee `f`:
`USD credit = floor_to_cents(C × (1 − f) / r)`.
The fee is already inside the CAD debit; subtracting it again would double-charge it.

The preview uses the published Wealthsimple USD-account cash conversion tiers:
1.5% below CAD10,000; 1% from CAD10,000; 0.5% from CAD25,000; 0% from CAD100,000, applied to the whole
transaction. These thresholds use CAD because this planner converts CAD into USD.
[Wealthsimple official fee schedule](https://www.wealthsimple.com/en-ca/legal/fees/trade).

| Illustrative total CAD debit | Embedded conversion fee | Estimated USD credit |
| ---: | ---: | ---: |
| CAD600 | CAD9.00 | US$422.50 |
| CAD700 | CAD10.50 | US$492.92 |
| CAD800 | CAD12.00 | US$563.34 |

These figures exclude the broker's variable exchange-rate spread, any account
subscription and applicable taxes. Existing USD-account access is assumed, not
verified. The source is the [Bank of Canada USD/CAD series](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?start_date=2026-09-04&end_date=2026-09-18).

The scenario retains USD between US-stock trades, so conversion is a funding cost,
not a new 1.5% charge on every trade within the USD account. Converting proceeds back
to CAD is a separate future cost. Norbert's Gambit remains a route to compare using
actual journaling charges, spreads, settlement and account fees; this preview does
not claim to execute or quote that route. See [account readiness](active-account-readiness.md).

## Actual funded-US test

CAD700 with USD0, converting CAD700, produced **CAD0 and USD492.92**. The fixed
scanner selected **no current stock** from its 11 declared US stocks under the
existing whole-share, 20% position and 0.5% ATR-risk budgets. The native-book risk
distance budget is only about US$2.46 per name. This is a narrow universe and sizing
constraint, not a claim that the US market lacks opportunities. Fractional execution
and a broader investable universe require separate implementation and validation;
risk thresholds were not relaxed to force a trade.

The funded USD retrospective diagnostic completed 238 cohorts,
with 28 candidate observations, 28 selected-candidate
cohorts and 210 cash cohorts. The mean five-session native USD cohort return
was 0.2693% after 20 bps assumed trading costs, versus
0.0628% for matched SPY cohorts; at 40 bps it was
0.2458%. CAD was correctly marked unfunded.

**This positive diagnostic average does not establish a deployable strategy.** It
is sparse, retrospective, equal-weight within each selected cohort, and based on
today's selected universe. It is not the return of the cash-weighted sized account.
Provider historical closes may already reflect stock splits, so historical
whole-share affordability does not reconstruct actual pre-split tradability.
Conversion fees lower the example starting USD budget, but the reported USD cohort
percentages exclude conversion/return-conversion costs, subscriptions, tax and
CAD/USD valuation changes. The same fixed nominal USD budget is reused per cohort;
there are no modeled monthly deposits or compounded portfolio returns.

## Reproduce and inspect

```powershell
& '.venv/Scripts/python.exe' -m frontier.cli scan --cad 700 --usd 0 --convert-cad 700
& '.venv/Scripts/python.exe' -m frontier.cli scan --no-refresh --cad 700 --usd 0 --convert-cad 700
```

[Open the scanner](http://127.0.0.1:8765/). Saved scan: `3ecfde6b79664d0f97ff5a7e365224d3`.
Stock capture: `86084e25411142b7a3cdf589cd23457d`. Scanner source identity:
`sha256:acc0c749e276a297a29ba67c6d60eded03eaab7f388cee5c32dbed1f226094e8`. CLI output now includes the diagnostic limitations
alongside its summary, as required by the independent disclosure review.

The existing weekday 17:15 Toronto heartbeat now compares native CAD and illustrative
USD-funded cases, fetching stock data once and reusing it for the second case. It
compares like-for-like scenarios across days and does not increase assumed capital,
perform conversions or promote a strategy automatically.

## Verification and review

- **132 tests passed in 80.37 seconds**, Ruff, TypeScript and production build passed.
- Funding tests cover cash conservation, existing USD, one fee application, whole-
  transaction fee-tier boundaries, no-source-call on zero conversion, excessive
  conversion and unavailable/future references.
- Integration verifies both scanner calculations use the post-conversion cash.
- Actual Chrome submitted the funded scenario through the running API, verified
  its response and exact downloaded evidence, switched between older native-cash
  and new conversion artifacts, and reloaded without double deduction.
- Desktop/mobile checks at 1440, 768, 390 and 320 pixels reported no page/HTTP errors or
  horizontal overflow. Evidence: `artifacts/usd-funding-browser-validation.json`.
- Independent review found no debit/credit defect; its CLI disclosure finding is
  fixed. Ponytail full/standard review retained one narrow helper using existing
  source capture and Decimal, with no new product dependency or broker adapter.
