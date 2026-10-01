# Next stage: cash-backed earnings changes and the preceding price response

This is a proposal, not an executed experiment or a promotion decision. Its design was developed from the source qualification counts before account results were inspected. The parent agent supplied four headline account results before this document was saved; the design below was not changed in response. No account outcome files were read to prepare it.

The next useful experiment is a larger, fixed issuer panel testing whether **improved cash backing distinguishes earnings changes that continue to move prices over the following five sessions**, and whether the preceding price/volume response modifies that relationship. This adds original-filing information that the existing technical models do not have. It also gives a limited nonlinear model a concrete economic reason to exist.

The pilot has 121 structurally eligible events and 27 selected events during 2017–2025, from only five contributing issuers. Twenty-seven is below its declared 30-event minimum. Repeated quarters from five firms do not provide enough independent variation to train and validate a complex model, even if a small account path happens to be profitable. Broader evidence is required; profitability of the simple rule is not a prerequisite for testing interactions.

## One fixed expansion

Predeclare 100 US operating-company common-share CIKs using the existing frozen listing and historical access. Select on verified security type and 2016 dollar liquidity, with a deterministic CIK-hash order among eligible issuers; do not rank by later returns, the pilot's outcomes, or successful fact extraction. Freeze the liquidity threshold, hash seed, exact CIK/security list and exclusions before joining event returns. Exclude funds, ADRs, REITs and financial firms because the proposed operating cash-flow comparison has materially different meanings for those instruments. Use original historical classification where it can be verified; otherwise keep classification uncertainty explicit rather than inventing a historical label.

Retain every requested issuer and original filing, including failures, and make no replacements after source inspection. The initial cohort is necessarily restricted to names in the present frozen listing with pre-2017 history: it is a current-member historical sample, not a reconstructed historical market. One hundred issuers is a bounded mechanism test, not the final trading universe. Declare the SEC request, storage and rate limits before acquisition; reuse saved originals. Source qualification must precede the return join.

## Information and mechanism

Keep the existing seasonal net-income innovation and its eight-earlier-event scale, `S`, unchanged. Add one cash-backing change from the **same original accession**:

`Q = ((CFO_YTD - NI_YTD) - (CFO_prior_year_YTD - NI_prior_year_YTD)) / prior_FY_assets`.

Require matching current/prior-year YTD periods, original non-dimensional USD facts, exact `NetCashProvidedByUsedInOperatingActivities` and `NetIncomeLoss`, and the already qualified prior fiscal-year-end assets. No later accession, modern companyfacts value, Q4 interpolation, or alternative profit/cash-flow concept may fill a gap. Same-period seasonal differences avoid manufacturing a stand-alone quarter from later filings. Positive `Q` is a cash-backing hypothesis; working capital, tax timing and noncontrolling interests can still make it misleading.

Use five inputs only: `S`, `Q`, the preceding five-session stock-minus-SPY return, the latest completed session's dollar activity divided by its preceding 20-session median, and SPY's position relative to its 200-session moving average. All price inputs end at the previous close, with adjustment identities and volume units qualified. The economic question is whether cash-supported improvement has a different short-run response when prices have already risen sharply or activity is unusual.

Keep the conservative existing public-availability floor and 09:00 ET decision, followed by that session's close entry. SEC acceptance is not automatically the first earnings-release time. The hypothesis is post-filing response, not an announcement-surprise trade. No modern LLM interprets historical filings: deterministic facts avoid historical-knowledge leakage.

## A bounded comparison

Run five recipes on the **same complete-feature population**, all with five-session holdings:

1. Every eligible filing, with the existing deterministic tie order.
2. Existing `S >= 1` selection, ranked by `S`.
3. `S >= 1` and `Q > 0`, still ranked by `S`.
4. One fixed regularized linear model predicting return and downside from the five inputs.
5. One fixed shallow boosted-tree model predicting the same outputs, to test their interactions.

Save the wider structural population and each unavailable-feature reason separately; a missing `Q` must not silently improve the comparator's sample. Reuse existing model, calibration and cash-planning interfaces. Freeze exact presets before fitting; no threshold, horizon or hyperparameter sweep. Learned entries use the existing expected-net-dollar utility and downside penalty, with calibration fitted only on prior calibration observations. They do not receive a more favorable fee assumption or sizing rule.

Fit 2017–2019 events, calibrate on 2020 and test on 2021; then expand the fitting window annually, using the immediately preceding year for calibration and testing through 2025. Purge outcomes whose scheduled exit reaches the next partition. Fit preprocessing only on fitting rows. Save every fold failure and abstention; never substitute an easier model after seeing test performance. This declares two learners across five test years, with their forecasts shared between fee scenarios. The five recipes produce **ten continuous accounts**, not separate accounts reset at each model switch. Every control and learned account evaluates the identical 2021–2025 test period, begins with the same USD2,000, and retains cash and positions continuously through model switches. The 2017–2020 observations supply fitting/calibration only, not earlier control-account profits. All these historical years remain research data, not a pristine prospective holdout.

## Execution and decision

Use USD2,000, whole shares, five slots, the existing 20% position cap and 0.5% NAV risk sizing, historical settlement calendars, fixed fee-inclusive order reservations and quantity reductions only at the assumed fill. Compare the existing proportional 40-bps scenario with independently specified Moomoo charges plus the same 40-bps execution scenario. That execution allowance is a sensitivity assumption, not measured fills; FX funding is separate. Preserve action/source limitations and invalid required fills.

Judge incremental evidence against both controls: net expectancy, fees, exposure, sampled drawdown, issuer concentration, and weekly/monthly/yearly stability, with every unsuccessful path reported. A model beating an unconditional control while still losing money is useful diagnosis, not a deployable strategy. A gain concentrated in a few issuers or one year does not establish broad alpha. A drawdown beyond the owner's 30% limit is unacceptable. Source/sample failures must lead to an explicit inconclusive result, not relaxed entry thresholds.

The immediate deliverable is a frozen issuer list and source/feature declaration for this one experiment. Before acquisition or fitting, that declaration must fix the exact liquidity threshold, CIK-hash seed, allowed security types/classification treatment, model presets and minimum fitting/calibration row counts. It proceeds regardless of the simple pilot's profit sign, and it does not authorize live trading or automatic paper promotion.
