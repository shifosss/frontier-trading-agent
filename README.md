# Frontier Trading

The product target is automated daily/weekly trading. A persistent **paper operator** now joins the scanner and research engine: weekly entries, daily exits, settled-cash checks, CAD drawdown control, durable orders and restart recovery. The existing US$100,000 Alpaca paper account was initialized and its five-minute worker started on September 18, 2026; the first reconciliation passed with no holdings or orders. Check the Trading desk for current saved state. This larger-account trial does not validate US$500 affordability, and live execution is not implemented. Start with the [paper operator setup](docs/paper-operator.md) and [updated delivery plan](docs/automated-trading-plan.md).

A local research workstation for US and Canadian stocks and ETFs. It imports
traceable data, runs real Nautilus simulations, compares fixed baselines and bounded
model proposals, and preserves the decisions and accounting behind each result.

**Current status — September 18, 2026:** the workstation and research workflow run
locally, including a 41-instrument market scanner and tested cash-dividend accounting.
Historical studies remain exploratory. Stock splits, complete point-in-time data,
options, and broker execution are not qualified; no profitable trading edge or
state-of-the-art performance is claimed.

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

- **Active-trading target:** hourly/daily decisions and intraday to roughly one-week stock positions. The [cadence specification](docs/trading-cadence.md) separates holding time from multi-year testing and identifies the required update to the existing historical/paper baselines.
- **Historical-first Strategy lab:** 8,434 current US/Canadian candidates, daily data requested from 2000, 30 declared strategy/horizon hypotheses, continuous cash portfolios, daily drawdowns, and training-only rolling selection. Four account sizes and three costs remain visible, alongside the original cohort and prospective observations. See [historical research](docs/historical-research.md) and the [completed 28.6-million-bar study](docs/historical-research-results.md), including negative US results, Canadian data gaps and an audited issuer-data repair study. The lab runs separately from the 41-name starter scanner and frozen paper account. See [broad research](docs/broad-research.md) for coverage, scheduling and interpretation.

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
nested walk-forward evaluation, advanced model comparisons, accumulated prospective
outcomes, and qualification of the full broker-paper order lifecycle remain open. Synthetic opening quotes
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
