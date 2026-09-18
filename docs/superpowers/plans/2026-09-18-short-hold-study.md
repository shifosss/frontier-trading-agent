# Run the short-hold study for the owner

The owner asked the agent to run the study. The approved direction is in `docs/trading-cadence.md`; no manual launch is required.

## Decisions

- Add a versioned 1/3/5-session daily portfolio engine, preserving the existing 5/10/20-session baseline and frozen paper policy. Reuse existing feature and reporting helpers.
- Screen daily and manage each position's age, orders and settled cash independently. The old nonoverlapping batch loop does not implement the clarified cadence.
- Use next-close entry and explicitly label it overnight/daily research. Hourly stock research still requires actual hourly stock data; do not fabricate it.
- Keep existing training/selection windows for a controlled comparison. Report trade-level and weekly/monthly outcomes; faster model reselection is a different experiment.
- Use sourced historical settlement transitions and document conservative holiday assumptions. A cash account cannot fund another trade using unsettled proceeds.
- Reuse the immutable completed run's source capture, cutoff and membership. This avoids a new data vintage or unnecessary acquisition obscuring the effect of changed trading behavior.
- Keep source repairs explicit. The original capture's missing marks remain visible; the separate issuer-data sensitivity is not silently merged.
- Stream or limit detailed audit retention where the full grid would otherwise create millions of resident trade dictionaries. Retain all performance comparisons, failure reasons and definitions; describe exactly which detailed paths are saved.

## Work

- [x] Implement and economically test the independent-position simulator and trade/period metrics.
- [x] Verify US/Canadian settlement transitions and holiday behavior.
- [x] Add short-hold mode and immutable-source reuse to CLI/web/background orchestration.
- [x] Update the interface to launch the new mode and explain actual cadence/results.
- [x] Independently review financial logic and maintainability; run relevant project checks.
- [x] Profile a representative real-data smoke, then launch the full declared study.
- [x] Inspect all completed/incomplete outcomes, verify the actual interface, and report results.

## Execution evidence

The 13-instrument USD500 smoke completed all 90 fixed portfolios, three rolling accounts and six references in 24.68 seconds, with about 412 MB peak working set. Full project verification passed 307 tests, Ruff and the production frontend build. Independent randomized accounting review reconciled 5,231 completed trades.

Full run `90af4c840aad48f7ab58fba7a682f96a` started at 2026-09-18T21:53:09Z using the unchanged 8,234-history capture from `577a24e71a844022b3ac86ca66e32c34`. No new source repair, acquisition or spending is included.

The full job published at 2026-09-18T22:08:08Z (14m59s). Results: 509 fixed portfolios complete, 211 incomplete from required Canadian prices; all 24 rolling accounts and 48 references complete. Eighteen rolling accounts remained entirely in cash. The current grid does not justify promotion. Full findings: `docs/short-hold-research-results.md`. Final independent full-result audit passed all 792 account/reference rows and 1,344 rolling trades; the actual interface passed 96 filter comparisons across four widths. Existing automation now uses these completed findings for further research.
