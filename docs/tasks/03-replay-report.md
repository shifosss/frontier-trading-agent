# Task 3 executable replay and campaigns report

Completed 2026-09-18. All execution is local research; no broker orders, new spending,
or global configuration changes.

## Implemented behavior

- Actual pinned Nautilus Trader 1.231.0 owns orders, fills, positions and native
  USD/CAD cash. One consolidated RESEARCH simulated venue and exactly one cash
  account are funded once. Original listing IDs are retained in results, and
  original exchange calendars determine openings. Engine-only internal IDs map
  listings into the shared account; no capital is duplicated across venues.
- NativeFeeModel returns commission in each actual instrument quote currency.
  Orders are whole-share, long-only, unlevered and constrained by actual available
  native cash after fees. There are no automatic FX conversion trades.
- Daily and hourly features use latest as-of revisions with event and available
  times no later than the decision. Close decisions execute only at a strictly
  later eligible observed bar opening. Same-time availability cannot execute at
  that opening. Pending terminal intents remain unfilled; no terminal liquidation.
- Opening OHLC values are explicitly reconstructed synthetic bid/ask quotes with
  fixed slippage and deep synthetic size. They are not observed market quotes and
  do not model volume impact. Revisions do not replace earlier opening prices.
- Combined-NAV exposure-group targets are at most20%, divided among interlisted
  members, and constrained by cash. Existing holdings can drift; drift is retained.
  Gap-down sizing uses the greater of opening ask and last observed close to avoid
  overallocating close-marked NAV. State marks use actually available close prices.
- FX comes from the latest dated rate whose publication is already available;
  no missing-rate fallback. Missing prior FX fails with an actionable error.
- Known actions fail closed. Unknown coverage requires explicit opt-in and returns
  total_return=null plus separately named raw_price_return and prominent limitations.
- All requested frozen result keys are implemented. Extra fields include separate
  slippage, raw-price NAV return, unfilled intents, exposure drift, native currency
  contribution and original-market attribution. The final review correction below supersedes the initial Position P&L attribution.
- Daily-sampled volatility/Sharpe require nonzero variance. The seeded circular
  block bootstrap reports a descriptive95% interval with500 resamples and blocks
  up to5 daily returns. There is no significance/promotion threshold.
- RUNNING is committed before execution, every failure becomes FAILED, and completed
  results/reports live under artifacts/RUN_ID. Evaluation accesses are persisted
  globally within each immutable dataset identity, including verification accesses.
- Deterministic default tournament freezes11 candidates before evaluation: cash,
  passive, trend/reversion with lookbacks10/20/40, and passive/trend/reversion with
  doubled fixed commission/slippage. Normal funding is USD10,000/CAD10,000;
  normal costs are1 native unit/order and5bps. All failed attempts are retained.
- Candidate artifacts include exact configurations, dataset identity/manifest,
  code identity and frozen_at. Code identity covers domain/data/store/fixtures/
  replay/metrics/campaign/reports plus uv.lock, excluding unrelated provider/UI
  changes. Verification rejects financial-code drift and directly compares all
  financial/decision content, excluding registry UUIDs/runtime and evaluation-access
  history. No autonomous LLM research, untouched holdout or walk-forward claim.
- CLI supports doctor, demo, datasets, import, run, campaign, runs, show,
  verify-replay and serve. serve delegates to frontier.web.serve(workspace,port).
  Reports are escaped, standalone local HTML with the same results plus full
  configuration, source manifest, evaluation exposure, drift and pending intents.

## Exact retained source imports

Run `.venv/Scripts/python.exe scripts/import_session_snapshots.py` from the repository.

- Full200-bar SPY+XIU source identity:
  f31316b05cdfd12ab3a93b136cea3fa805858000631de518f4f1b94263e5f833.
  It includes known SPY June18 dividend, and replay is durably rejected even with
  incomplete-action opt-in. Source is not silently converted into an action-free run.
- Separate June22–September17 window,123 bars:
  3c041e7b3772e7662ec019cf4fb4101e2020695169dd7f6164e54d3431259e5a.
  This starts flat after the known June18 ex-date; July31 payment does not create
  an inherited receivable. Unknown Canadian action coverage remains explicit.
- Source metadata, original symbol/provider names and date bounds, URLs, raw-file
  digests and FX provenance are preserved in immutable imported metadata. The
  original raw JSON files remain under data/raw. Imported source CSV/JSON files are
  also retained by the immutable foundation. Retrieval date is known; the exact
  time is unrecorded and explicitly described. Availability is inferred, never
  presented as observed point-in-time data.
- BoC publication is modeled at16:30 America/Toronto with DST. Original prior FX
  rows are kept. No invented history or hourly data was added.

## Actual verification and artifacts

Focused command:

```powershell
& '.venv/Scripts/python.exe' -m pytest -q tests/test_replay.py tests/test_campaign.py tests/test_cli.py
& '.venv/Scripts/ruff.exe' check src/frontier/replay.py src/frontier/metrics.py src/frontier/campaign.py src/frontier/reports.py src/frontier/cli.py scripts/import_session_snapshots.py tests/test_replay.py tests/test_campaign.py tests/test_cli.py
```

Result:14 tests pass against the actual engine; Ruff passes. Actual independent
hand-accounting case funds USD1,000+CAD1,000 at1.25USD/CAD: initial CAD NAV2,250;
buys3USD shares and4CAD shares at100 with1 native fee each; final cash USD699/CAD599,
NAV2,247.75. Every curve point reconstructs from native cash/positions and dated FX.
Tests also cover single-account funding, strict equal-time exclusion, daily/hourly
next openings, shared exposure groups, zero CAD funding, missing FX, holiday mismatch,
future price/revision/FX mutation invariance, gap-down allocation, separate actual
slippage, cash zero-variance metrics, split/dividend refusal, durable failed records,
repeat equality, persisted CLI reports and complete failed campaign retention.
The engine emits upstream pandas Timestamp.utcnow deprecation warnings; tests pass.

Final consolidated evidence: artifacts/task3-validation.json.

- Synthetic run73c42b32781749f8bea68e10bd3a2c8c:
  artifacts/73c42b32781749f8bea68e10bd3a2c8c/result.json and report.html.
- Synthetic campaign071000bd685e46d0956072447721245e:11/11 completed.
- Real exploratory run7f25b48b9add4428ad538516071e2c6f:
  artifacts/7f25b48b9add4428ad538516071e2c6f/result.json and report.html.
  Seven genuine fills; raw-price NAV return0.004106935708080073; total_return=null.
- Real campaign5c62ecf3bece4fdfb94a586932b77970:11/11 completed.
- Each campaign directory contains frozen_candidates.json and campaign.json.
- Both representative final runs passed exact financial/decision replay verification.
  Subsequent financial-source or dependency-lock changes intentionally require new
  frozen studies; old immutable runs remain inspectable.

Reproduce the real run and verify the resulting run ID:

```powershell
& '.venv/Scripts/python.exe' -m frontier.cli run 3c041e7b3772e7662ec019cf4fb4101e2020695169dd7f6164e54d3431259e5a --strategy passive --allow-incomplete-actions
& '.venv/Scripts/python.exe' -m frontier.cli verify-replay RUN_ID
& '.venv/Scripts/python.exe' -m frontier.cli campaign 3c041e7b3772e7662ec019cf4fb4101e2020695169dd7f6164e54d3431259e5a --allow-incomplete-actions
```

## Boundaries

Corporate actions remain unqualified; historical opening quotes and availability
are inferred. Small-sample, reused-interval results are exploratory only. Registry
access overlap does not detect different dataset vintages/provider aliases. There
is no calibrated spread/impact, cash interest, financing, dividend entitlement,
qualified corporate-action accounting, live execution or automatic promotion.
CLI and HTML are local inspection surfaces, and no market-performance promise is made.


## Final integration correction

The real hourly run exposed missing earlier netting lifecycles in `cache.positions()`.
Final attribution now sums every actual engine fill, using engine `notional_value`
Money rounding and native commission, then adds final holdings at observed close
marks. It does not replace engine order execution or cash accounting. A hand oracle
with four one-share round trips at 100.1234 / 101.4567 verifies final USD cash 997.36
and P&L -2.64, and market totals reconcile to native currency contribution.

[Consolidated validation](../validation.md) and `artifacts/final-validation.json`
supersede the intermediate run IDs above for the final research-code identity.
Older immutable records remain visible and are marked as earlier versions in the app.
