# Validated local release

Verified September 18, 2026 on the configured Windows host. This is a working
research workstation. The broader state-of-the-art and broker-operation goals
remain subject to the acceptance criteria in [the roadmap](roadmap.md).

The latest [planned USD funding follow-up](usd-funding-study.md) passed **132 tests**,
lint/build and the real conversion-preview browser workflow.

The preceding [scanner and dividend milestone](scanner-study.md) passed **114 tests**,
Ruff, TypeScript/build, exact dividend replay and real desktop/mobile browser checks.
Its current evidence is recorded in the [quality-review update](code-quality-review.md#scanner-and-dividend-milestone--september-18-2026).

The historical sections below record the initial release at `674c02d`. The subsequent
[Ponytail full-mode quality review](code-quality-review.md) passed 92 tests,
23 exact financial-result comparisons, and desktop/mobile browser checks.
That report records the new code identity; the original evidence below is retained.

## Automated checks

`./scripts/verify.ps1` completed successfully:

- **88 tests passed** in 70.44 seconds against the actual installed engine.
- Ruff passed for `src`, `tests`, and `scripts`.
- TypeScript and the production Vite build passed.
- `uv pip check --python .venv/Scripts/python.exe` checked 47 compatible packages.
- The installed `frontier doctor` entrypoint reports Python 3.13, Frontier 0.1.0,
  and Nautilus Trader 1.231.0.

The test suite covers source-to-Parquet integrity, source timing and calendars,
USD/CAD cash and fees, an independent hand-accounting oracle, missing FX,
future-data mutation invariance, hourly execution timing, opening gaps, exposure
groups, known-action rejection, deterministic replay, retained failures, model
budgets and feedback, provider process cleanup, immutable observation chronology,
CLI workflows, and loopback API behavior. Model protocol tests use explicit test
providers; the live model evidence below is separate.

Upstream Nautilus/Pandas and Starlette test-client deprecations remain visible.
They are warnings, not suppressed failures. No Linux/macOS CI or broker-paper
execution has been run.

## Final replay evidence

`artifacts/final-validation.json` records exact run IDs, native accounting,
reproduction comparisons and code identity. Final financial identity:
`sha256:91216c61dc185c2136bb431a504c2259a840134486df40a6031ed86de8767eda`.

| Lane | Saved run | Fills | Exact replay | Interpretation |
| --- | --- | ---: | --- | --- |
| Fictional US/Canada fixture | `50402e705552443390aea0944b8da596` | 38 | Passed | Engineering only |
| Retained SPY/XIU daily window | `f14f9097667e4b6ebccc0cceb210ca7b` | 7 | Passed | Exploratory raw-price |
| Retained SPY hourly window | `6b1d370bed7d433f8bfec497004a0c8b` | 17 | Passed | Exploratory raw-price |

Both final daily tournaments completed all 11 declared trials: fixture campaign
`bb518c360ac044778b6151792fd3f518` and historical campaign
`8c359b0eef074f018b613b57905b8655`. Each has a frozen candidate list and saved results.
The full historical source includes a known dividend and was durably rejected;
the separate shorter window starts flat after its ex-date. Unknown action coverage
remains unknown, and historical `total_return` remains null.

Every final lane's per-market contributions sum to its native currency P&L. This
check exposed and corrected an earlier netting-position attribution defect.
Engine cash and portfolio NAV did not depend on that attribution calculation.
The four-round-trip rounding regression independently gives USD 997.36 final cash
and -2.64 P&L. Reports also preserve fixed slippage, dated indicative FX, inferred
opening quotes, incomplete actions, and reused evaluation-period limitations.

## Actual model and data access

Two real two-call Codex campaigns used the existing ChatGPT login, with typed
proposals and actual first-run metrics included in each second prompt:

- Fixture: `artifacts/model-campaigns/25342cad16ea475fbc7e6fe791274400/campaign.json`.
- Historical: `artifacts/model-campaigns/787940fbcd694c7194724efd76324925/campaign.json`.

All four proposals produced engine runs. Provider prompts, outputs, token counts,
versions and elapsed time are retained. The historical attempts returned negative
raw-price results; they are preserved without a profitability or independent-test
claim. `final-validation.json` links new deterministic reruns under the final code
to the original attempts. No extra model calls were needed for those reruns.

Actual session connector evidence includes Alpha Vantage daily SPY/XIU, Longbridge
434 regular-session SPY hourly bars, and Alpaca hourly/action responses. BoC public
FX fetching and verified cache reuse were tested. Standalone Longbridge auth is
expired; no login or brokerage mutation was performed. See
[existing connector access](existing-connectors.md) for precise boundaries.

## Frozen observations and interface

A historical SPY/XIU prefix through September 16 was frozen today, then evaluated
with the retained September 17 extension. Observation
`8c09603fd555874df3871296c98de3fad1075a5192ee98e89a88b00196406147`
is correctly **historical_only**, with no inferred fill or performance outcome.
Repeating the request returns the identical record. No historical record was
backdated into prospective evidence.

The launcher was tested from a stopped service, including the workspace path's
spaces and apostrophe. It starts a hidden loopback service at
`http://127.0.0.1:8765`; reuse was also verified. Browser tests used actual Chrome
and the served production build, with real HTTP and engine work:

- Run a study, rerun its exact saved configuration, and inspect actual fills.
- Freeze a completed run, inspect the saved real-model campaigns and usage,
  and record the existing historical observation through the interface.
- Navigate Study, Data, Research, Experiments and Operations at 1440px and 390px.
- No page errors, failed HTTP requests or horizontal page overflow.

Evidence: `artifacts/browser-validation.json`; locally inspected desktop/mobile
screenshots are under `.qualification/frontier-*.png`. API integration separately
exercises campaign creation with an explicit test provider, actual replay,
rejected budgets/concurrency, artifact reload after app recreation and observation
errors. Browser verification did not consume more real model calls.

## Independent review and remaining work

Independent code review closed source-integrity, provider child-process timeout,
observation timing/provenance, passive warmup and market-attribution findings.
Corrections have regression coverage. Code identity survives LF/CRLF checkout changes,
and observation identity binds source history and implementation. Earlier artifacts remain immutable and are
identified as earlier versions; rerunning saved settings creates new evidence.

Corporate-action accounting, complete Canadian action/history and hourly data,
longer point-in-time universes, nested chronological model evaluation, untouched
holdouts, advanced model comparisons, actual prospective outcomes and broker
reconciliation are not complete. A model's ability to propose a strategy does not
establish an investment edge. No perpetual scheduler, live account or paid service
was configured.
