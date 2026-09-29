# Frontier Trading

The target is automated hourly/daily decisions with intraday to roughly one-week individual-stock positions. The local system now combines broad historical research, saved learned models and persistent simulated accounts with a separate operating Alpaca paper baseline. Start with the [delivery plan](docs/automated-trading-plan.md), [latest account rehearsal](docs/candidate-replay-results.md) and [paper operator](docs/paper-operator.md).

**Current status — September 28, 2026:** daily models can screen the frozen broad universe and carry holdings, orders and settled cash across restartable historical sessions. Both declared USD2,000 rehearsals lost money, including before fees. Corporate-action source inconsistencies are under independent investigation; no model is economically qualified for promotion. The existing eleven-stock paper baseline has submitted and reconciled simulated fills, but still uses weekly entries and up to 20-session holds. Hourly research, daily paper migration, options and live execution remain unfinished.

**Latest strategy experiments:** the [original-filing comparison](docs/post-filing-results.md) completed four USD2,000 accounts after qualifying 252 original disclosures. The income filter gained only USD2.53 under proportional costs and lost USD73.23 with modeled Moomoo fees; its 27 selected events are below the declared sample minimum. The [intraday continuation/reversal pilot](docs/intraday-opening-results.md) completed four losing accounts and 2,479 independently checked trades using actual historical minutes. The [six-account calibration comparison](docs/calibration-shrinkage-results.md) improved capital preservation but produced three losses, two all-cash accounts and one small gain from only three early-2016 trades. No repeatable profitable strategy is qualified. Broader original-disclosure coverage and distinct earnings/price conditions are the next research priority.

Earlier [18 conditional-selection accounts](docs/conditional-strategy-selection-results.md) covered 4,434 eligible US-listed equity instruments and lost under all declared scenarios; independent checks reconciled 38,849 trades. The [54 reversal/continuation/mixture accounts](docs/strategy-interaction-results.md) and [81-cell timing study](docs/strategy-timing-results.md) also remain visible. Original sources, unsuccessful variants and complete results are preserved.

**Updated research mandate:** USD10,000 is now the primary simulated balance, with USD2,000 retained for comparison. The owner's 5–15% weekly aspiration is measured on the entire account after costs and does not relax the 30% drawdown or cash-only constraints. Existing results do not support that return rate. Active ETF and cash-funded option research now accompanies the original-filing expansion; a bounded Alpaca probe returned 36 historical option bars, while full historical-chain access through Alpha Vantage was unavailable. See the [capital comparison, return objective and source findings](docs/capital-and-return-objective.md).

The [next cash-backed earnings study](docs/earnings-quality-research.md) declares 20 accounts and a fixed 100-issuer panel. A source-only screen qualified 1,222 issuers and froze the first 300 in a deterministic hash order for SEC classification. The new cash-flow feature passed original-source checks; the new model fits and accounts await the broader financial-source capture.

The React/FastAPI workstation preserves data, decisions, accounting, failures and reports. Local historical simulations, saved model forecasts and actual paper observations are distinct evidence sources; none demonstrates future profitability.

## Open the workstation

On the configured Windows machine, double-click **[Launch Frontier.cmd](Launch%20Frontier.cmd)**.
It starts or reuses this workspace's local service and opens
[Frontier at localhost](http://127.0.0.1:8765).

For a fresh checkout, use Python 3.13, uv, and Node.js/npm. From the repository root:

```powershell
uv sync --frozen
npm --prefix frontend ci --cache .cache/npm
npm --prefix frontend run build
& '.venv/Scripts/python.exe' -m frontier.cli doctor
& '.venv/Scripts/python.exe' -m frontier.cli demo
& '.venv/Scripts/python.exe' -m frontier.cli serve
```

The demo creates fictional US/Canada data and a genuine engine run with JSON and
HTML reports. The app uses `data/datasets`, `data/frontier.sqlite`, and `artifacts`.
Use global `--workspace PATH` before a command to select another workspace.
The launcher can build missing frontend assets; it expects the Python environment
from `uv sync --frozen` to exist.

## What works

- **Active-trading target:** hourly/daily decisions and intraday to roughly one-week stock positions. The [cadence specification](docs/trading-cadence.md) separates holding time from multi-year testing. The new historical lane screens daily with independent 1/3/5-session positions; hourly stock qualification and paper-policy migration remain open.
- **Historical-first Strategy lab:** the frozen 8,434-member US/Canadian capture contains 8,234 usable histories and 28.6 million daily bars. The multi-model lane compares Ridge, ExtraTrees, boosted trees, a six-output MLP and ensembles with technical-rule controls across 1/3/5-session holds, two budgets and three cost scenarios. Of 720 accounts, 569 completed and 151 retained missing-data failures; no strategy is promoted. See [multi-model findings](docs/multi-model-research-results.md) and [historical research](docs/historical-research.md). The earlier rule and 5/10/20-session studies remain explicit baselines.
- **Saved-model account rehearsal:** immutable fitted models, purged sample boundaries, every-session forecasts, independent positions, scheduled exits, cost-aware sizing and dated cash settlement. SQLite chunks preserve state across process restarts; the API and CLI can resume the same new journal. See [commands and compatibility](docs/candidate-replay.md) and [independently audited results](docs/candidate-replay-results.md). Historical fills are atomic simulations; broker partial-fill integration remains separate.
- **Source qualification:** a separate September 25 [bounded refresh](docs/weekly-data-refresh.md) captured 8,387 histories and retained 50 failures without replacing the full historical capture. An [action inventory](docs/action-source-validation-plan.md) covers 7,143 reported events with a predeclared 91-event independent sample. The [AIXI audit](docs/aixi-source-continuity.md) confirms a source-unit error; revisions and original results are preserved.


- **Stock scanner:** one click captures free five-year daily histories for 41 declared
  US/Canadian stocks and ETFs. A fixed momentum/volatility rule ranks stocks;
  ETFs supply context. Whole-share sizing separates CAD/USD cash and exposure
  groups. Every exclusion and saved scan is inspectable. Forward-return cohorts
  compare the rule with native benchmarks and cash, with cost stress and explicit
  missing-data exclusions; they are not a compounded portfolio backtest.
- **Account mandate:** CAD600–800 monthly additions, a recorded 30% drawdown
  tolerance, Wealthsimple primary/moomoo cash alternative, no borrowing, planned
  CAD-to-USD funding allowed, and separate long-term ETF reserves. The scanner can
  model a one-time conversion into retained USD cash, using a dated reference and
  published fee tiers, without making a transfer or counting the CAD twice. CAD700 is illustrative cash; the scanner
  does not monitor the real account or enforce its drawdown limit.

- **Research and inspection:** local React/FastAPI workstation, immutable dataset
  imports, saved runs and failed attempts, equity curves, decisions, fills, positions,
  source provenance, configuration, and standalone reports.
- **Actual accounting:** Nautilus Trader 1.231.0 executes orders in one simulated
  multi-currency cash account. USD/CAD funding and fees remain separate; dated FX
  supports reporting without invented conversion trades. Whole shares, cash limits,
  and a 20% exposure-group cap constrain new targets. Close signals wait for a
  strictly later eligible opening.
- **Declared comparisons:** cash, passive, trend, and reversion baselines; a fixed
  11-trial exploratory tournament includes lookback variants and cost stress.
  Inputs, costs, attempts, evaluation access, and replay results are retained.
- **Bounded model research:** an existing ChatGPT-authenticated Codex CLI supplies
  at most two typed proposals per campaign. Accepted templates receive actual replay
  feedback. Two real two-call campaigns completed on fictional and historical data.
  Calls consume existing account usage; recorded token counts are not a dollar invoice.
  Generated executable code and automatic promotion are excluded.
- **Frozen observation:** completed runs can be frozen, then evaluated against a
  new compatible dataset with appended observations. Records distinguish historical
  observations from decisions captured before a future eligible opening. They do
  not submit broker orders or fabricate future fills.

The retained real sample contains 100 daily bars each for SPY and XIU, plus 434 SPY
hourly bars across 62 US sessions. Bank of Canada observations provide dated USD/CAD
reference rates. Raw prices and inferred historical availability do not establish
point-in-time or total-return evidence. Known cash dividends require verified ex-date
and payment-date records: entitlement enters NAV before payment but cannot be spent
until paid. Splits remain rejected. Unknown coverage requires explicit exploratory
opt-in and leaves `total_return` null. The previously failing full SPY/XIU study now
runs on a new immutable dataset with a dividend payment date and earlier published FX.
The original source and failure records are preserved.

## Useful commands

Use the returned dataset, run, and frozen IDs in place of the placeholders:

```powershell
& '.venv/Scripts/python.exe' -m frontier.cli scan --cad 700 --usd 0
& '.venv/Scripts/python.exe' -m frontier.cli scan --no-refresh --cad 700 --usd 0
& '.venv/Scripts/python.exe' -m frontier.cli scan --no-refresh --cad 700 --usd 0 --convert-cad 700
& '.venv/Scripts/python.exe' -m frontier.cli scans
& '.venv/Scripts/python.exe' -m frontier.cli datasets
& '.venv/Scripts/python.exe' -m frontier.cli run DATASET_ID --strategy trend --lookback 20 --allow-incomplete-actions
& '.venv/Scripts/python.exe' -m frontier.cli campaign DATASET_ID --allow-incomplete-actions
& '.venv/Scripts/python.exe' -m frontier.cli model-campaign DATASET_ID --max-proposals 2 --allow-incomplete-actions
& '.venv/Scripts/python.exe' -m frontier.cli verify-replay RUN_ID
& '.venv/Scripts/python.exe' -m frontier.cli freeze RUN_ID
& '.venv/Scripts/python.exe' -m frontier.cli observe FROZEN_ID NEW_DATASET_ID
```

`runs`, `campaigns`, `model-campaigns`, `frozen`, and `observations` list saved work;
`show RUN_ID` returns its registry record and result. `source-status`, `fetch-boc`,
`fetch-longbridge`, and `import-session-hourly` expose the narrow source helpers.
Run `scripts/verify.ps1` for lint, tests, TypeScript checks, and the frontend build.
Run any command with `--help` for arguments. Model campaigns require the existing
Codex CLI ChatGPT login; ordinary replay and saved-artifact inspection do not.

## Current gaps

The Longbridge connector in Codex successfully supplied the retained hourly data.
Its standalone CLI is a separate access path: the September 18 status check found
an expired token. The user must authenticate that CLI manually before unattended
Longbridge fetching can work. The application never logs in automatically.

Canadian hourly coverage, complete corporate actions, longer point-in-time history,
nested walk-forward qualification, demonstrated model profitability, accumulated prospective
outcomes, and qualification of the full daily broker-paper order lifecycle remain open. Synthetic opening quotes
model fixed slippage without observed bid/ask or market impact. Historical intervals
used by research are exposed, and frozen observation is not a live trading system.

See [the completed scanner and dividend study](docs/scanner-study.md),
[USD funding study](docs/usd-funding-study.md),
[account and options readiness](docs/active-account-readiness.md),
[validation evidence](docs/validation.md),
[Ponytail code-quality review](docs/code-quality-review.md),
[current progress](docs/progress.md),
[roadmap and acceptance criteria](docs/roadmap.md),
[engine qualification](docs/engine-qualification.md), and
[existing connector boundaries](docs/existing-connectors.md).
