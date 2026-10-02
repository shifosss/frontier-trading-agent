# Disclosure timing: completed cached metadata audit

**October 1, 2026: 3,732 of 4,057 original 10-Qs (91.99%) have at least one same-issuer original 8-K Item 2.02 candidate in the preceding declared window. This is metadata linkage, not verified earlier disclosure of the same fiscal period or financial components. No strategy was promoted.**

The [source-only design](disclosure-novelty-research.md), [immutable definition](../.qualification/disclosure-novelty20261001/definition.json) and [UTC clarification](../.qualification/disclosure-novelty20261001/clarification.json) were saved before extraction. The same 100 issuers and every registered original filed in 2012–2025 remain. The audit reused 179 original SEC discovery responses and made zero HTTP/document requests, extracted no financial facts and read no prices, returns, model predictions or account ledgers. It did not rerun the completed earnings accounts.

## All requested events

| Event category | Original 10-Qs |
|---|---:|
| Exactly one preceding original 8-K Item 2.02 candidate | 3,531 |
| Multiple preceding candidates | 201 |
| Equal/later candidate only, within declared windows | 248 |
| No observed qualifying candidate in the declared windows | 77 |
| **Total requested originals** | **4,057** |

There are 3,941 primary preceding pairs: 193 originals have two, eight have three, and 3,531 have one. The remaining 325 have none. All 201 multiple cases remain ambiguous; no nearest/latest release was selected. Same-clock events are separate, not earlier. Outside-window and unavailable evidence remains recoverable from the retained groups and each requested event's exhaustive counts.

The fixed matching convention uses explicit aware API acceptance instants and elapsed UTC durations: preceding `[Q−45×86,400 seconds,Q)`, equal instant separately, and late `(Q,Q+7×86,400 seconds]`. Original 8-Ks need the exact comma-delimited `2.02` token. Amendments never replace originals.

The audit retains 27,327 8-K/8-K/A metadata groups. All observed Q and K API clocks are aware, and no conflicting accession dictionaries occurred. Item metadata has 8,115 qualifying-token groups, 17,406 valid nonmatching groups and 1,806 unusable item encodings. These group counts include amendments and filings outside the Q matching windows; they are not 8,115 proven earnings releases. The row files retain every literal encoding, form and source origin.

All 3,867 captured and 190 incomplete original 10-Q captures remain in the requested denominators; an incomplete financial capture does not delete a metadata event. Thirteen lookback windows reach before the original 2012 filing-date envelope; none reach beyond the late upper envelope. Even an in-envelope window is not proven exhaustive of all prior earnings releases or public channels. The 77 no-observed cases are not proof of no earlier disclosure.

## Timing readout

A [separate diagnostic declaration](../.qualification/disclosure-novelty20261001/timing-diagnostics-definition.json) was saved after the audit's candidate counts were known and before reading its lead-time distribution. It did not change candidate rules or select a preferred release. Every one of the 3,941 primary pairs is included.

- Metadata lead ranges from **5 seconds** to **3,848,692 seconds** (about 44.55 days); its median is **88,098 seconds**, or **24 hours 28 minutes 18 seconds**. The mean is about 4.98 days. These are acceptance-time differences, not verified market-publication or executable-trade delays.
- 1,320 pairs have the same ET acceptance civil date; 2,621 have an earlier ET date.
- 1,316 requested Q events have at least one same-date candidate; 2,484 have at least one earlier-date candidate. These event categories overlap in 68 cases. Their union is 3,732.

The [separate exact-arithmetic review](../.qualification/disclosure-novelty20261001/review-v2/timing-review.json) independently verified all primary durations, ET date classes and zero/multiple-event counts. These clustered candidate pairs are not independent samples. In particular, a five-second earlier acceptance supplies no evidence of a usable earlier strategy decision. Original release content, fiscal period and component availability remain unverified for **every** pair. The later 10-Q's S/Q values were never backdated.

## Every filing year

| Filing year | Requested Qs | With preceding candidate | Multiple | Original financial capture incomplete |
|---|---:|---:|---:|---:|
| 2012 | 263 | 239 | 13 | 13 |
| 2013 | 269 | 249 | 15 | 15 |
| 2014 | 279 | 263 | 15 | 11 |
| 2015 | 289 | 271 | 20 | 14 |
| 2016 | 290 | 264 | 9 | 13 |
| 2017 | 292 | 268 | 11 | 13 |
| 2018 | 297 | 272 | 14 | 12 |
| 2019 | 293 | 271 | 12 | 13 |
| 2020 | 296 | 271 | 24 | 12 |
| 2021 | 296 | 270 | 13 | 13 |
| 2022 | 297 | 271 | 21 | 13 |
| 2023 | 297 | 273 | 13 | 15 |
| 2024 | 299 | 276 | 11 | 16 |
| 2025 | 300 | 274 | 10 | 17 |

All 1,400 issuer/year rows—including zero-count years—are retained in the [denominator table](../.qualification/disclosure-novelty20261001/attempts/f6326cbd442d4ba08594221006e338eb/issuer-year-denominators.json). These are source-population counts for 2012–2025. They are not a correction of the previous 2021–2025 trading accounts or a joined analysis of winning/losing trades.

## Verification, failures and reproduction

Actual attempt `f6326cbd442d4ba08594221006e338eb` completed once. Definition SHA256 is `3946aac2f8f4bd0ab697ae36ba9ce41ee117fb2d05b4e40d0fe0a6485902b9a3`; execution implementation SHA256 is `8bb12faf676ce9136a1b06552a67b60bae6a73ed65d28f7dd6c1a478dee6a628`. The [compact result](../.qualification/disclosure-novelty20261001/attempts/f6326cbd442d4ba08594221006e338eb/report.json) and [terminal output identities](../.qualification/disclosure-novelty20261001/attempts/f6326cbd442d4ba08594221006e338eb/completion.json) retain exact sources and outputs.

Thirty-two focused synthetic tests and repository-rule Ruff checks passed. The initial sandbox test run encountered temporary-directory permission errors; the scoped rerun passed. Root code review corrected repo-relative `.qualification` source-path handling before execution and retained a regression check. No shared model/cash engine or frozen operator code changed.

The first independent actual review failed because its checker reconstructed five source-origin fields while the producer retained eight. Its original checker, attempt, stderr and failure remain unchanged. The separately versioned checker added independent verification of raw byte size, root/history table kind and exact original history descriptor. It retained full eight-field equality rather than discarding assertions. V2 passed against the **unchanged** actual outputs: 4,243 frozen input identities, 179 raw responses, 200,363 raw row occurrences, 27,327 metadata groups, all 4,057 requested events, 1,400 issuer/year rows, 1,127,625 Cartesian classifications, all 8,973 serialized near-window pairs, all 3,941 primary pairs and seven terminal outputs. See [the passing independent review](../.qualification/disclosure-novelty20261001/review-v2/verification.json). The study itself was not rerun.

Raw discovery responses already belong to the retained earnings corpus. New local row-level files are `metadata-records.jsonl` (42,732,624 bytes), `events.json` (13,496,897 bytes) and `pairs.jsonl` (5,956,464 bytes) under this attempt. They are omitted from ordinary Git; compact declarations, summaries, denominators, code, reviews and exact output identities are published. Keep this new study directory with the owner's separate Google Drive research backup; the earlier handover inventory is a dated snapshot that predates it.

## What this changes

The prevalence makes an earlier-disclosure investigation useful. It does **not** show that stale information caused the poor earnings results, that cash backing was already public, or that an earlier strategy earns money. It also does not qualify original-header entity continuity for a retrospective metadata candidate.

The next step is a separately declared, bounded original 8-K document/exhibit probe with source-only deterministic selection and no financial/return-based replacements. Verify original accession and matching filer CIK, link the fiscal period, and identify which facts were actually public. Only then consider a separately declared earlier-time feature/account comparison using those facts at their qualified availability clock. Completed financial studies and this unchanged metadata audit remain frozen. The separately authorized eleven-stock Alpaca paper baseline is unchanged.
