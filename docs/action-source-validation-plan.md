# Corporate-action source validation plan

September 28, 2026. A source-only inventory now covers every usable history in frozen capture `90af4c840aad48f7ab58fba7a682f96a`. It reads no strategy P&L, model outputs or account journals, makes no network requests, and changes no production code or historical source. The declaration was saved before event-price inspection.

## Completed inventory

| Coverage | Count |
| --- | ---: |
| Frozen source hashes verified | 8,234 |
| Sources containing provider-reported split events | 3,581 |
| Reported events | 7,143 |
| Forward / reverse factors | 2,703 / 4,440 |
| USD / CAD events | 4,929 / 2,214 |
| Missing required boundary bars or prices | 51 |
| Source hash / parsing failures | 0 |
| Original failed instrument captures, still unavailable | 200 |

Events range from December 31, 1999 to September 18, 2026. The 1999 events may precede requested price history and remain visible as missing boundaries. No invalid positive-ratio components or duplicate effective dates occurred. "Split" is the provider's category, not independent proof that an event is a simple share split or a complete record of ADS, merger, spin-off or distribution mechanics.

Every event retains its source URL and hash, symbol, currency/calendar, original event fields, effective session and ratio, exact preceding/effective/on-or-after source bars, adjusted and quoted closes, high/low/volume, and the current normalizer's reconstructed nominal prices and volumes. An absent effective-session bar is not filled from another session. The factor calculation matches the existing normalization convention; it does not certify that the vendor actually used that convention. The separate [AIXI audit](aixi-source-continuity.md) demonstrates why that distinction matters.

Two predeclared heuristics identify triage candidates: an adjusted price change whose absolute log is at least `log(1.5)`, and the subset whose adjusted price ratio multiplied by the reported new/old share ratio is within `log(1.2)` of one. They flag 600 large moves and 12 factor-aligned cases, respectively. Both signs are retained. These arbitrary screening tolerances are **not repair rules, acceptance criteria or proof of error**; no economic result selected them. True price moves can trigger either flag, and real action errors can escape them.

## Frozen independent validation sample

The follow-up sample contains **91 events**, one from each populated cell of a maximum 96-cell design. Cells combine USD/CAD, forward/reverse factors, four eras (through 2009, 2010-2019, 2020-2023, 2024-2026), factor magnitude at most two versus greater than two, and a native-currency activity proxy below one million versus at least one million versus unavailable.

The activity proxy is median provider close times provider volume over the 20 preceding bars, requiring at least 10 finite positive observations. It is a source-derived proxy, not verified execution liquidity or market capitalization; USD and CAD levels are not converted. Within each cell, the smallest SHA-256 of a declared seed and event identity selects the event. Neither returns nor triage flags enter selection. Missing boundaries remain eligible, and unsuccessful source validation must not be replaced with another event. The five empty cells are recorded.

A separate verifier reproduced all 91 minimum ranks, compared their boundary factors with the existing `_reported_split_factors` helper, and checked 14,229 price-volume products. This verifies implementation and source bookkeeping, not action truth. The primary sample is independent of the anomaly flags; targeted cases such as AIXI must be reported separately rather than substituted into it.

## Follow-up protocol

1. Freeze the 91 selected identities before requests. Obtain issuer, exchange or depositary evidence for effective dates, old/new securities, share ratios and applicable cash/fees. Preserve unavailable sources and contradictory notices. Use existing access/free sources only.
2. Compare independently sourced raw and adjusted daily observations around each boundary with explicit entity mapping, timezone, feed, timestamp and adjustment vintage. Set validation tolerances using source rounding, tick precision and session conventions before examining strategy outcomes. Record revisions and price/volume differences; quoted bars do not prove executable fills.
3. Classify each case as corroborated, contradicted or unresolved, with evidence. Assess large upward and downward movements symmetrically. No blanket outlier deletion, guessed split or correction based on profitable outcomes is permitted.
4. Any correction becomes a separately versioned dataset, preserving the original. Separate common-unit synthetic labels from actual nominal prices, quantities, fractional entitlements, action charges and settlements. Rebuild affected features, preprocessing, every model and ensemble calibration as new candidates; never patch model metadata to claim compatibility.
5. Compare all declared original and revised paths, including losses, failed paths, abstention, changed eligibility and costs. A sample inventory does not qualify a trading policy or a whole-account action ledger.

The inventory cannot find actions omitted entirely by the provider, nor establish historical listing completeness. The original 200 capture failures, current-member survivorship and unresolved non-split action mappings remain limitations. Broader action coverage needs a separately declared study.

## Retained evidence

`.qualification/action-inventory20260928/` contains `definition.json`, `inventory_actions.py`, `events.jsonl`/`.csv`, `source-coverage.jsonl`, `failures.json`, the original capture failures, `triage-flags.csv`, `validation-sample.csv`, `sample-strata.csv`, `summary.json`, `verify_inventory.py`, `verification.json` and a SHA-256 inventory. The source payloads remain at their original content-addressed paths; their hashes and the original capture-index hash are retained. The complete inventory took approximately 77 seconds.
