# Earnings disclosure timing: 8-K Item 2.02 audit results

**October 2, 2026: the frozen audit ran once and completed. Primary verdict: `supported_at_metadata_level`.** For 1,284 to 1,294 of the 2,010 strategy-qualified 10-Q events (63.9% to 64.4%), a same-company original 8-K with Item 2.02 became public at least one XNYS session before the 10-Q's decision session. This is filing metadata only. It does not show which S/Q components the earlier release contained, it changes no completed result, and it promotes no strategy.

## Run identity

- Attempt `31316f533e4f4c0e829d9e5bfbc4c6a4` under definition SHA256 `e48d158b119094f0b320a3d0f875eb27475febc93688bb29b3ba397c9c151ca2` (amendment-12), status `complete`. It started 2026-10-02 02:05:16 UTC and took 26 seconds.
- Runtime: CPython 3.13.14 on Linux, SQLite 3.45.1, `tzdata` 2026.4 with an empty zoneinfo search path. America/New_York TZif SHA256 `d7f2206b…1fa9`.
- No network requests, and no prices, returns, S/Q values or exhibits read. Both source read locks and the audit lock were held throughout.
- Preflight before the run: `ready: true`, nothing blocking, 0 `issuer_unavailable`.
- The inputs came from the owner's Google Drive copy of the retained workspace. Only the 249 needed files (97.7 MB) were fetched, out of a 31.8 GB corpus:
  - 69 `discovery.json` files
  - 100 root submissions sources
  - 79 history pages
  - the calendar
  - the qualification `events.json`, fetched as a gzip copy because it exceeds the connector's 10 MB limit and decompressed back to its exact bytes
- Every fetched file matched its frozen SHA256 before the run. The two source lock files were empty in the original and were recreated byte-identical.
- [`attempt.json`](../.qualification/disclosure-timing20261001/attempts/31316f533e4f4c0e829d9e5bfbc4c6a4/attempt.json) binds 209 input identities and 179 raw-source identities. All five attempt files are committed: `attempt.json`, [`summary.json`](../.qualification/disclosure-timing20261001/attempts/31316f533e4f4c0e829d9e5bfbc4c6a4/summary.json), [`issuers.json`](../.qualification/disclosure-timing20261001/attempts/31316f533e4f4c0e829d9e5bfbc4c6a4/issuers.json), and the per-10-Q [`events.json`](../.qualification/disclosure-timing20261001/attempts/31316f533e4f4c0e829d9e5bfbc4c6a4/events.json) (SHA256 `862d0c09…a394`) and `events.csv` (SHA256 `23bdfc22…dfd9`). The per-10-Q files carry SEC filing metadata only and are what a next-stage sample would draw from.

## Every 10-Q, by stratum

| Status | All registered (4,057) | Captured (3,867) | Strategy-qualified (2,010) |
|---|---:|---:|---:|
| issuer_unavailable | 0 | 0 | 0 |
| q_metadata_unavailable | 0 | 0 | 0 |
| q_session_unavailable | 0 | 0 | 0 |
| window_coverage_incomplete | 46 | 44 | 10 |
| ambiguous_metadata | 0 | 0 | 0 |
| no_candidate | 85 | 81 | 23 |
| single_prior | 2,349 | 2,272 | 1,166 |
| single_same_session | 1,325 | 1,238 | 686 |
| single_after | 22 | 7 | 1 |
| multiple | 230 | 225 | 124 |
| **Prior share, lower bound** | 63.30% | 64.29% | **63.88%** |
| **Prior share, upper bound** | 64.43% | 65.43% | **64.38%** |
| Verdict | supported | supported | **supported** |

The lower bound counts only unambiguous prior candidates; 118 of the 124 qualified `multiple` rows have one. The upper bound also counts every row that could have one, which here means only the 10 qualified rows whose window falls outside the retained submissions coverage. Both bounds clear the predeclared 50% threshold, so the verdict does not depend on how those rows are resolved.

## How early the earlier filing was

Among the 1,284 qualified events with a prior candidate, the earliest one led the 10-Q decision session by:

| Lead | Events | Share of prior events |
|---|---:|---:|
| 1 session | 519 | 40.4% |
| 2–4 sessions | 285 | 22.2% |
| 5–9 sessions | 318 | 24.8% |
| 10 or more | 162 | 12.6% |

The median lead is 2 sessions (p75 7, p90 11, max 98). 480 qualified events (23.9% of 2,010) had the 8-K at least 5 sessions earlier, which is the completed study's full holding length.

The other large group is `single_same_session`: 686 qualified events (34.1%) whose 8-K reached the same decision session as the 10-Q. Their median acceptance gap is 0.49 hours, and in 117 of them the 8-K was accepted after the 10-Q. For these rows, the completed study's decision was not later than the release.

## Trend by filing year (all registered originals)

| Year | 10-Qs | Prior share (lower–upper) | Same session | Lead ≥ 5 sessions | Median lead |
|---|---:|---|---:|---:|---:|
| 2012 | 263 | 71.5–72.6% | 57 | 121 | 6 |
| 2013 | 269 | 69.9–71.4% | 66 | 118 | 6 |
| 2014 | 279 | 72.0–74.6% | 64 | 115 | 5 |
| 2015 | 289 | 69.9–72.3% | 70 | 107 | 5 |
| 2016 | 290 | 66.9–67.6% | 79 | 92 | 3 |
| 2017 | 292 | 67.5–69.5% | 82 | 82 | 3 |
| 2018 | 297 | 64.0–67.7% | 84 | 83 | 3 |
| 2019 | 293 | 63.8–64.5% | 100 | 77 | 2 |
| 2020 | 296 | 61.5–61.8% | 105 | 78 | 3 |
| 2021 | 296 | 58.8–58.8% | 118 | 59 | 2 |
| 2022 | 297 | 57.9–58.2% | 115 | 64 | 2 |
| 2023 | 297 | 54.5–55.2% | 128 | 55 | 2 |
| 2024 | 299 | 56.2–56.2% | 127 | 50 | 2 |
| 2025 | 300 | 54.3–54.3% | 130 | 44 | 2 |

Over these years, issuers moved toward filing the 10-Q in the same session as the earnings release. Every year still clears 50%, but in the 2021–2025 window that the completed economic comparison traded, long leads became rarer: 44–64 a year at ≥5 sessions, against 107–121 a year in 2012–2015.

## Issuers and metadata quality

- All 100 issuers were reconstructed from raw bytes with no conflicting or duplicate accessions. Every issuer has at least one Item 2.02 8-K.
- There are 26,712 raw 8-K occurrences, the same count as the earlier schema inspection. 8,052 of them are unique Item 2.02 8-Ks, and 475 have an empty primary document.
- 31 in-window 8-K/A rows with Item 2.02 were reported and, as declared, never used as candidates. No in-window 8-K lacked items metadata.
- 89 issuers have qualified events. 55 of them have a prior candidate for at least half of those events, and 14 have none. The median issuer share is 78.6%, so the result is not one or two issuers.
- 8 10-Qs (3 qualified) were filed after their window ended and are flagged `late_10q_beyond_window`.

## What this does and does not establish

As declared, `supported_at_metadata_level` means earlier Item 2.02 releases are common enough to justify a separately declared, bounded original-document probe. It does not show that net income, year-to-date operating cash flow or total assets were public early. An Item 2.02 release often reports a different measure (for example adjusted earnings), and the submissions acceptance time is not proof of first dissemination. Nothing here backdates any 10-Q fact, changes the completed earnings comparison, or implies an edge.

The declared next stage has not started. Before any request, it needs its own declaration:

- a seeded random sample of strategy-qualified `single_prior` candidates
- for each, only the original accession index and press-release exhibit, fetched under the existing SEC bounds (1 request/second, no retries of completed failures, a global stop on 403/429)
- a record of whether the release itself states the current-period components

Only components shown to be public may ever be used at the earlier clock, and only in a new predeclared economic comparison.

## Known limitation carried forward

A missing, truncated or key-less `freeze.json` makes `audit.py` and `--preflight` raise (`FileNotFoundError`, `JSONDecodeError` or `KeyError`) instead of returning a structured declaration blocker. It fails closed: no attempt is created. `audit.py` is left byte-identical to the code this attempt recorded (SHA256 `c4ccaa30…57b4`), so the fix belongs in any future amendment rather than a post-run edit.
