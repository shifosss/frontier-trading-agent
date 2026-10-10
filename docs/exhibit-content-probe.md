# Earnings release content: exhibit probe

**October 9, 2026: frozen October 2 and amended once (amendment-01), not yet successfully run. The first attempt, `aa8f9104…`, halted on SEC's 403 for an undeclared automated tool after one request that returned no index, header or exhibit content; its 10-Q comparison inputs had already been projected.** One amended run follows, from the owner's macOS main checkout; the run steps are at the end.

## Why this is next

Two independently declared metadata audits agree that an Item 2.02 8-K usually precedes the original 10-Q. The [decision-session audit](disclosure-timing-results.md) finds this for 63.9–64.4% of the 2,010 strategy-qualified events; the [novelty audit](disclosure-novelty-results.md) finds an earlier ET acceptance date for 2,484 of 4,057 originals. Neither shows what the earlier release contained. The completed earnings study's signals use specific 10-Q values:

- **S:** current-quarter and prior-year same-quarter net income, and prior fiscal-year-end total assets.
- **Q:** current and prior-year year-to-date operating cash flow and net income, plus the same assets.

An earlier-clock version of either signal is only defensible for the components the press release itself states, for the same periods. This probe measures how often that holds, on a small seeded sample, before anyone extracts releases at scale.

## Design

The machine-readable declaration is [`definition.json`](../.qualification/exhibit-content20261002/definition.json). [`freeze.json`](../.qualification/exhibit-content20261002/freeze.json) binds it by SHA256 (`00cae883…08dc`) together with the code that implements it: [`probe.py`](../.qualification/exhibit-content20261002/probe.py), its synthetic tests [`test_probe.py`](../.qualification/exhibit-content20261002/test_probe.py), and the reused frozen `audit.py`, `capture.py` and `features.py`. Any change needs a dated amendment and a new freeze. [`amendment-01.json`](../.qualification/exhibit-content20261002/amendment-01.json) changed only the request's user agent, plus the rule that sets an earlier attempt aside and the text that rule made false; the original declaration was `f9e6e2b5…0b8f`.

- **Frame:** the 1,166 strategy-qualified `single_prior` events from the decision-session audit, across 70 issuers (579 filed 2012–2020, 587 filed 2021–2025). Ambiguous `multiple` events and same-session events are excluded.
- **Sample:** 150 events, ordered by the SHA256 of `exhibit-content20261002|` plus the 10-Q accession. No replacement: a failed fetch or missing exhibit stays in the denominator. An offline dry check of the draw (filing metadata only) gives 56 issuers, 70 events filed 2012–2020 and 80 filed 2021–2025, and 50 agent-filed 8-Ks.
- **Requests:** for each sampled 8-K, its accession index, its SGML header and every EX-99 document in index order (more than 10 is recorded as overflow and none is fetched). The archive directory is keyed by the issuer CIK, as in the frozen capture; the accession prefix is never used. The frozen capture's `Cache` runs from its verified bytes with the declared user agent (`Alex Zhang alexandar.zhang@mail.utoronto.ca`): 1 request per second, no redirects, a global stop on 403 or 429, only `www.sec.gov/Archives/edgar/data/` URLs, at most 2 attempts per URL and 1,800 in total.
- **Lifecycle:** an exclusive study lock plus an exclusive transaction on the shared SEC source lock, a check that no other Python process is running anything under `.qualification` or any study script by name (older SEC capture workers hold only their own lock), one attempt per frozen definition (an earlier attempt stops blocking a new run only if the definition names it in `reconciled_attempts` and a declared amendment supersedes the definition it ran under; checked under the lock, and created only together with its record), and an append-only, fsynced request journal whose complete lines `attempt.json` binds before each request is sent and after each outcome. A URL with a saved outcome is never requested again; an interrupted one may be retried once. A 403/429, an oversize response or a new transport failure (an incomplete read included) writes `STOP.json` and halts, and a saved one whose stop a crash prevented halts again on resume; resuming then needs `--acknowledge-stop`.
- **Identity:** the header must show the issuer's CIK inside a `<FILER>` block (an unclosed block ends at the next party section such as `<SUBJECT-COMPANY>`), form 8-K and, when items are listed, Item 2.02. Its acceptance time, re-clocked with the frozen `event_clock`, must still fall in an earlier decision session than the 10-Q's. An observed mismatch or a later session stays in the sample as not stated. A header missing one of those fields leaves identity unverified: the release is still examined, but the event cannot count in the lower bound. The clock is bound to the same verified `features.py` bytes, XNYS calendar and pinned `tzdata` 2026.4 as the decision-session audit, and each sampled 10-Q's session must reproduce that audit's value before any request.
- **Which document:** the press release is the EX-99 document whose index description says press, news or earnings release, or whose opening text calls itself one (a reference such as "see our earnings release" does not count); with none, the single EX-99.1 (flagged). Several candidates are matched jointly and flagged ambiguous. PDFs and other binaries are unavailable. A component that is not stated in a document with an image of its statement (named by alt text, file name or the preceding heading) is also unavailable, even if its label appears elsewhere; a logo or chart does not count. When several candidates are matched jointly, one that may still hold the value (unreadable or image-only) keeps the component possible. Availability in any EX-99 document is a separate, non-verdict readout.
- **Comparison values:** before any request, the S and Q input values, their period endpoints and the prior fiscal-year end of the 150 sampled 10-Qs are projected from the completed qualification `records.json` into `projection.json`. Every other field is skipped without being decoded. No price, return, forecast or account is read.
- **Matching:** a component is stated only when a table cell or narrative sentence labelled for it (net income, total assets, operating cash flow) equals the 10-Q value after units, a `$`/`USD` mark and display rounding, **and** its column header or sentence parses to the required period:
  - Adjusted, non-GAAP, normalized, underlying, pre-tax, available-to-common, pro forma, per-share, noncontrolling and continuing/discontinued-operations labels never count. Operating cash flow also matches "cash flow from operations", but free cash flow ("Free cash flow from operations") never counts. An equal amount in another currency (a symbol, a code just before or after an amount (also "(CAD)", "in Canadian dollars" or "Canadian $"), a code in its own cell, a column header, a row label, a caption unit phrase such as "in millions of Canadian dollars", or a declaration such as "All amounts in Canadian dollars", which anywhere in the release, table cells included, applies to every amount without an explicit US$ or USD) is `currency_mismatch` and never counts as stated.
  - Under a label naming only a loss ("net loss") or a use of cash ("cash used in"), an unsigned amount is negative.
  - HTML `colspan` and `rowspan` are expanded and header rows are found structurally, so split rows such as "Three Months Ended June 30," over "2025 | 2024" stay in the header, and a stacked "Six Months Ended" section takes its own header, even when its period cell has no span. A value takes only its own column's header (plus table-wide captions), never a neighbour's. Plain-text tables align headers by character position, and a lone period line such as "Six Months Ended June 30, 2025" starts a new table. A non-GAAP section heading row inside a table, such as "Non-GAAP Measures", excludes the rows below it. A table left open at the end of an HTML document is still read.
  - Quarterly net income must sit under a three-month column ending at the 10-Q period end, year-to-date values under the matching year-to-date column, and assets under the prior fiscal-year-end date. A bare "year to date" header takes the 10-Q's year-to-date length.
  - The scale comes from the nearest unit phrase (cell, column header, table header, caption, then preceding text). Without one, a value equal only at an inferred scale is `scale_unverified` (upper bound only).
  - An equal value is dropped only when its parsed end date or duration contradicts the requirement. Any other equal value whose period is not verified (no date, an ambiguous duration) is `period_unverified`.
  - Superscript footnote markers, and a numbered marker such as "(1)" alone in a cell, are dropped. A header or clause such as "June 30, 2025 and 2024", "June and September 2025", "Three/Six Months", "Q2 and Q3 FY2025", "Q2/Q3 FY2025" or "second quarter of fiscal 2025 and fiscal 2024" names several periods and verifies none, and a header naming only another fiscal quarter ("Q3 FY2025") is a different period. Forecast wording, including a modal such as "will total", "projects" or "is targeted at", excludes an amount, as does an item within the measure ("included a $5.2 million tax benefit", "resulted primarily from"), a tax label such as "Net income taxes paid", a change phrase before or after the label ("The increase in net income", "Net income change"), a change or comparison base ("increased $5.2 million", "from $5.2 million", a "Growth" column), probable wording ("is likely to reach"), prose under an "Outlook" or non-GAAP heading (a one-cell layout table included, read in source order) or a new subject after a colon, "because", "since" or "as". A short title such as "Core Financial Results" still applies across unit or audit lines such as "(Unaudited)" and "(in millions)". A bound or range endpoint ("less than $5.2 million", "between $4.8 million and $5.2 million") and a "Note" reference column are not values, and an exact rounding midpoint (a displayed 5 for 5.5) is not equal. Month-year headers ("June 2025") mean the month end. Prose laid out in table cells is read as prose. In prose, amounts may be written `$5.2 million`, `USD 5.2 million`, `5.2 million USD` or `-$3.0 million`, and each amount pairs only with the nearest label before it (with no other measure such as EBITDA or operating cash flow named in between) and the period phrase of its own clause (split at "compared with", "versus", semicolons and similar). A clause naming an excluded measure such as adjusted net income does not count, and a clause with several amounts and several periods (including "June 30, 2025 and 2024 … respectively"), or naming both a quarter and a year-to-date period, is `period_unverified`.
  - Every match keeps its document URL and SHA256, table and row (or clause), label, cell, header, parsed period and scale.
- **Readout:** per component and per signal (shares and Wilson intervals for both), with lower and upper bounds (the upper bound also counts `period_unverified` and unavailable components; the lower bound also excludes ambiguous releases and unverified identity), Wilson 95% intervals and both filing eras. The signal verdicts use the flow components (net income and operating cash flow). Prior fiscal-year-end assets were normally public earlier through the annual report, so they are reported separately; a later full extraction must take them from that report at its own verified clock.
- **Verdict per signal:** `release_complete_common` if the Wilson lower limit of the lower-bound share is at least 0.7; `release_complete_rare` if the Wilson upper limit of the upper-bound share is below 0.3; otherwise `inconclusive`. `common` justifies only a separately declared full extraction of that signal's components. Nothing here backdates a 10-Q value, changes a completed result or promotes a strategy.
- **Verification:** 114 offline synthetic tests cover every matching rule and the fetch lifecycle with a fake opener (`verification.json`). After the run, `--reanalyze` recomputes every classification from the saved bytes and must reproduce `events.json`, `summary.json` and `spot-check.json` exactly, each still with the SHA256 recorded in `attempt.json`, and `spot-check.json` lists the 20 events with the smallest SHA256 of `exhibit-content20261002|spot|` plus the 10-Q accession, with their evidence, for an owner reading of the original documents.

## Owner decisions (October 2)

The owner accepted the draft defaults: the decision-session frame, 150 events, thresholds 0.7 and 0.3, and the frozen capture's user agent (it carries no contact address). The probe runs on the owner's workstation, which holds `records.json` and performs the projection there.

## Owner decisions (October 9)

After attempt `aa8f9104d57c4d94aada8705284d211b` halted on SEC's 403 for an undeclared automated tool, the owner chose amendment-01, which changes only the user agent to the declared `Alex Zhang alexandar.zhang@mail.utoronto.ca`. Earlier attempts stop blocking only when named and superseded; the SEC access check below is part of the procedure; amendment-01 is revised in place while no attempt exists under it; aa8f's six non-raw files are committed with the amendment; and the amended run happens once, from the owner's macOS main checkout, launched by the owner in Terminal.app. Before the amendment, `probe.py` had written `projection.json` (the sampled 10-Qs' comparison inputs) ahead of its single request; no exhibit, index or header content was read, and the Claude and Codex session transcripts of 2026-10-07..09 show no tool call that displayed its values.

## Running it from the macOS main checkout

Run from the repository root of the owner's macOS main checkout in Terminal.app, on `main` after amendment-01 is merged, and from no other checkout (not a worktree, a clone or the Windows workstation). Expect about 450–600 requests, roughly 8–10 minutes.

1. `git switch main && git pull --ff-only && uv sync --frozen`, then `git status --porcelain` must print nothing. The study files are stored byte-exact (`.gitattributes` marks `.qualification/**` as `-text`).
2. These retained files must be present with their declared SHA256 (preflight checks them):
   - `.qualification/earnings-quality20260928/qualification/attempts/b1258d8e28124eea8ffdd227f6ac71cf/records.json` (208,387,935 bytes, `0aa2fcd4…df28db`)
   - `.qualification/post-filing-strategy20260928/calendar.json` (`a1ead37f…2560`)
   - `.qualification/earnings-quality20260928/sec-source.lock.sqlite`, the shared SEC source lock (an empty file in the original workspace)
3. Check that the halted attempt is intact; all 7 lines must say `OK`:

   ```bash
   A=.qualification/exhibit-content20261002
   .venv/bin/python -c 'import json, sys; [print(h + "  " + p) for p, h in json.load(open(sys.argv[1]))["superseded_attempt"]["files"].items()]' $A/amendment-01.json |
     (cd $A/attempts/aa8f9104d57c4d94aada8705284d211b && shasum -a 256 -c)
   ```

4. Close any other research script under `.qualification` and any agent test run (the probe refuses to start while one runs). Check, without any request or write:

   ```bash
   .venv/bin/python -B .qualification/exhibit-content20261002/probe.py --preflight
   ```

   It must print `"ready": true`, `"sample_size": 150` and `"resumable_attempts": []`.
5. Access check. This GET is outside the probe and its journals; only the status is kept, and nothing from the sample is requested. It must print `200 https://www.sec.gov/Archives/edgar/full-index/`:

   ```bash
   UA=$(.venv/bin/python -c 'import json; print(json.load(open(".qualification/exhibit-content20261002/definition.json"))["requests"]["user_agent"])')
   .venv/bin/python -I -c 'import sys, urllib.request as r; q = r.Request("https://www.sec.gov/Archives/edgar/full-index/", headers={"User-Agent": sys.argv[1], "Accept-Encoding": "identity"}); s = r.urlopen(q, timeout=30); print(s.status, s.url)' "$UA"
   ```

   On a 403, wait at least an hour and retry once; a second 403 means stop and re-plan.
6. Run once, with the Mac on mains power, the lid open and a stable network. It prints the attempt directory when it completes:

   ```bash
   caffeinate -is -w $$ &
   .venv/bin/python -B .qualification/exhibit-content20261002/probe.py --run
   ```

   Do not wrap the probe in `caffeinate`: its helper process matches the probe's worker check and the run is refused. `-w $$` keeps the Mac awake for as long as this shell lives. Start it the same way before `--resume`.

7. If it stops:
   - Interrupted (Ctrl+C, sleep, power): `--resume <id>`.
   - `Halted`: read `attempts/<id>/source/STOP.json` first, with `cat` in Terminal. Never open `attempts/` in Finder: a `.DS_Store` written under `source/` makes `--reanalyze` report not reproduced. After a transport failure, check the network, then `--resume <id> --acknowledge-stop` (that URL's event becomes unavailable). After a 403/429, wait at least an hour and repeat step 5; acknowledge only when it returns 200 and this is the attempt's first acknowledged 403/429, otherwise stop and re-plan.
   - `failed`: do not resume or rerun. Report the error; a fix needs an amendment.
   - Never resume or acknowledge `aa8f9104…`.
8. Confirm the saved bytes reproduce the outputs; `reproduced` must be `true` (the command exits with status 1 otherwise):

   ```bash
   .venv/bin/python -B .qualification/exhibit-content20261002/probe.py --reanalyze <id>
   ```

9. The new attempt's `sample.json` and `projection.json` must hash to the same values as aa8f's (`97e3f048…bb1f` and `234154d7…2aa0`):

   ```bash
   shasum -a 256 .qualification/exhibit-content20261002/attempts/<id>/{sample,projection}.json
   ```

10. Commit the attempt without the raw SEC bytes, which stay as local evidence (`attempt.json` still records each raw payload's SHA256). The source files added are exactly those listed in `attempt.json` under `source`, except raw payloads under `raw/` and quarantined partial payloads (`partial/*.bin.*`); the request journal, resource records, acknowledged stops and any quarantined journal tail are added:

    ```bash
    a=.qualification/exhibit-content20261002/attempts/<id>
    git add -f "$a/attempt.json" "$a/sample.json" "$a/projection.json" "$a/events.json" "$a/summary.json" "$a/spot-check.json"
    .venv/bin/python -c 'import json, sys; from fnmatch import fnmatch; [print(n) for n in json.load(open(sys.argv[1]))["source"] if not (fnmatch(n, "raw/*") or fnmatch(n, "partial/*.bin.*"))]' "$a/attempt.json" |
      while IFS= read -r name; do git add -f "$a/source/$name"; done
    ```

    Never commit `probe.lock.sqlite` or the shared lock. The results are then written up in `docs/exhibit-content-results.md`.
