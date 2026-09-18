# Task 4: Local research workstation

## Contract and ownership
Implement after Task3 interfaces are stable. Read docs/tasks/02-data-evidence-report.md and03-replay-report.md and actual backend interfaces. Own src/frontier/web.py, frontend/, scripts/start.ps1, Launch Frontier.cmd, tests/test_web.py, docs/interface-design.md, docs/tasks/04-interface-report.md. Add only serve command integration to cli.py in coordination with root. No subagents. User authorized routine build/test; no external hosting/spending.

## User outcome
Double-click Launch Frontier.cmd to open a usable local research workbench at127.0.0.1. First launch imports the deterministic engineering demo if no datasets exist, then shows clear next actions. Existing real snapshots remain separate. Do not launch any order/broker flow. Title: Frontier Research. Use Python FastAPI serving locally built React/TypeScript/Vite static assets from the same origin. No CDN/font/API dependency for offline use. Lock npm dependencies; use local npm cache, no global installation.

## Design
Apply frontend-design skill (read it). Plan short tokens/wireframe in docs/interface-design.md and self-critique before code. Direction: a precise blue-and-white analytical workstation, left rail, one broad chart canvas plus a compact aligned study form, quiet contextual warnings. Palette paper#F7FAFD, white#FFFFFF, ink#18324B, blue#245BD3, teal#167D8D, amber#9A5A12. Typography Aptos/Segoe UI or locally available sans, strong numerical alignment, readable minimum sizes. Do not imitate a dark crypto terminal, marketing page, identical card grid, or fake live feed. Use color for series/state, not decoration. Sentence case, plain labels, focus rings, keyboard usability, responsive1024/768/390width, reduced motion. Main navigation Study/Data/Experiments/Operations.

## Backend
create_app(workspace:Path)->FastAPI, tests use TestClient and temporary workspace. Build a small synchronous API, a single coordinator lock serializes engine jobs; use normal sync handlers so status endpoints remain responsive. Every real study writes registry before engine; failed jobs persist and are shown with actual errors. No fake spinner response or hardcoded charts.
- GET /api/status: engine/runtime identities, workspace, dataset/run counts, capability flags/current unsupported actions/hourly qualification, data timestamps.
- GET /api/datasets and GET /api/datasets/{id}: real manifest and data preview.
- POST /api/demo: idempotent import synthetic fixture (not rerun every launch).
- POST /api/import: source-directory path or uploaded JSON/CSV source files; choose safe simplest local flow. Source directory import clearly explains required files; upload optional.
- GET /api/runs, GET /api/runs/{id}: record+artifact data; report endpoint serves only registry-owned HTML path validated inside artifact_root.
- POST /api/runs: RunConfig; real replay, actual result.
- POST /api/campaigns: fixed declared tournament, actual results/IDs and trial counts.
- Static route after API routes; unknown API404 JSON, do not return index.html.
- Bind127.0.0.1 only; reject cross-origin mutation requests and unexpected Host headers. This local no-auth service may import files/run jobs, so malicious webpages must not be allowed to operate it. Don't add public deployment/auth complexity.

## UX flows
Study: dataset select shows country,currency,date span,row count, synthetic/historical label. Initial profileUSD10k/CAD10k,20%max group, long-only, whole shares. Costs visible before Run. Choose strategy and lookback or Compare baselines. Advanced collapsible fields. If source actions unknown, clear opt-in explaining distributions omitted and result not total return. Known corporate actions: show precise unsupported error; no "ignore actions" override.
Results: actual equity plot with currency/units/dates, baseline comparison normalizes initial NAV only when necessary, inspect drawdown/return/fees/fills/exposure plus plain assumptions. Empty/cash run chart and zero-trade state must be legible. Missing metric displays "Not enough observations"; no fabricated zero/Sharpe. Mark exploratory tournament; never call best historical variant proven winner.
Decision replay: select instrument/decision/time, inspect permitted input time, signal, target, reason, next execution, actual fills. Tables scroll and show native fee currency. Download report/config/result.
Data: provenance, coverage, action status, calendar and FX basis, import instructions+source folder field, last observation date vs fetched date. Never write "live" for snapshots.
Experiments: sortable actual runs, failed entries expandable, compare selected runs with common inputs/cost differences visible. Full trial counts on campaign.
Operations: verified capability checklist, current service state, latest jobs/errors. Unsupported broker/hourly/features state truthfully. No decorative disabled controls pretending to exist.
Loading, error and success feedback accurately follow completed requests. Large jobs button disabled while running, error contains correction hint.

## Launch
scripts/start.ps1 checks project.venv and frontend build, provides actionable setup error (may uv sync --frozen/npm ci only if missing with existing free tooling), starts server hidden and opens browser only when health passes. Root will test actual subprocess path. Script path quoting handles apostrophe/spaces; never assumes admin. Launch Frontier.cmd invokes PowerShell with project-relative script. Don't modify Windows startup, global config, scheduled tasks, firewall.
For easiest repeat use: documented one command install + doubleclick. Doctor identifies missing setup/capabilities.

## Acceptance
Build actual React app npm run build and typecheck. API tests: demo/list/run/result/report, failed action run retained, import traversal/report path, host/origin mutation rejection, unknown API404. Root will perform real browser interaction and inspect screenshots; leave server command and selector/control labels. Test fixture results expected from backend, no hardcoded dashboard metrics. Report exact build/test commands, current app URL, remaining gaps.


## UX review decisions

Keep the previous result visible when changing form parameters. Start with passive and20-session lookback for rules that use it; hide lookback for cash/passive. Persist exploratory opt-in per dataset version in the browser rather than prompting every run. Use exact per-order commission from RunConfig, not a new incompatible basis-points fee preset. Evidence labels stay next to dataset and result names. Keyboard shortcutCtrl+Enter may run a study. Unsupported capability errors preserve form values and name a correction.
