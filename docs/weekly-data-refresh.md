# Bounded weekly market-data refresh

The September 25 weekly cutoff is captured and verified in isolated run `6af796bf858547b2839e09edac1d1fdf`. Acquisition began September 26, stopped at the owner's pause, and completed after the goal resumed on September 28. It covers **September 14-25, 2026**, with ten possible daily sessions. No historical evaluation or model fitting ran as part of this refresh.

The frozen full-history studies, their main indexes and the main listing pointer remain unchanged. This recent window is evidence for a future, separately declared data update; it has insufficient warmup to replace the full study inputs or support a trading decision by itself.

## Coverage

The September 26 dated listing contains **8,437 eligible instruments**: 5,662 US stocks, 2,755 Canadian stocks and the 20 retained benchmark ETFs. Its 59 raw directory responses and membership identity passed hash verification. The US directories carry September 25 vintages; Canadian membership combines the August TMX file with dated exchange directories, rather than assuming every directory has a daily publication timestamp.

| Capture measure | USD | CAD | Total |
| --- | ---: | ---: | ---: |
| Requested instruments, including benchmark ETFs | 5,676 | 2,761 | 8,437 |
| Usable bounded histories | 5,673 | 2,714 | 8,387 |
| Normalized daily rows | 56,640 | 27,037 | 83,677 |
| All ten sessions present | 5,650 | 2,695 | 8,345 |
| Partial window | 23 | 19 | 42 |
| Last observation at September 25 cutoff | 5,672 | 2,709 | 8,381 |
| Stale at cutoff | 1 | 5 | 6 |
| Failed histories retained | 3 | 47 | 50 |

The six stale histories are ADG.V, ARO.V, ATTT, BVOF-B.CN, NASA.CN and VROY.V. Neither freshness nor ten available bars establishes liquidity or trading eligibility.

All **8,437 HTTP responses** are retained: 8,413 HTTP 200 and 24 HTTP 404 responses. There were **zero duplicate symbol requests**, including across the interruption. The 50 failures comprise 24 HTTP 404s, 12 invalid OHLCV histories, 10 missing `close` fields and four empty/duplicate-session normalization failures. None was silently retried, substituted or removed from the denominator.

Compared with the frozen study's dated membership, the new snapshot adds 19 symbols, removes 16 and changes 33 specifications. These are observed directory differences, not reconciled issuer changes or verified delistings.

## Recovery and verification

The saved checkpoint contained 3,625 completed histories and 25 failures after 3,650 attempted instruments. HWC and HVT-A had retained in-flight HTTP responses; both were recovered locally. The resumed process requested only the remaining 4,785 instruments under the **original frozen cutoff and original listing**. Previously completed records, their raw bodies and the prior failure records remain unchanged. Checkpoint copies and the resume request identify the original state and recovery script.

Every accepted raw history was hashed and normalized again. Checks covered the requested window, original cutoff, row count, final session, membership and complete success/failure partition. Directory hashes and all retained HTTP body hashes also passed. The following protected files remained byte-identical to their pre-refresh state:

- `data/historical/history-index.json`
- `artifacts/historical-lab/latest.json`
- `data/research/universe/latest.json`
- The capture indexes for runs `814780d48b4141b9a82a3fb917d1b85a` and `90af4c840aad48f7ab58fba7a682f96a`

Of the accepted histories, 3,627 were observed September 26 and 4,760 on September 28. The resumed requests retain their later source vintage while normalization still ends September 25. They are not observations that were all available at the original frozen time. No refreshed rows were spliced into an older frozen capture.

## Predeclared overlap audit

Before completion, 32 symbols per currency were selected by sorted symbol SHA256 among common dated members. No unavailable symbol was replaced. Comparing the five raw provider fields over September 14-18 produced:

- 61 compared symbols and three unavailable comparisons: ANDC.V, STG.TO and ADX.CN.
- 1,525 comparable cells, with **138 changes across 55 symbols**.
- Changes in 55 volume, 21 close, 19 high, 22 low and 21 adjusted-close cells.
- 112 changed cells on September 18 and 26 on September 17.
- Largest relative price-field change: GMV.V September 18 close/high/adjusted close, approximately 0.155 to 0.160, or **+3.23%**. Both upward and downward changes are retained.

The sample demonstrates source-vintage differences, including in recently closed sessions. It does not establish which vintage is correct, quantify universe-wide revision rates, or reconcile corporate actions. No corrections, model refits or strategy promotions followed this audit. Existing frozen results must continue to identify their original source bytes.

## Evidence and reproduction

Evidence lives under `.qualification/weekly-refresh20260926/`:

- `request.json` and the original `run_refresh.py`: original bounded request and acquisition.
- `resume_capture.py`, `resume-attempts/20260928T184030828312Z/`: saved checkpoint copies, full resume request, recovered responses and completion identity.
- `capture-workspace/artifacts/historical-lab/runs/6af796bf858547b2839e09edac1d1fdf/`: unchanged capture definition, complete capture index, all failures and completed status.
- `capture-workspace/data/research/universe/`: dated membership and 59 directory source bodies.
- `http-responses.jsonl`, `http-responses/`: per-response URL, status, observation time, body and hash, including rejected histories.
- `verification.json`, `coverage-summary.json`: all-history checks and independent request/coverage accounting.
- `membership-differences.json`: all additions, removals and changed specifications.
- `overlap-audit-definition.json`, `overlap-audit.json`: fixed sample, every comparison and all changed values.

Repeat the offline checks with the project Python through the RTK wrapper configured in `C:/Users/user/.codex/RTK.md`:

```powershell
rtk proxy .venv/Scripts/python.exe -B -X utf8 .qualification/weekly-refresh20260926/finalize_refresh.py
rtk proxy .venv/Scripts/python.exe -B -X utf8 .qualification/weekly-refresh20260926/audit_overlap.py
```

This is a completed capture and provenance audit. It is not a point-in-time membership database, complete corporate-action ledger, qualified performance study or promoted paper-trading policy.
