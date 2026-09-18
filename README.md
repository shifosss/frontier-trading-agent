# Frontier Research

A local research workstation for US and Canadian stocks and ETFs. It imports
traceable data, runs real Nautilus simulations, compares fixed baselines and bounded
model proposals, and preserves the decisions and accounting behind each result.

**Current status — September 18, 2026:** the workstation and research workflow run
locally. Historical studies remain exploratory. Corporate-action accounting,
complete point-in-time data, and broker execution are not qualified; no alpha or
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
point-in-time or total-return evidence. Known dividends/splits reject replay;
unknown coverage requires explicit exploratory opt-in and leaves `total_return` null.

## Useful commands

Use the returned dataset, run, and frozen IDs in place of the placeholders:

```powershell
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
outcomes, and broker-paper reconciliation remain open. Synthetic opening quotes
model fixed slippage without observed bid/ask or market impact. Historical intervals
used by research are exposed, and frozen observation is not a live trading system.

See [validation evidence](docs/validation.md), [current progress](docs/progress.md),
[roadmap and acceptance criteria](docs/roadmap.md),
[engine qualification](docs/engine-qualification.md), and
[existing connector boundaries](docs/existing-connectors.md).
