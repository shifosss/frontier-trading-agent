# October 1 disclosure metadata audit: continuation addendum

The source-only audit completed once as `attempts/f6326cbd442d4ba08594221006e338eb`. Start with [the source-only design](../../docs/disclosure-novelty-research.md) and [completed results](../../docs/disclosure-novelty-results.md). All 100 issuers and 4,057 original 10-Qs remain; 3,732 have preceding original 8-K Item 2.02 metadata candidates. This does not verify the fiscal period, financial components, dissemination clock or an earlier trading edge.

| Evidence | Purpose |
|---|---|
| [Definition](definition.json) / [UTC clarification](clarification.json) | Pre-extraction population, source identities and candidate criteria |
| [Execution identity](implementation.json) / [decision register](decision-register.json) | Reviewed code bindings, software checks and ten decision reasons |
| [Actual completion](attempts/f6326cbd442d4ba08594221006e338eb/completion.json) / [summary](attempts/f6326cbd442d4ba08594221006e338eb/report.json) | Exact immutable output identities and all result categories |
| [Issuer/year denominators](attempts/f6326cbd442d4ba08594221006e338eb/issuer-year-denominators.json) / [input identities](attempts/f6326cbd442d4ba08594221006e338eb/input-identities.json) | All requested population rows and frozen source binding |
| [Preserved initial review failure](review/failure.json) / [passing v2](review-v2/verification.json) | Checker schema correction with unchanged actual audit outputs |
| [Timing declaration](timing-diagnostics-definition.json) / [readout](timing-diagnostics.json) / [independent timing review](review-v2/timing-review.json) | Every primary pair and every zero/multiple event, without candidate selection |
| [Local artifact inventory](artifact-inventory.json) | Exact size/hash of this later study's files and explicit Git publication decisions |

Original discovery responses remain in the earnings corpus. Three new row-level outputs—`events.json`, `metadata-records.jsonl` and `pairs.jsonl`—remain local and are omitted from ordinary Git. Preserve this entire directory's relative layout in the separate research backup, alongside the existing earnings sources. The original handover inventory predates these files. A clone contains compact declarations/code/reviews, not the full raw metadata corpus or those new rows.

The audit needs its declared inputs to reproduce; do not rerun it unchanged simply because a clone lacks raw files. To check software only, run the 32 synthetic tests with Python3.13 and the existing frozen environment:

```powershell
& '.venv/Scripts/python.exe' -B -m unittest discover -s '.qualification/disclosure-novelty20261001' -p 'test_audit.py'
```

These tests do not qualify source documents or economic outcomes. Next declare a bounded original 8-K document/exhibit probe with deterministic source-only membership, no return/extraction-success replacements and no broad new financial capture. Verify the original filer CIK, fiscal period and components actually public before any separate earlier-time strategy comparison. Never backdate later 10-Q S/Q values. Existing economic studies and the paper baseline remain unchanged.
