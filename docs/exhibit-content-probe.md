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
- **Requests:** for each sampled 8-K, only its accession index, its SGML header and at most three EX-99 exhibits; at most 750 requests in total. The frozen capture's bounds apply: 1 request per second, no retry of a completed attempt, no redirects, a global stop on 403 or 429, and only `www.sec.gov/Archives/edgar/data/` URLs.
- **Identity:** the header must show the issuer's CIK and form 8-K. Its acceptance time, re-clocked with the frozen `event_clock`, must still fall in an earlier decision session than the 10-Q's. Failures stay in the sample and count as not stated.
- **Comparison values:** the S and Q input values and period endpoints of the sampled 10-Qs, projected from the completed qualification `records.json`. No other field is read, and no price, return, forecast or account.
- **Matching:** a component is stated when a table row labelled for it (net income, total assets, operating cash flow) has a cell equal to the 10-Q value after units and display rounding. Matching both the current and prior value fixes the period. Every match keeps its evidence.
- **Readout:** per component and per signal, the share of the 150 events with every input stated, with lower and upper bounds for unavailable rows, Wilson 95% intervals and both filing eras.
- **Verdict per signal:** `release_complete_common` if the Wilson lower limit is at least 0.7; `release_complete_rare` if the upper limit is below 0.3; otherwise `inconclusive`. `common` justifies only a separately declared full extraction of that signal's components. Nothing here backdates a 10-Q value, changes a completed result or promotes a strategy.
- **Verification:** offline synthetic tests before any request; an independent checker that re-derives every classification from the saved bytes; and a seeded list of 20 events with their evidence for an owner spot check.

## Decisions needed before freezing

1. **Frame:** decision-session `single_prior` events as drafted, or also the novelty audit's pairs.
2. **Sample size:** 150. That is about 450–750 requests and roughly 8–13 minutes at 1 request per second.
3. **Thresholds:** 0.7 and 0.3.
4. **Where to run:** your workstation, or this cloud container if its network policy allows `www.sec.gov`. Checking that is itself an SEC request.
5. **10-Q values:** `records.json` (208 MB) is not in the clone. Either run the declared projection on the workstation and commit its small output, or upload a gzip copy split into parts under 10 MB.
6. **User agent:** reuse the frozen capture's agent, which has no contact address, or add one; SEC's fair-access guidance asks for a contact.
