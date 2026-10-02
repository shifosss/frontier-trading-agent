# Earnings disclosure timing: declared 8-K Item 2.02 audit

**October 1, 2026: declared, frozen and tested offline. October 2: run once; the primary verdict is `supported_at_metadata_level` (prior share 63.9–64.4% of the 2,010 qualified events). See the [results](disclosure-timing-results.md).** No price, return, S/Q value or exhibit was read. Before the run, an earlier schema-only inspection, recorded in the handbook, counted 26,712 raw 8-K occurrences and their field completeness without matching any of them.

## Why this is next

The [cash-backed earnings comparison](earnings-quality-results.md) decided at 09:00 ET after each original 10-Q became public. Both learned families did worse than a fitting-only mean forecast, and no account reached a 5% week. One untested explanation is timing. Companies usually announce quarterly results in an earlier 8-K under Item 2.02, so by the 10-Q decision session part of the S/Q information may already have been priced. This audit measures how often such an earlier filing exists. It tests no strategy.

## What is frozen

The study lives in [`.qualification/disclosure-timing20261001`](../.qualification/disclosure-timing20261001/interface.md). Definition SHA256: `e48d158b119094f0b320a3d0f875eb27475febc93688bb29b3ba397c9c151ca2`.

- **Denominators:** all 100 issuers and 4,057 registered original 10-Qs, including the 190 failed captures. The 3,867 captured originals and the 2,010 strategy-source-qualified events are reported as separate strata, and each filing year is also reported. No issuer is replaced or dropped.
- **Candidate:** a same-CIK original `8-K` whose `items` field holds the exact token `2.02`, filed after the 10-Q period end. The window closes at day 83 or the day before the issuer's next period end, whichever comes first, so a later period's results release cannot fall in it. The next period end is the next frozen 10-Q, or an original 10-K/10-KT/10-QT in the issuer's submissions. The shortest 12-week quarter ends on day 84. Three issuers have consecutive 10-Q period ends only 52–81 days apart, and ROP has a 10-K period end 61 days after a 10-Q. Review made these changes before any run; see `amendment-01.json`, `amendment-06.json` and `amendment-10.json`. `8-K/A` rows are counted but are never candidates.
- **Clock:** the completed study's `event_clock` is reused unchanged for both filings. A candidate is `prior` only if its decision session is strictly earlier than the 10-Q's. Every 10-Q session is recomputed from its frozen manifest and must match the completed study's saved session, including for issuers whose sources are unavailable, or the attempt stops.
- **Ambiguity:** conflicting duplicate accessions, in-window 8-Ks without items metadata and unclockable candidates are kept as `ambiguous_metadata`. A window outside the retained submissions date ranges is kept as `window_coverage_incomplete`. Both stay in the denominator.
- **Verdict (2,010 qualified events):** `supported_at_metadata_level` if at least 50% have an unambiguous prior candidate. `not_supported_at_metadata_level` if fewer than 20% could possibly have one, counting every unavailable, uncovered or ambiguous row as possible. Otherwise `inconclusive`.

## What it cannot show

Item 2.02 metadata says an earnings-related release was furnished. It does not say whether the release reported the same quarter, net income, year-to-date operating cash flow or assets. Submissions API acceptance times are not header-verified and are not proof of first public dissemination. A `supported` verdict therefore justifies only the next separately declared step: a bounded, seeded random sample of original press-release exhibits, recording which S/Q components were actually public. Only components shown to be public may ever be used at the earlier clock, in a new predeclared economic comparison.

## Status and verification

The audit has run once (attempt `31316f533e4f4c0e829d9e5bfbc4c6a4`, see the [results](disclosure-timing-results.md)). Do not restore inputs to run it again: `audit.py --preflight` now reports `ready: false` because that attempt already used the frozen definition, and `audit.py` refuses before creating anything. A rerun needs a new declared amendment that records why.

To verify the committed record without the retained inputs:

1. Run the synthetic tests: `.venv/bin/python -B -m pytest .qualification/disclosure-timing20261001/test_audit.py -q -p no:cacheprovider` (on Windows `.venv/Scripts/python.exe`).
2. Check that `definition.json` hashes to the `definition_sha256` in `freeze.json` and in the attempt's `attempt.json`, and that each amendment record matches its SHA256 in `freeze.json`.
3. Check that each file under `attempts/31316f533e4f4c0e829d9e5bfbc4c6a4/` matches the SHA256 listed in `attempt.json` `files`.

The next stage is a separately declared, seeded exhibit-content probe of qualified `single_prior` candidates; it needs its own declaration and the owner's approval before any SEC request.
