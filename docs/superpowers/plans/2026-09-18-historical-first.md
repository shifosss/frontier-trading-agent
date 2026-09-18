# Historical-first research implementation plan

> **For agentic workers:** Use subagent-driven development with independent file ownership and a financial correctness review.

**Goal:** Improve strategies using long historical market data and continuous cash portfolio tests before relying on new forward observations.

**Architecture:** Keep the existing paper mandate and cohort study intact. Add an isolated, resumable historical capture and walk-forward study, using the existing research universe, background launcher, web patterns and installed numerical tools.

**Tech stack:** Python, pandas/numpy, exchange_calendars, httpx, SQLite locks, FastAPI, React.

**Spec:** The user's September 18 instruction prioritizes broad, useful historical experimentation using existing access and free data.

## Decisions and reasons

- Request daily history from 2000: this adds the dot-com decline, financial crisis, pandemic and inflation/rate shock rather than merely multiplying recent-period variants. Individual IPO dates limit actual history.
- Expand exchange directories and preserve exclusions; issuer counts, share classes, ETFs and derivative contracts are different coverage measures.
- Test continuous cash portfolios and training-only rolling selection. Independent cohorts cannot measure portfolio drawdowns or deployable returns.
- Declare baseline and benchmark-trend-filter hypotheses before examining new outputs. Report every attempt, including cash and failures; repeated tuning against exposed history is not fresh out-of-sample evidence.
- Keep raw capture bytes and source identity, and label current membership and current-vintage adjustments honestly. Longer history alone does not cure survivorship bias.
- Use isolated historical paths so data expansion does not alter a frozen paper strategy or invalidate its journal.

## Tasks

- [x] Expand and test `research_universe.py`: TSXV and reliable additional Canadian directories; record source counts and publication dates.
- [x] Add `historical_data.py`: fixed date-range capture, vectorized calendar normalization, raw provenance, meaningful normalization equivalence and old-date tests.
- [x] Add `historical_study.py`: continuous whole-share cash accounting, costs, drawdowns, yearly evidence, 3-year training/1-year tests, all-attempt reporting and lookahead/accounting tests.
- [x] Add `historical_lab.py` and CLI/web/UI integration: durable resumable jobs, read-only status and downloadable evidence, no page-load launch or automatic promotion.
- [x] Run a real broad historical capture and study; inspect coverage, failures, selection stability and economic results; record findings.
- [x] Independently review financial correctness and Ponytail maintainability; run full project verification and browser checks.
- [x] Update the existing automation to prioritize historical research and source freshness, retaining quiet notifications and the existing paper baseline.

## Acceptance evidence

Saved results must state actual usable symbols, rows and date spans; each training selection must precede its test; missing held prices must not silently remove losses. Daily marks and costs must reconcile to cash and equity. Full report downloads and UI filters must agree. Historical findings must distinguish exploratory evidence from readiness for live trading.


## Implementation review record

- Discovery: 8,434 candidates from saved official US, TMX, CSE and Cboe sources; eight parser tests and actual provider-symbol probes passed.
- Capture: reported-split reconstruction independently matched AAPL's January 2000 nominal prices. Stable calendar bounds reduced a 100-history normalization from 18.3 seconds to 4.64 seconds.
- Portfolio engine: 30 declared hypotheses, daily cash/equity, all budget/cost comparisons, historical-only annual selections and ETF/cash references; 14 economic and chronology tests passed.
- Review fixes: both-currency merge and progress callback; historical T+3 and settlement across folds; no held-price requirements for zero-filled shares; unknown benchmark regime marked incomplete; already-loaded capture identity checked before publication.
- Validation: final full 262-test suite, lint and frontend build passed. The final 35-test historical/discovery pass includes a new provenance regression. Browser checks cover 96 synthetic filter combinations and four actual running-state widths.
- Automation: the existing weekday 09:35/17:35 Toronto follow-up now prioritizes historical research. Refresh the full historical dataset weekly or when scientific code changes, rather than redownloading on every wakeup.
- Actual run `577a24e71a844022b3ac86ca66e32c34` completed: 8,234 histories / 28,621,250 bars, 720 fixed portfolios, 24 rolling portfolios and 48 references. US representative rolling accounts lose money after costs; all Canadian rolling accounts are incomplete at missing Wajax marks. Findings and denominators are in `docs/historical-research-results.md`.

- Final actual UI: 48 saved-result filter views and incomplete CAD at four widths passed; missing marks and partial history are explicit, with no mismatched-period benchmark comparison. Full evidence download was range-verified.
