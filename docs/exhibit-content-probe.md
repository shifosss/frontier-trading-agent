# Earnings release content: exhibit probe

**October 2, 2026: frozen on owner approval, not yet run. No SEC request, exhibit read or 10-Q value projection has been made.** It runs once, on the owner's workstation; the run steps are at the end.

## Why this is next

Two independently declared metadata audits agree that an Item 2.02 8-K usually precedes the original 10-Q. The [decision-session audit](disclosure-timing-results.md) finds this for 63.9–64.4% of the 2,010 strategy-qualified events; the [novelty audit](disclosure-novelty-results.md) finds an earlier ET acceptance date for 2,484 of 4,057 originals. Neither shows what the earlier release contained. The completed earnings study's signals use specific 10-Q values:

- **S:** current-quarter and prior-year same-quarter net income, and prior fiscal-year-end total assets.
- **Q:** current and prior-year year-to-date operating cash flow and net income, plus the same assets.

An earlier-clock version of either signal is only defensible for the components the press release itself states, for the same periods. This probe measures how often that holds, on a small seeded sample, before anyone extracts releases at scale.

## Design

The machine-readable declaration is [`definition.json`](../.qualification/exhibit-content20261002/definition.json). [`freeze.json`](../.qualification/exhibit-content20261002/freeze.json) binds it by SHA256 (`69315a20…086a`) together with the code that implements it: [`probe.py`](../.qualification/exhibit-content20261002/probe.py), its synthetic tests [`test_probe.py`](../.qualification/exhibit-content20261002/test_probe.py), and the reused frozen `audit.py`, `capture.py` and `features.py`. Any change needs a dated amendment and a new freeze.

- **Frame:** the 1,166 strategy-qualified `single_prior` events from the decision-session audit, across 70 issuers (579 filed 2012–2020, 587 filed 2021–2025). Ambiguous `multiple` events and same-session events are excluded.
- **Sample:** 150 events, ordered by the SHA256 of `exhibit-content20261002|` plus the 10-Q accession. No replacement: a failed fetch or missing exhibit stays in the denominator. An offline dry check of the draw (filing metadata only) gives 56 issuers, 70 events filed 2012–2020 and 80 filed 2021–2025, and 50 agent-filed 8-Ks.
- **Requests:** for each sampled 8-K, its accession index, its SGML header and every EX-99 document in index order (more than 10 is recorded as overflow and none is fetched). The archive directory is keyed by the issuer CIK, as in the frozen capture; the accession prefix is never used. The frozen capture's `Cache` runs from its verified bytes with its user agent: 1 request per second, no redirects, a global stop on 403 or 429, only `www.sec.gov/Archives/edgar/data/` URLs, at most 2 attempts per URL and 1,800 in total.
- **Lifecycle:** an exclusive study lock plus an exclusive transaction on the shared SEC source lock, a check that no other Python process is running anything under `.qualification` (older SEC capture workers hold only their own lock), one attempt per frozen definition (checked under the lock, and created only together with its record), and an append-only, fsynced request journal. A URL with a saved outcome is never requested again; an interrupted one may be retried once. A 403/429, an oversize response or a new transport failure writes `STOP.json` and halts; resuming then needs `--acknowledge-stop`.
- **Identity:** the header must show the issuer's CIK, form 8-K and, when items are listed, Item 2.02. Its acceptance time, re-clocked with the frozen `event_clock`, must still fall in an earlier decision session than the 10-Q's. An observed mismatch or a later session stays in the sample as not stated. A header missing one of those fields leaves identity unverified: the release is still examined, but the event cannot count in the lower bound. The clock is bound to the same verified `features.py` bytes, XNYS calendar and pinned `tzdata` 2026.4 as the decision-session audit, and each sampled 10-Q's session must reproduce that audit's value before any request.
- **Which document:** the press release is the EX-99 document whose index description or opening text says press, news or earnings release; with none, the single EX-99.1 (flagged). Several candidates are matched jointly and flagged ambiguous. PDFs and other binaries are unavailable. A component that is not stated in a document with an image of its statement (named by alt text, file name or the preceding heading) is also unavailable, even if its label appears elsewhere; a logo or chart does not count. When several candidates are matched jointly, one that may still hold the value (unreadable or image-only) keeps the component possible. Availability in any EX-99 document is a separate, non-verdict readout.
- **Comparison values:** before any request, the S and Q input values, their period endpoints and the prior fiscal-year end of the 150 sampled 10-Qs are projected from the completed qualification `records.json` into `projection.json`. Every other field is skipped without being decoded. No price, return, forecast or account is read.
- **Matching:** a component is stated only when a table cell or narrative sentence labelled for it (net income, total assets, operating cash flow) equals the 10-Q value after units, a `$`/`USD` mark and display rounding, **and** its column header or sentence parses to the required period:
  - Adjusted, non-GAAP, pro forma, per-share, noncontrolling and continuing/discontinued-operations labels never count. Operating cash flow also matches "cash flow from operations". An equal amount in another currency (a symbol, a code in its own cell, a column header, or a caption unit phrase such as "in millions of Canadian dollars") is `currency_mismatch` and never counts as stated.
  - Under a label naming only a loss ("net loss") or a use of cash ("cash used in"), an unsigned amount is negative.
  - HTML `colspan` and `rowspan` are expanded and header rows are found structurally, so split rows such as "Three Months Ended June 30," over "2025 | 2024" stay in the header, and a stacked "Six Months Ended" section takes its own header. A value takes only its own column's header (plus table-wide captions), never a neighbour's. Plain-text tables align headers by character position.
  - Quarterly net income must sit under a three-month column ending at the 10-Q period end, year-to-date values under the matching year-to-date column, and assets under the prior fiscal-year-end date. A bare "year to date" header takes the 10-Q's year-to-date length.
  - The scale comes from the nearest unit phrase (cell, column header, table header, caption, then preceding text). Without one, a value equal only at an inferred scale is `scale_unverified` (upper bound only).
  - An equal value is dropped only when its parsed end date or duration contradicts the requirement. Any other equal value whose period is not verified (no date, an ambiguous duration) is `period_unverified`.
  - Superscript footnote markers are dropped. Month-year headers ("June 2025") mean the month end. Prose laid out in table cells is read as prose. In prose, amounts may be written `$5.2 million`, `USD 5.2 million`, `5.2 million USD` or `-$3.0 million`, and each amount pairs only with the nearest label before it (with no other measure such as EBITDA or operating cash flow named in between) and the period phrase of its own clause (split at "compared with", "versus", semicolons and similar). A clause naming an excluded measure such as adjusted net income does not count, and a clause with several amounts and several periods (including "June 30, 2025 and 2024 … respectively"), or naming both a quarter and a year-to-date period, is `period_unverified`.
  - Every match keeps its document URL and SHA256, table and row (or clause), label, cell, header, parsed period and scale.
- **Readout:** per component and per signal (shares and Wilson intervals for both), with lower and upper bounds (the upper bound also counts `period_unverified` and unavailable components; the lower bound also excludes ambiguous releases and unverified identity), Wilson 95% intervals and both filing eras. The signal verdicts use the flow components (net income and operating cash flow). Prior fiscal-year-end assets were normally public earlier through the annual report, so they are reported separately; a later full extraction must take them from that report at its own verified clock.
- **Verdict per signal:** `release_complete_common` if the Wilson lower limit of the lower-bound share is at least 0.7; `release_complete_rare` if the Wilson upper limit of the upper-bound share is below 0.3; otherwise `inconclusive`. `common` justifies only a separately declared full extraction of that signal's components. Nothing here backdates a 10-Q value, changes a completed result or promotes a strategy.
- **Verification:** 70 offline synthetic tests cover every matching rule and the fetch lifecycle with a fake opener (`verification.json`). After the run, `--reanalyze` recomputes every classification from the saved bytes and must reproduce `events.json` and `summary.json` exactly, and `spot-check.json` lists the 20 events with the smallest SHA256 of `exhibit-content20261002|spot|` plus the 10-Q accession, with their evidence, for an owner reading of the original documents.

## Owner decisions (October 2)

The owner accepted the draft defaults: the decision-session frame, 150 events, thresholds 0.7 and 0.3, and the frozen capture's user agent (it carries no contact address). The probe runs on the owner's workstation, which holds `records.json` and performs the projection there.

## Running it on the workstation

Run from the repository root in PowerShell, on `main` after this declaration is merged. Expect about 450–600 requests, roughly 8–10 minutes.

1. `git pull` then `uv sync --frozen`. The study files are stored byte-exact (`.gitattributes` marks `.qualification/**` as `-text`).
2. These retained files must be present with their declared SHA256 (preflight checks them):
   - `.qualification/earnings-quality20260928/qualification/attempts/b1258d8e28124eea8ffdd227f6ac71cf/records.json` (208,387,935 bytes, `0aa2fcd4…df28db`)
   - `.qualification/post-filing-strategy20260928/calendar.json` (`a1ead37f…2560`)
   - `.qualification/earnings-quality20260928/sec-source.lock.sqlite`, the shared SEC source lock (an empty file in the original workspace)
3. Close any other research script under `.qualification` (the probe refuses to start while one runs). Check, without any request or write:

   ```powershell
   .venv\Scripts\python.exe -B .qualification\exhibit-content20261002\probe.py --preflight
   ```

   It must print `"ready": true` and `"sample_size": 150`.
4. Run once. It prints the attempt directory when it completes:

   ```powershell
   .venv\Scripts\python.exe -B .qualification\exhibit-content20261002\probe.py --run
   ```

5. If it stops:
   - Interrupted (Ctrl+C, sleep, power): `--resume <id>`.
   - `Halted`: read `attempts\<id>\source\STOP.json` first. After a 403/429, wait at least an hour; after a transport failure, check the network. Then `--resume <id> --acknowledge-stop`.
   - `failed`: do not resume or rerun. Report the error; a fix needs an amendment.
6. Confirm the saved bytes reproduce the outputs; both values must be `true`:

   ```powershell
   .venv\Scripts\python.exe -B .qualification\exhibit-content20261002\probe.py --reanalyze <id>
   ```

7. Commit the attempt without the raw SEC bytes, which stay as local evidence:

   ```powershell
   git add -f .qualification/exhibit-content20261002/attempts/<id>/attempt.json `
     .qualification/exhibit-content20261002/attempts/<id>/sample.json `
     .qualification/exhibit-content20261002/attempts/<id>/projection.json `
     .qualification/exhibit-content20261002/attempts/<id>/events.json `
     .qualification/exhibit-content20261002/attempts/<id>/summary.json `
     .qualification/exhibit-content20261002/attempts/<id>/spot-check.json `
     .qualification/exhibit-content20261002/attempts/<id>/source/requests.jsonl `
     .qualification/exhibit-content20261002/attempts/<id>/source/resources
   ```

   Never commit `probe.lock.sqlite` or the shared lock. The results are then written up in `docs/exhibit-content-results.md`.
