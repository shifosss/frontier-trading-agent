# Interface implementation and verification

Implemented local React/TypeScript/Vite workstation, FastAPI API and Windows launcher. Visual plan and critique are in docs/interface-design.md. No external font, chart service, market feed or broker control is included.

## What is present
- Study: real immutable dataset selection and evidence, country/currency/coverage, passive/cash/trend/reversion, 20-session lookback for signal strategies, USD10k/CAD10k, explicit per-order fees/slippage, collapsible advanced settings, per-dataset-version exploratory opt-in, Ctrl+Enter.
- Results: actual timestamped equity, raw-price return explicitly labeled for incomplete actions, drawdown/fills/NAV, native fees/exposure/Sharpe, decision/input/availability/target/next-execution inspection, matching actual fills, holdings, saved HTML/config/result. Prior result stays visible as form settings change.
- Data: source, fetched versus observation dates, content identity, calendar/FX explanation, preview and local folder import. Files must resolve inside workspace/data/imports or workspace/data/raw.
- Experiments: persisted actual/failed runs, errors, sortable table, selected same-dataset comparisons normalized to initial NAV100, differing costs/funding shown; declared baseline tournament with actual trial count.
- Operations: actual engine/runtime/version/workspace/counts and limitations. Hourly execution and corporate actions explicitly unqualified; broker and FX trading unsupported.
- API uses one synchronous engine coordinator; status reads remain outside the lock. Only loopback Host names accepted. Mutations require application/json and matching Origin if present; cross-site fetches rejected. Unknown API routes return JSON404. Result/report paths are registry-owned and resolved within artifact root. Import folder/file symlink escapes are rejected.
- serve(workspace,port=8765) seeds demo only if no datasets. scripts/start.ps1 checks environment/assets, starts a hidden Python process, verifies matching service+workspace health, then opens browser. Launch Frontier.cmd quotes the script path including spaces/apostrophe. --NoBrowser permits subprocess checks.

## Validation so far
- npm --prefix frontend install --cache .cache/npm --prefer-offline --no-audit --no-fund: installed69 runtime/build packages plus pinned Prettier3.6.2 for readable source; package-lock.json generated.
- npm --prefix frontend run build: passed, TypeScript then Vite; no CDN dependency.
- npm --prefix frontend run typecheck: passed.
- .venv/Scripts/python.exe -m ruff check src/frontier/web.py tests/test_web.py: passed.
- .venv/Scripts/python.exe -m pytest tests/test_web.py -q:6 passed in22.09s, including an actual11-trial campaign with every run retained. Actual Nautilus run->registry->result->report round trip passed; known dividend rejection retained failed row. Other tests cover demo idempotency/preview/status, host/origin/content-type restrictions, import traversal/report confinement and JSON404.
- Existing dependency deprecation warnings from Starlette/TestClient and Nautilus pandas Timestamp.utcnow only; no test failures.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -NoBrowser passed against the existing healthy127.0.0.1:8765 service; it reused the service and verified workspace identity. Fresh-launch subprocess behavior and browser visual/interaction inspection are being tested by root. This report does not claim those pending checks passed.

## Setup and opening
From repository root: uv sync --frozen; npm --prefix frontend ci --cache .cache/npm; npm --prefix frontend run build. Then double-click Launch Frontier.cmd. Existing frontend/dist is served offline at http://127.0.0.1:8765. Main control names: Study, Data, Experiments, Operations; Dataset; Strategy; Run study; Compare baselines; Import dataset; Open report. Width behavior is defined for390/768/1024 and wide desktop; root should inspect screenshots at each.
