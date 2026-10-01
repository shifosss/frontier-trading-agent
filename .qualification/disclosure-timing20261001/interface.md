# Source-only 8-K Item 2.02 timing audit

Declared October 1, 2026 and frozen before any 8-K submissions row was read. `definition.json` holds the question, denominators, matching window, clock, ambiguity rules and interpretation thresholds. `freeze.json` binds its SHA256 (`891da3a2466f3dd10f725987a4fbd2f6ce0893b562cdaf9c433a4bb610a31c5d`), the three code files it relies on and the amendment records. Changing either needs a new dated amendment and freeze. Existing attempts are never rewritten. Three amendments were made after review and before any run. `amendment-01.json` ends the window on day 83 and requires the source lock. `amendment-02.json` recomputes every 10-Q clock from its frozen manifest, so the consistency check also covers events whose issuer sources are unavailable. `amendment-03.json` makes six changes:

- It hash-checks the reused modules before executing them.
- It binds Python 3.13, `pyproject.toml` and `uv.lock`, and records the runtime with each attempt.
- It excludes conflicting accessions from the per-issuer counts.
- It lets an absent per-issuer file make only that issuer unavailable.
- It flags late 10-Qs for every issuer.
- It re-verifies the amendment records on every run.

## What it does

For each of the 4,057 frozen original 10-Qs it lists same-CIK original `8-K` rows whose `items` contain the exact token `2.02` and whose filing date falls in (10-Q `reportDate`, `reportDate` + 83 days]. The shortest possible next quarter ends on day 84, so its results release cannot fall in the window. Each candidate gets a decision session from the completed study's unchanged `event_clock` and is classed as `prior`, `same_session` or `after` relative to the 10-Q's own decision session. Each 10-Q then gets exactly one status, in this order: `issuer_unavailable`, `q_metadata_unavailable`, `q_session_unavailable`, `window_coverage_incomplete`, `ambiguous_metadata`, `no_candidate`, `single_prior`, `single_same_session`, `single_after`, `multiple`.

Provenance is rebuilt from the retained raw submissions bytes. Reused sources resolve repository-relative and must match the frozen request reuse catalog. Captured sources resolve under `source/`. The re-parsed concatenation must equal each saved `discovery.json` row list. Changed bytes in any bound or recorded file stop the attempt. A missing per-issuer file (a `discovery.json`, a root or a history page) makes only that issuer unavailable, and its 10-Qs stay in every denominator. Global inputs, code and the 4,057 manifests must all be present and unchanged. The input state must be identical at the start and end of the run.

It never makes a network request. It never reads prices, returns, S/Q values, models or 8-K documents. An earlier Item 2.02 filing is a timing candidate, not evidence of what was disclosed. Later 10-Q facts are never backdated.

## Outputs

`attempts/<uuid>/` holds `attempt.json`, `issuers.json` (source identities, coverage, occurrence/duplicate/conflict counts), `events.json` (every 10-Q with all candidates, amendments, unknown-items and conflict accessions), `events.csv` and `summary.json`. The summary reports per-stratum status counts, the lower and upper prior-candidate shares, lead-session quantiles and the predeclared verdict. A failure keeps `failure.json`.

The primary stratum is the 2,010 strategy-source-qualified events. The verdict is `supported_at_metadata_level` if the lower share is at least 0.5. It is `not_supported_at_metadata_level` if the upper share is below 0.2, and `inconclusive` otherwise. No verdict changes the completed earnings comparison or promotes a strategy.

## Inputs to restore before the real run

The clone already contains `source/request.json`, `source/completion.json`, all 4,057 `source/filings/*/*.json` manifests and 31 of the 100 `source/issuers/<SYM>/discovery.json` files. Restore these from the retained workspace at the same repository-relative paths, about 110 MB plus the history pages:

1. The other 69 `.qualification/earnings-quality20260928/source/issuers/<SYM>/discovery.json` files.
2. The 100 reused root submissions sources under `.qualification/earnings-quality20260928/discovery/profiles/raw/`, named in `definition.json` `inputs`.
3. `.qualification/post-filing-strategy20260928/calendar.json`.
4. `.qualification/earnings-quality20260928/qualification/attempts/b1258d8e28124eea8ffdd227f6ac71cf/events.json`.
5. `.qualification/earnings-quality20260928/source/capture.lock.sqlite`, the capture's empty SQLite lock file.
6. The 79 history pages under `.qualification/earnings-quality20260928/source/raw/`. Each `discovery.json` names its pages, so run the preflight after step 1 to list them.

The full 31.8 GB corpus is not needed.

## Commands

```
.venv/bin/python -B .qualification/disclosure-timing20261001/audit.py --preflight   # lists missing/changed inputs, writes nothing
.venv/bin/python -B .qualification/disclosure-timing20261001/audit.py               # one new attempt; refuses changed definition/inputs
.venv/bin/python -B -m pytest .qualification/disclosure-timing20261001/test_audit.py -q -p no:cacheprovider
```

On Windows use `.venv/Scripts/python.exe`. Check for a live source worker before running, as for every SEC-corpus reader. The audit requires `source/capture.lock.sqlite` and holds a read transaction on it, plus its own exclusive `audit.lock.sqlite`. If the lock file is missing or a writer holds it, the run is refused before any attempt is created.
