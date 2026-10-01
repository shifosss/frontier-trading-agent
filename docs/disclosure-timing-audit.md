# Earnings disclosure timing: declared 8-K Item 2.02 audit

**October 1, 2026: declared, frozen and tested offline. Not yet run.** The audit needs retained SEC metadata that is not in a fresh clone. No 8-K row, price, return, S/Q value or exhibit has been read.

## Why this is next

The [cash-backed earnings comparison](earnings-quality-results.md) decided at 09:00 ET after each original 10-Q became public. Both learned families did worse than a fitting-only mean forecast, and no account reached a 5% week. One untested explanation is timing. Companies usually announce quarterly results in an earlier 8-K under Item 2.02, so by the 10-Q decision session part of the S/Q information may already have been priced. This audit measures how often such an earlier filing exists. It tests no strategy.

## What is frozen

The study lives in [`.qualification/disclosure-timing20261001`](../.qualification/disclosure-timing20261001/interface.md). Definition SHA256: `6c3053d40d0a384705d5eff551138894c3f158500335a8fc7707210e5c07ab47`.

- **Denominators:** all 100 issuers and 4,057 registered original 10-Qs, including the 190 failed captures. The 3,867 captured originals and the 2,010 strategy-source-qualified events are reported as separate strata, and each filing year is also reported. No issuer is replaced or dropped.
- **Candidate:** a same-CIK original `8-K` whose `items` field holds the exact token `2.02`, filed after the 10-Q period end and within 83 days of it. The shortest 12-week next quarter ends on day 84, so its results release cannot fall in the window. Review moved this bound from 84 to 83 days before any run; see `amendment-01.json`. `8-K/A` rows are counted but are never candidates.
- **Clock:** the completed study's `event_clock` is reused unchanged for both filings. A candidate is `prior` only if its decision session is strictly earlier than the 10-Q's. Every 10-Q session is recomputed from its frozen manifest and must match the completed study's saved session, including for issuers whose sources are unavailable, or the attempt stops.
- **Ambiguity:** conflicting duplicate accessions, in-window 8-Ks without items metadata and unclockable candidates are kept as `ambiguous_metadata`. A window outside the retained submissions date ranges is kept as `window_coverage_incomplete`. Both stay in the denominator.
- **Verdict (2,010 qualified events):** `supported_at_metadata_level` if at least 50% have an unambiguous prior candidate. `not_supported_at_metadata_level` if fewer than 20% could possibly have one, counting every unavailable, uncovered or ambiguous row as possible. Otherwise `inconclusive`.

## What it cannot show

Item 2.02 metadata says an earnings-related release was furnished. It does not say whether the release reported the same quarter, net income, year-to-date operating cash flow or assets. Submissions API acceptance times are not header-verified and are not proof of first public dissemination. A `supported` verdict therefore justifies only the next separately declared step: a bounded, seeded random sample of original press-release exhibits, recording which S/Q components were actually public. Only components shown to be public may ever be used at the earlier clock, in a new predeclared economic comparison.

## To run it

Restore the retained files listed in the [study interface](../.qualification/disclosure-timing20261001/interface.md#inputs-to-restore-before-the-real-run). They total about 110 MB plus 79 small history pages and the empty capture lock file, not the 31.8 GB corpus. Then run `audit.py --preflight` until it reports `ready: true`, and run `audit.py` once. Record the attempt and summary in a dated `*-results.md` next to this file.
