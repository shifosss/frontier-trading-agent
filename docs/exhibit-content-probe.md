# Earnings release content: draft exhibit probe

**October 2, 2026: draft for owner review. Not frozen. No SEC request, sample draw, exhibit read or 10-Q value projection has been made.**

## Why this is next

Two independently declared metadata audits agree that an Item 2.02 8-K usually precedes the original 10-Q. The [decision-session audit](disclosure-timing-results.md) finds this for 63.9–64.4% of the 2,010 strategy-qualified events; the [novelty audit](disclosure-novelty-results.md) finds an earlier ET acceptance date for 2,484 of 4,057 originals. Neither shows what the earlier release contained. The completed earnings study's signals use specific 10-Q values:

- **S:** current-quarter and prior-year same-quarter net income, and prior fiscal-year-end total assets.
- **Q:** current and prior-year year-to-date operating cash flow and net income, plus the same assets.

An earlier-clock version of either signal is only defensible for the components the press release itself states, for the same periods. This probe measures how often that holds, on a small seeded sample, before anyone extracts releases at scale.

## Draft design

The machine-readable draft is [`definition.json`](../.qualification/exhibit-content20261002/definition.json).

- **Frame:** the 1,166 strategy-qualified `single_prior` events from the decision-session audit, across 70 issuers (579 filed 2012–2020, 587 filed 2021–2025). Ambiguous `multiple` events and same-session events are excluded.
- **Sample:** 150 events, ordered by the SHA256 of a fixed study string plus the 10-Q accession. No replacement: a failed fetch or missing exhibit stays in the denominator.
- **Requests:** for each sampled 8-K, its accession index, its SGML header and every EX-99 document in index order (more than 10 is recorded as overflow). The archive directory is keyed by the issuer CIK, as in the frozen capture; 402 of the 1,166 frame 8-Ks were filed by an agent, so the accession prefix is never used. The frozen capture's bounds apply: 1 request per second, no redirects, a global stop on 403 or 429, only `www.sec.gov/Archives/edgar/data/` URLs, and a hard cap of 1,800 requests.
- **Lifecycle:** an exclusive study lock plus an exclusive writer transaction on the shared SEC source lock, an owned-process check before any start or resume, one immutable attempt per frozen definition, and an append-only request journal. A completed URL is never requested again; an interrupted one may be retried once.
- **Identity:** the header must show the issuer's CIK and form 8-K. Its acceptance time, re-clocked with the frozen `event_clock`, must still fall in an earlier decision session than the 10-Q's. Failures stay in the sample and count as not stated.
- **Which document:** the press release is the EX-99 document whose index description or opening text says press, news or earnings release; with none, the single EX-99.1 (flagged). Several candidates are flagged ambiguous. PDFs, other binaries and image-only tables are recorded as unavailable, never as "not found". Availability in any EX-99 document is a separate, non-verdict readout.
- **Comparison values:** the S and Q input values, their period endpoints and the prior fiscal-year end of the sampled 10-Qs, projected from the completed qualification `records.json`. No other field is read, and no price, return, forecast or account.
- **Matching:** a component is stated only when a table row labelled for it (net income, total assets, operating cash flow) has a cell equal to the 10-Q value after units and display rounding **and** that cell's column header parses to the required period. Quarterly net income must sit under a three-month column ending at the 10-Q period end, year-to-date values under the matching year-to-date column, and assets under the prior fiscal-year-end date. An equal value with an unreadable header is `period_unverified`; one under a different period does not count. Every match keeps its header and evidence.
- **Readout:** per component and per signal, with lower and upper bounds for unavailable or unverified rows, Wilson 95% intervals and both filing eras. The signal verdicts use the flow components (net income and operating cash flow). Prior fiscal-year-end assets were normally public earlier through the annual report, so they are reported separately; a later full extraction must take them from that report at its own verified clock.
- **Verdict per signal:** `release_complete_common` if the Wilson lower limit is at least 0.7; `release_complete_rare` if the upper limit is below 0.3; otherwise `inconclusive`. `common` justifies only a separately declared full extraction of that signal's components. Nothing here backdates a 10-Q value, changes a completed result or promotes a strategy.
- **Verification:** offline synthetic tests before any request; an independent checker that re-derives every classification from the saved bytes; and a seeded list of 20 events with their evidence for an owner spot check.

## Decisions needed before freezing

1. **Frame:** decision-session `single_prior` events as drafted, or also the novelty audit's pairs.
2. **Sample size:** 150. Expect about 450–600 requests (8–10 minutes at 1 request per second), with a hard cap of 1,800.
3. **Thresholds:** 0.7 and 0.3.
4. **Where to run:** your workstation, or this cloud container if its network policy allows `www.sec.gov`. Checking that is itself an SEC request.
5. **10-Q values:** `records.json` (208 MB) is not in the clone. Either run the declared projection on the workstation and commit its small output, or upload a gzip copy split into parts under 10 MB.
6. **User agent:** reuse the frozen capture's agent, which has no contact address, or add one; SEC's fair-access guidance asks for a contact.
