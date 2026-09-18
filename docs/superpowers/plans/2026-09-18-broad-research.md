# Broad market research and durable operation

> **For agentic workers:** Use subagent-driven implementation and independent review. The owner has authorized implementation and useful experiments; no further design approval is required.

**Goal:** Replace the 41-name research ceiling with sourced listing discovery, repeatable strategy comparisons, and visible scheduled progress while preserving the active paper mandate.

**Architecture:** Keep discovery, historical signal research, and paper execution separate. Reuse daily-data normalization and the existing dependencies. Persist dated universe membership, raw captures, frozen experiment definitions, every result and failure; never promote a winner automatically.

**Tech stack:** Existing Python 3.13, pandas/numpy, httpx, exchange calendars, SQLite, FastAPI/React and Windows launchers. No new paid services or dependencies.

**Spec:** Owner instructions in this task and `docs/automated-trading-plan.md`.

## Decisions and acceptance checks

- [x] Repair background process lifetime first. A disposable child must survive its launcher exiting, then the actual web and paper workers must produce fresh independent observations. Change launcher code only; preserve the frozen financial source identity.
- [x] Discover current US common/ordinary listings from Nasdaq Trader and Canadian candidates from TMX's issuer file. Save source bytes, timestamps and exclusions. Current membership is not historical membership. Unknown security types and unverifiable symbols stay visible as exclusions.
- [x] Capture broad histories in resumable batches with existing daily normalization. Do not rank symbols using future liquidity to claim historical point-in-time eligibility. Expose discovered, attempted, usable and failed counts separately; a stock missing its own lookback is individually ineligible.
- [x] Freeze four hypotheses before evaluation: momentum, trend pullback, mean reversion, and breakout; compare 5/10/20-session forward cohorts. Test USD/CAD books separately at 500/2,000/10,000/100,000 simulated native-currency balances and 20/40/100 basis-point round-trip costs. These are signal-research cohorts, not a second portfolio execution engine.
- [x] Use chronological 60/20/20 development/validation/evaluation partitions and discard cohorts crossing boundaries. Signals use only completed data; entries use the next session close. Missing selected exit data invalidate the entire cohort rather than silently dropping a losing name. Historical affordability remains limited by current-vintage split adjustment.
- [x] Compare against cash and native-market ETF benchmarks on matched dates and costs. Show all attempted hypotheses, coverage and adverse cases, not just the best result. No CAGR or account-return claim from cohort averages.
- [x] Save prospective candidate observations on each completed-session refresh. Future refreshed data can evaluate those frozen names without changing the original signal. Distinguish these observations from exploratory historical partitions.
- [x] Expose research status, latest results and one-click refresh in the workstation; keep capture/evaluation out of a long blocking web request. Add a local CLI for scheduler use and update the existing Codex follow-up with useful research work after the close.
- [x] Test lookahead resistance, partition boundaries, missing outcomes, cost/cash arithmetic, source parsing, resume/deduplication and worker startup. Run the existing relevant suite and frontend build. Apply Ponytail full/standard complexity review separately from financial correctness review.

## File ownership

- Launcher worker: `scripts/start.ps1`, `scripts/start-paper.ps1`, shared helper and focused launcher tests.
- Discovery worker: `src/frontier/research_universe.py`, parser tests.
- Strategy worker: `src/frontier/strategy_study.py`, mathematical/causality tests.
- Integration: `src/frontier/research_lab.py`, `src/frontier/cli.py`, `src/frontier/web.py`, frontend research view, orchestration tests and documentation.

The active paper universe stays pinned to its existing 11 eligible US stocks. An expanded paper policy requires an explicit versioned migration after this research supplies evidence; changing the research list must not silently alter accepted orders.
