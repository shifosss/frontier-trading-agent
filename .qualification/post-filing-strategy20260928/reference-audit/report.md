# Independent descriptive event-reference audit

Passed all 121 eligible events, 484 adjusted-price endpoints, 27 selected labels, five-session alignment and 30 overall/issuer/year summary groups. Calculations used independent 40-digit Decimal arithmetic without importing or rerunning the helper. Maximum absolute discrepancy in a return or mean was 3.14e-16.

| Population / weighting | Stock return | Same-date SPY return | Stock minus SPY |
|---|---:|---:|---:|
| All 121 eligible; equal event |74.8799bps|52.0166bps|22.8633bps|
| Selected 27; equal event |76.5655bps|72.2008bps|4.3647bps|
| All eligible; equal entry date |73.9331bps|52.8346bps|21.0985bps|
| Selected; equal entry date |77.9884bps|76.1314bps|1.8570bps|

The selected group has a stock-minus-SPY average 18.4986bps lower under equal-event weighting and 19.2415bps lower under equal-entry-date weighting. Its slightly higher gross stock return coincides with stronger market returns on those dates. These descriptive comparisons do not establish improved stock-specific selection or causal alpha. The selected sample spans five issuers and nine years but has only 27 events, below the unchanged 30-event support gate.

The full denominator reconciles: 252 original feature records; 90 outside the 2017-2025 filing period; 162 in period, of which 41 fail structural qualification; 121 eligible matched events across 117 entry dates. All 27 selected events match, across 26 dates. No eligible observation was discarded for missing future endpoints. Ford contributes 27 in-period structural exclusions and zero eligible events; AT&T contributes 14 exclusions and 13 eligible events. AAPL/BANF/HRL/MSFT each contribute 27 eligible events.

All row identities and selection labels match the frozen feature file, including S>=1. Every stock/SPY entry/exit value matches the already verified market array and scheduled five-session dates. Original and completed-reference identities were checked. Missingness and exclusions are retained separately from measured returns.

This is an unfunded gross event description, excluding fees, share quantities, cash constraints and taxes. It retains mixed-provider retrospective adjusted-price and corporate-action limits. Funded account arithmetic is independently audited elsewhere. No network request, funded-account file read, source edit or strategy rerun occurred. Exact Decimal rows, aggregates, identities and denominator counts are retained beside this report.
