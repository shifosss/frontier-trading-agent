# Strategy action-crossing attribution

September 28, 2026. This bounded review covers **all 54 completed accounts** in `.qualification/strategy-interactions20260928/`. The recorded results do not concentrate in the known action-crossing tails. Every account's recorded net trade P&L is negative, and the partition of trades without a recorded crossing is also negative in every account. This is descriptive partition arithmetic, **not a corrected backtest**.

| Observation | Result |
| --- | ---: |
| Original account trade observations | 191,947 |
| Trades crossing the provider split-labelled inventory | 174 (about 0.091%) |
| Distinct inventory events crossed | 63 |
| Accounts with at least one crossing | 33 of 54 |
| Crossing trades per account | 0–22 |
| Recorded crossing-trade net P&L per account | −US$64.33 to +US$7.13 |
| Largest crossing share of an account's sum of absolute trade P&L | 0.626% |
| Crossings of the previously audited issue union | 0 |
| Original net trade P&L per account | −US$1,993.73 to −US$203.72 |

The 54 accounts are alternative strategy/cost/holding-period simulations. Their trade observations and P&L must not be interpreted as independent investments or summed into one portfolio.

## Meaning of the source join

The existing 7,143-event inventory contains **provider split-labelled events**, including some factors representing distributions and composite actions. It is not an exhaustive corporate-action inventory and does not cover ordinary cash dividends comprehensively. The output category `any_reported_action` means any event **within that inventory**.

A trade crosses an event when its symbol matches and `entry_session < effective_session <= exit_session`. These accounts enter at the next close: entering on the event day after the opening adjustment does not count as holding through that boundary. The join uses the original reported date without a guessed date repair.

The previously audited issue union comprises the five distribution/composite quantity interpretations, the EVO/TOPS nominal discrepancies, and the separately established AIXI September 8 missing adjustment. None was crossed while these accounts held a position. That narrow finding **does not establish clean signal inputs**: an earlier action can still affect features, lookbacks, eligibility or rankings before entry. Omitted events, revised prices, entity mapping and current-member survivorship also remain unresolved.

Each crossing receives its **whole recorded trade P&L**, including the saved costs. This shows where observed economics reside; it does not identify how much profit or loss the action caused. Category groups overlap and cannot be added. No trade crossed multiple inventoried events in this batch, although the attribution method retains that possibility.

## Both positive and negative tails

The largest positive event contribution is **+US$12.10**, from DXC's June 1, 2018 event in several three-session proportional-cost variants. The largest negative is **−US$30.76**, from XTIA's January 7, 2020 event in the three-session volatility-regime selector. These are source-attribution observations, not independently verified action economics.

Eleven crossing trades in nine accounts hit the pre-existing large-adjusted-move triage flag, and all eleven recorded losses. No trade crossed the ratio-alignment triage subset or an event flagged for a missing source boundary. The triage definitions were not selected from this study's returns and remain diagnostic flags, not proof of bad prices.

For every account, the evidence includes the five largest positive and five largest negative contributions separately for all trades, crossing trades and crossed events. Empty sides remain empty; failures and inactive paths would remain visible. All 54 accounts completed and supplied their trade logs.

## Implications for the next strategy experiment

These holding-boundary tails are too small in the recorded results to explain away the grid's losses. The useful next work is strategy economics: signal selectivity, persistence versus reversal, exit timing, turnover and broker-cost exposure. This audit does not justify another round of wholesale source repair before those experiments.

Preserve the current study as a losing comparison set. Any later action-aware data treatment or feature sensitivity should be a separately declared experiment applied consistently across strategies, with affected samples and all outcomes reported. Subtracting these trades' P&L would not reconstruct cash, later position sizes, settlement or the sequence of opportunities.

## Retained evidence and checks

`.qualification/strategy-action-attribution20260928/` contains:

- `definition.json`: rules and source hashes saved before outcome access.
- `account-attribution.csv` / `.json`: all 54 accounts and their observed crossing/noncrossing partitions.
- `category-attribution.csv`: all nine categories per account, including zero counts, both signed contributions and concentration fractions.
- `crossing-trades.csv`: all 174 original account/trade-index references, dates, event identities, recorded amounts and flags.
- `event-attribution.csv`: every crossed event/account contribution.
- `largest-contributions-all54.json`: all signed extreme lists, with deterministic original-index ties.
- `matched-event-definitions.json`, input hashes, arithmetic verification and the isolated analysis scripts.

All 191,947 serialized trade amounts were checked against gross P&L less entry/exit fees, and every account's count/net total reconciled to the original report within the declared float-serialization tolerance. A second method using a direct date predicate reproduced all 174 joins, all 54 partitions and all 216 signed trade-extreme lists. All 54 original result hashes still match. No account was rerun, edited, excluded or relabelled, and no network, broker, production-code or model operation was used.

