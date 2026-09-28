# Intraday continuation and reversal: completed pilot

**September 28, 2026: all four accounts completed and passed independent ledger checks; none is profitable under the declared assumptions.** The [predeclared experiment](intraday-opening-study.md) used actual SIP minutes, a completed opening-hour signal, delayed 10:46 entry and a fixed 12:46 exit. It screened every exchange session in 2017–2025, using 2016 only for warmup. These are repeated two-hour stock trades, not multi-year holdings.

## All four accounts

Each account starts with USD2,000. P is the original proportional 40-bps round-trip sensitivity. M adds the frozen Moomoo Canada US-equity tariff. Both preserve whole shares, fixed cash reservations and historical cash settlement. Costs can change quantities, later affordability and subsequent trades.

| Hypothesis | Cost | Ending USD | Return | Sampled max drawdown | Trades | Gross P&L USD | Modeled costs USD |
|---|:---:|---:|---:|---:|---:|---:|---:|
| Continuation | P | 1,131.69 | -43.42% | 43.70% | 869 | -10.67 | 857.64 |
| Continuation | M | 55.35 | -97.23% | 97.23% | 420 | -9.53 | 1,935.11 |
| Reversal | P | 1,158.10 | -42.09% | 42.12% | 772 | -55.59 | 786.30 |
| Reversal | M | 56.05 | -97.20% | 97.20% | 418 | -7.50 | 1,936.46 |

All 2,479 trade observations are retained. All four paths exceed the owner's 30% drawdown limit; none qualifies for promotion. The research accounts continue through those losses to expose the failure, rather than claiming deployable risk management. Unchanged cash beats every account; cash interest is not modeled.

**The failure is not solely an assumed-fee issue.** Recorded gross trade P&L is slightly negative in every account, although modeled costs explain most of the capital loss. These gross dollars use the actual fee-affected quantities and cash paths. Removing fees arithmetically is not a fee-free account replay and does not prove that every alternative execution route would produce exactly the same result.

## Stability and activity

Both P accounts lose in every one of the nine calendar years. Continuation has only 8 positive months out of 108; reversal has 6. Net win rates are 22.67% and 22.80%, with net expectancy of -USD1.00 and -USD1.09 per completed trade. Regular-session time-weighted invested exposure is only 1.92% and 1.74%. Low exposure did not make either profitable.

Neither M account records a profitable completed trade. Both remain flat in 2024 with roughly USD60 left; that is depleted buying capacity, not successful risk selection. Their tiny positions suffer minimum order charges. A machine-precision weekly value of approximately 2.2e-16 in the continuation record is economically zero and is not a profitable week.

F, T, AAPL and MSFT account for almost every trade. HRL contributes just three continuation/P and four reversal/P trades; BANF contributes none. The USD0.32 total net gain on four HRL reversal trades is not a reason to select that name as a winner. No stock was added, removed or replaced after outcomes.

The unfunded descriptive reference has 4,314 causally eligible stock-session events, of which 4,313 have both endpoints, across 1,892 matched dates. The single unmatched event lacks both entry and exit prices. Its equal-date gross mean is approximately **0.745 basis points**. That is an event average, not a funded return, and cannot be compared directly with cumulative account percentages. All four funded accounts retain the same reference denominators.

## Source coverage and execution limits

All 2,514 source sessions completed transport. The archive contains **6,064,767 valid unique observed minute bars** out of 6,836,760 expected symbol-minute slots; **771,993 slots remain missing**. No bar was invented. BANF supplies 753,134 of those gaps and only one complete opening hour in the entire capture. Its causal warmup requirements therefore never produce a trade. HRL has 14,019 missing minutes; the other five series have 104–1,666 each. Missing trading observations do not automatically mean a provider outage.

The account audit retains every source/session identity. Complete transport does not mean complete observations. Required entry/exit prices happened to be present for every executed position; sparse generic-reference events remain visible. Observed holding-period marks required no stale carry in these four paths, but sampled-minute drawdown still does not establish the worst movement within a minute.

These are six surviving, purposive source-fixture stocks and revised historical provider data. The experiment is not representative of the entire US market and does not establish all corporate actions, original publication vintages, actual broker fills or implementation capacity. The minute reference opens and 40-bps costs are declared simulation conventions. Published broker charges, quoted spreads, account subscription costs and CAD/USD funding remain separate evidence.

## Research decision

Do not promote either opening rule, tune its thresholds to these outcomes, or select only the handful of profitable stock/trade subsets. Preserve the completed experiment as a failed hypothesis and a reusable, source-qualified intraday test path. A separately declared broader or richer model can still be tested; this pilot does not prove that all intraday strategies fail.

The next distinct input family is original quarterly financial disclosures. A [bounded SEC source study](../.qualification/filing-feasibility20260928/results.md) verified three original filings and a [specific post-filing hypothesis](../.qualification/filing-feasibility20260928/strategy-memo.md) is documented. Its full historical inputs and performance remain unqualified. The separate 144-cell quote study adds independent dates and the actual entry/exit clock windows; it does not retroactively change these four accounts.

## Reproduction

Evidence lives under `.qualification/intraday-opening-strategy20260928`. `completed.json` points to attempt `75d60237bbe6436da358465eb6d3d820`, with four ledgers, every session audit, full minute NAV marks and weekly/monthly/yearly returns. Definition `d9c539e611076c9d2a18c56aa2e9f9e0a702411dcb0fcb9f96ea08b7568f3463` and source-input identity `95b967e77b2f04e642ba7e6c9d0e24fcffd71ec48107bb33dc93cf54f398ae6c` remain frozen. `economic-results.json` summarizes every path. Twenty-eight strategy/source/runner checks and independent pre-execution review passed; the separate ledger auditor passed thirteen synthetic checks before auditing actual results.

`independent-intraday-audit-20260928T221259Z.json` passed all four complete ledgers with zero audit failures: 2,479 trades, 2,852 orders and 287,990 account marks, rereading 2,282 required source sessions. It independently reconstructs fees, reservations, cash, receivables, observed-minute valuation and period metrics, and checks the recorded causal signal inputs and fills. It reuses the frozen source adapter and settlement calendar. It does not independently regenerate the complete candidate selection set; arithmetic verification does not establish economic validity or actual executable fills.
