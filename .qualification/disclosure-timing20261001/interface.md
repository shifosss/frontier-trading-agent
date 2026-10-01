# Source-only 8-K Item 2.02 timing audit

Declared October 1, 2026 and frozen before any candidate matching, timing or outcome was computed. An earlier schema-only inspection, recorded in the handbook, counted 26,712 raw 8-K occurrences; `definition.json` discloses it. `definition.json` holds the question, denominators, matching window, clock, ambiguity rules and interpretation thresholds. `freeze.json` binds its SHA256 (`e48d158b119094f0b320a3d0f875eb27475febc93688bb29b3ba397c9c151ca2`), the three code files it relies on and the amendment records. Changing either needs a new dated amendment and freeze. Existing attempts are never rewritten. Twelve amendments were made after review and before any run. `amendment-01.json` ends the window on day 83 and requires the source lock. `amendment-02.json` recomputes every 10-Q clock from its frozen manifest, so the consistency check also covers events whose issuer sources are unavailable. `amendment-03.json` makes six changes:

- It hash-checks the reused modules before executing them.
- It binds Python 3.13, `pyproject.toml` and `uv.lock`, and records the runtime with each attempt.
- It excludes conflicting accessions from the per-issuer counts.
- It lets an absent per-issuer file make only that issuer unavailable.
- It flags late 10-Qs for every issuer.
- It re-verifies the amendment records on every run.

`amendment-04.json` makes three changes:

- It executes only the four needed definitions from the verified `capture.py`, so that module's top-level import of the project package never runs.
- It makes the preflight run the same declaration checks as a real run.
- It writes the variants and provenance of conflicting accessions to the outputs.

`amendment-05.json` changes three things in the preflight:

- Absent per-issuer files are reported separately instead of blocking.
- Held locks are probed read-only and reported as blocking.
- Inputs whose bytes changed are reported, not parsed.

`amendment-06.json` makes three changes:

- It also ends the window before the issuer's next frozen 10-Q period end.
- It loads the reused modules only for a real run.
- It writes every record atomically.

`amendment-07.json` takes the locks before any source input is hashed or read. It also reports an invalid, non-SQLite lock file instead of crashing.

`amendment-08.json` makes three changes:

- The final check also rechecks the 4,057 manifests.
- Time zones resolve only from the `uv.lock`-pinned `tzdata` 2026.4 package, never from system files. Each attempt records the America/New_York TZif SHA256.
- A non-file lock path is treated as invalid.

`amendment-09.json` makes two changes:

- It records every resolved raw source (root and history page) and re-hashes them before completing.
- The preflight inspects sources under the capture read lock and reports whether its inspection was guarded.

`amendment-10.json` makes five changes:

- It also ends the window at the issuer's next original 10-K or 10-KT period end.
- It runs the last identity check after the result files are written.
- It keeps raw-source identities on failed attempts.
- It stops the preflight at declaration drift.
- It corrects the earlier "no 8-K row read" claim.

`amendment-11.json` makes four changes:

- It also requires and guards the shared `sec-source.lock.sqlite`.
- It allows one attempt per frozen definition and requires unfinished attempts to be reconciled first.
- It parses only accession, status and session from the qualification events, never S, Q or u.
- It stops the declaration check at the first mismatch with the frozen SHA.

`amendment-12.json` makes two changes:

- It decodes only the accession, status and session values of the qualification events. Every other value, including S, Q and u, is skipped by scanning its bytes and never decoded.
- A missing source lock stops the preflight before it reads any source input, as a held or invalid one does. A starting worker creates an absent lock file, so absence guards nothing.

## What it does

For each of the 4,057 frozen original 10-Qs it lists same-CIK original `8-K` rows whose `items` contain the exact token `2.02` and whose filing date falls after the 10-Q `reportDate`. The window closes at day 83 or the day before the issuer's next period end, whichever comes first. The next period end is the next frozen 10-Q, or an original 10-K/10-KT/10-QT in the issuer's submissions. A later period's results cannot be filed before that period ends, so they cannot fall in the window. Three issuers have consecutive 10-Q period ends only 52–81 days apart, and ROP has a 10-K period end 61 days after a 10-Q. Each candidate gets a decision session from the completed study's unchanged `event_clock` and is classed as `prior`, `same_session` or `after` relative to the 10-Q's own decision session. Each 10-Q then gets exactly one status, in this order: `issuer_unavailable`, `q_metadata_unavailable`, `q_session_unavailable`, `window_coverage_incomplete`, `ambiguous_metadata`, `no_candidate`, `single_prior`, `single_same_session`, `single_after`, `multiple`.

Provenance is rebuilt from the retained raw submissions bytes. Reused sources resolve repository-relative and must match the frozen request reuse catalog. Captured sources resolve under `source/`. The re-parsed concatenation must equal each saved `discovery.json` row list. Changed bytes in any bound or recorded file stop the attempt. A missing per-issuer file (a `discovery.json`, a root or a history page) makes only that issuer unavailable, and its 10-Qs stay in every denominator. Global inputs, code and the 4,057 manifests must all be present and unchanged. The input state must be identical at the start and end of the run.

It never makes a network request. It never reads prices, returns, S/Q values, models or 8-K documents. An earlier Item 2.02 filing is a timing candidate, not evidence of what was disclosed. Later 10-Q facts are never backdated.

## Outputs

`attempts/<uuid>/` holds `attempt.json`, `issuers.json` (source identities, coverage, occurrence/duplicate/conflict counts), `events.json` (every 10-Q with all candidates, amendments, unknown-items and conflict accessions), `events.csv` and `summary.json`. The summary reports per-stratum status counts, the lower and upper prior-candidate shares, lead-session quantiles and the predeclared verdict. A failure keeps `failure.json`.

The primary stratum is the 2,010 strategy-source-qualified events. The verdict is `supported_at_metadata_level` if the lower share is at least 0.5. It is `not_supported_at_metadata_level` if the upper share is below 0.2, and `inconclusive` otherwise. No verdict changes the completed earnings comparison or promotes a strategy.

## Inputs to restore before the real run

The clone already contains `source/request.json`, `source/completion.json`, all 4,057 `source/filings/*/*.json` manifests and 31 of the 100 `source/issuers/<SYM>/discovery.json` files. Restore these from the retained workspace at the same repository-relative paths, about 110 MB plus the history pages:

1. `.qualification/earnings-quality20260928/source/capture.lock.sqlite` and `.qualification/earnings-quality20260928/sec-source.lock.sqlite`, the two empty SQLite source lock files. Until both exist, the preflight reports only the lock problems and reads no source input.
2. The other 69 `.qualification/earnings-quality20260928/source/issuers/<SYM>/discovery.json` files.
3. The 100 reused root submissions sources under `.qualification/earnings-quality20260928/discovery/profiles/raw/`, named in `definition.json` `inputs`.
4. `.qualification/post-filing-strategy20260928/calendar.json`.
5. `.qualification/earnings-quality20260928/qualification/attempts/b1258d8e28124eea8ffdd227f6ac71cf/events.json`.
6. The 79 history pages under `.qualification/earnings-quality20260928/source/raw/`. Each `discovery.json` names its pages, so run the preflight after steps 1 and 2 to list them.

The full 31.8 GB corpus is not needed. The preflight reports `ready` once nothing is `blocking`. In this clone, both lock files are missing, so the preflight stops there. With them restored, it also reports the calendar and the qualification events as blocking. Absent per-issuer files are listed under `issuer_unavailable`; a run keeps those issuers as unavailable rows that widen the bounds. As of this clone every issuer lacks at least one source, so restore the per-issuer files too, or every row is unavailable and the verdict can only be `inconclusive`.

## Commands

```
.venv/bin/python -B .qualification/disclosure-timing20261001/audit.py --preflight   # ready / blocking / issuer_unavailable; writes nothing
.venv/bin/python -B .qualification/disclosure-timing20261001/audit.py               # one new attempt; refuses changed definition/inputs
.venv/bin/python -B -m pytest .qualification/disclosure-timing20261001/test_audit.py -q -p no:cacheprovider
```

On Windows use `.venv/Scripts/python.exe`. Check for a live source worker before running, as for every SEC-corpus reader. The audit requires both source writer locks, `source/capture.lock.sqlite` and the shared `sec-source.lock.sqlite`. Before reading any source input, it takes a read transaction on each of them and its own exclusive `audit.lock.sqlite`, and holds all three through the final identity check. A missing, held or invalid lock refuses the run before any attempt is created and stops the preflight before it reads any source input. Each frozen definition runs once; a rerun needs a new declared amendment.
