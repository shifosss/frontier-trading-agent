# Standard code-quality review

Scope: the completed local release at `674c02d`, reviewed on September 18, 2026.
The objective is easier maintenance and less duplication, with unchanged financial
results, data contracts, saved evidence and user-facing workflows.

## Requested plugin

The user supplied [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)
after directory discovery found no installed copy. The official source was checked
out locally at `e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156` (version 4.10.0).
Its [full-mode skill](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/skills/ponytail/SKILL.md),
[diff review](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/skills/ponytail-review/SKILL.md),
and [repository audit](https://github.com/DietrichGebert/ponytail/blob/e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156/skills/ponytail-audit/SKILL.md)
were read and applied directly in this session. This is source-loaded skill use;
no global plugin installation or automatic lifecycle-hook activation is claimed.
No application dependency was added.

Independent backend and frontend reviews selected the cleanup. A separate final
reviewer traced the completed diff and its callers, finding no actionable issues.
Ponytail's final complexity passes identified no further worthwhile cuts: retained
checks and provider process controls serve tested requirements. Correctness was
reviewed separately from Ponytail's complexity-only review.

## Accepted changes and rationale

| Change | Why it is useful | Preserved behavior |
| --- | --- | --- |
| One shared strategy signal calculation | Replay and observation had separate implementations; a passive warmup discrepancy had already needed a fix. | Same Pandas mean, warmup, reasons and capped weights; callers retain their timing/rebalance ownership. |
| One web engine-job context | Three routes repeated locking, busy errors and exception cleanup. | Nonblocking busy response, error detail and guaranteed lock release. |
| Accurate volatility variable name | A standard deviation was named `variance`, obscuring the units used by Sharpe and annualization. | Formulas and report field names unchanged. |
| Resolve Node once during CLI discovery | The same executable lookup repeated for every PATH directory. | Existing Codex CLI discovery and subprocess behavior. |
| Named UI actions and page metadata | Repeated handlers and parallel navigation structures needed synchronized edits. | Same notices, saved settings, state ownership and navigation. |
| Stateless display components and shared dataset types | Large page modules mixed orchestration with chart/table/proposal rendering. | Same markup, formatting and API data; no new framework or runtime validation layer. |
| Consolidated responsive CSS | Later declarations always overrode earlier values at the same breakpoint. | Effective desktop/mobile styles unchanged. |

The review found no clearly unused CSS selectors; none are removed speculatively.
Locale percentage formatting and fixed-decimal research formatting remain distinct.
Windows provider process ownership, data-integrity checks and accounting invariants
are retained because existing regressions demonstrate why they are needed.

## Size and maintenance tradeoff

| Frontend module | Before | After |
| --- | ---: | ---: |
| `main.tsx` | 1,401 | 1,248 |
| `ResearchPanel.tsx` | 693 | 544 |
| `style.css` | 1,475 | 1,462 |

The two orchestration modules shrink by 302 lines. Across the frontend, total
source grows from 3,569 to 3,626 lines (+57): explicit display/data contracts and
navigation metadata replace implicit assumptions and parallel definitions. The
extracted renderers retain their markup and actual callers. This is a readability
tradeoff, not a claim of net code reduction. No framework, router, generic state
layer or new dependency was introduced.

## Validation

- `scripts/verify.ps1`: **92 tests passed in 60.84 seconds**, Ruff passed, TypeScript
  and the production build passed. The 82 existing upstream deprecation warnings
  remain visible.
- **23/23 retained replays are exactly equivalent** across configuration, dataset,
  metrics, complete equity curves, decisions, fills, positions, native balances,
  engine identity, exposure drift and unfilled intents. Code identity necessarily
  changes because the implementation changed; the new shared signal source is
  included in its hash and covered by a regression.
- All five pages at 1440px and 390px have identical pre/post text and screenshot
  bytes after waiting for the saved-research loading state to finish. No page
  errors or horizontal overflow were observed. Evidence:
  `artifacts/quality-ui-comparison.json` and `.qualification/quality-ui-{before,after}`.
- The independent reviewer also compared compiled bodies of `Download`, `Table`
  and `EquityChart`: all are unchanged. Responsive CSS was checked at both affected
  breakpoints.

The actual Chrome workflow check passed against the restarted service and built
frontend: demo import and its notice, opt-in persistence across Study/Research and
reload, study execution, exact saved-setting rerun, complete JSON download equality,
Experiments open, model-attempt replay inspection, earlier-version rerun, freeze and
idempotent historical observation. All five pages passed desktop/mobile navigation
with no page errors or failed HTTP responses. Evidence:
`artifacts/quality-browser-validation.json`. The historical observation remains
`historical_only`; no model calls, broker orders or inferred performance were added.

The initial browser harness needed selector/readiness corrections (the selected
dataset resets on reload, notices include a dismiss button, and research loads
asynchronously). The final assertions verify those actual behaviors; no application
change was needed to make the harness pass.

Saved pre-cleanup evidence: `artifacts/quality-review-baseline.json`, containing
23 runs across both daily tournaments and the hourly lane. Differential validation
compares full decisions, fills, equity curves, native balances, metrics and metadata,
not only a headline return. No new model proposals or market-data fetches were needed for this check.
Comparison results: `artifacts/quality-equivalence.json`. Financial code identity:
`sha256:0cac892e09591b334c0d0bc2ed865630c660a20cdddfc1e20b41a90849896464`.

Normal development still requires restarting the local service after Python changes;
the launcher deliberately reuses a running service rather than hot-reloading code.


## Scanner and dividend milestone — September 18, 2026

The same requested Ponytail **full/standard** skill was applied after implementation.
The source adapter and fixed scanner remain two ordinary Python modules, using
existing pandas/httpx/calendar dependencies and a bounded standard-library thread
pool. The interface adds one screen to the existing React state/navigation and API
job lock. No plugin framework, generic provider factory, new product dependency,
custom scheduler or broker abstraction was added. The Codex heartbeat handles the
requested recurring research scan; its state is app-owned, not hand-written cron.

The narrow dividend module relies on engine positions and native cash mutation;
it does not synthesize income as trades or replace the execution ledger. Dataset
imports accept an optional payment timestamp while preserving old source identities.
Financial input checks remain because they prevent demonstrated wrong accounting
or mislabeled evidence, rather than providing speculative fallback behavior.

Independent reviews identified and closed four concrete issues:

| Finding | Resolution and evidence |
| --- | --- |
| Provider metadata could name another symbol | Require matching symbol and currency; regression rejects mismatches. |
| Exact replay ignored dividend ledger/receivables | Compare both fields; a tampered ledger/receivable now fails verification. |
| USD0 generated misleading zero-return cohorts | Unfunded currencies have zero cohorts, null means, explicit reason and UI copy. |
| Missing stock histories looked like valid cash decisions | Exclude incomplete declared-universe cohorts; expose coverage/counts. Adequate no-signal histories still count as cash. |

Profiling the retained five-year capture found repeated whole-frame filtering.
Grouping history once by symbol and reusing each calendar lookback reduced comparable
profiled time from 139.94s to 48.66s. The latest scan, all 238 CAD cohorts and their
original summary fields were exactly unchanged. Coverage correction also leaves
this fully covered capture unchanged; current reference data and real capture IDs
remain separate from that before/after comparison.

Final verification: **114 tests passed in 79.04s**, Ruff passed, TypeScript and Vite
production build passed. The 96 upstream deprecation warnings remain visible.
The repaired historical replay is exactly identical across all 14 compared fields;
source enrichment preserves original raw bars byte for byte and original FX rows.
Current artifact/code IDs are in [the completed study](scanner-study.md).

Actual Chrome checks exercised the new scan button against the real service and
public data (41/41 captures), saved-history selection and exact JSON download.
All six pages passed at 1440, 768, 390 and 320 pixels: 24 page/width combinations,
no page errors, no failed HTTP responses, no horizontal overflow. The repaired
study deep link and Assumptions-tab dividend income display passed. The desktop
scanner screenshot was also visually inspected. Evidence:
`artifacts/scanner-browser-validation.json` and `.qualification/scanner-real-validation`.

The browser harness initially used a label selector where a combobox role selector
was needed, then looked for dividend text outside the Assumptions tab. These were
harness corrections; the final pass inspected the actual saved scan without another
unnecessary data fetch. This is distinct from the earlier mocked UI contract smoke
check in `.qualification/scanner-ui-smoke`.

The project Python environment was not changed for browser tooling. The verification
harness uses a workspace-local uv cache with Playwright/greenlet and the installed
Chrome executable. No global plugin, machine service, paid data or brokerage action
was installed or executed.


## Planned USD funding follow-up — September 18, 2026

The user now accepts CAD-to-USD funding for US trading. One narrow helper reuses the
existing public FX capture and Decimal; it deducts the CAD amount once, applies the
published whole-transaction conversion-fee tier and credits USD once. Existing cash
and old saved artifacts keep their behavior. No product dependency was added.

Independent review verified post-conversion cash propagation and saved-input restore.
It found that CLI summary output omitted the diagnostic's native-currency/FX-cost
limitations; the CLI now includes them. Historical split-adjusted share prices are
also explicitly identified as unsuitable evidence of pre-split whole-share
tradability. The strategy was not retuned to manufacture a funded entry.

Final checks: **132 tests passed in 80.37s**, Ruff/TypeScript/build passed, and the
actual conversion form/API/download/saved-history/reload flow passed in Chrome.
Four screen widths had no page/HTTP errors or horizontal overflow. Current IDs,
reference assumptions and financial results are in [USD funding study](usd-funding-study.md).


## Automated paper operator — September 18, 2026

Applied the previously source-loaded Ponytail skill at full (standard) level. Reused
httpx, exchange calendars, captured scanner features, SQLite and native process locks;
no new dependency or abstraction framework was introduced. The paper broker owns
cash, holdings and fills. The separate journal records evidence and checks known
cash/share changes; it does not replace Nautilus or invent a second execution engine.

Two independent reviews found and resolved: incorrect settlement on bank-only
holidays; a reopened holding inheriting old age; non-atomic plan/peak persistence;
incomplete captures consuming a session's only decision; entry prices masquerading
as completed-close peaks; fills later than request-start being rejected as future;
stale gross exposure between immediately filled orders; rejected exits appearing
healthy; cross-endpoint market marks causing false reconciliation failures; and one
working exit blocking risk exits in other holdings. Each consequential counterexample
has a regression check. Paused decisions also say wait when their buy intents are removed.

Final full verification: **196 tests passed in 99.23 seconds**, Ruff passed, and
TypeScript/Vite production build passed. The 96 warnings are existing upstream
Starlette/AnyIO and Nautilus/pandas deprecations. Independent reviewers rechecked
closure of their last findings. Paper HTTP tests use MockTransport, operating tests
use an explicit broker double, and no broker credentials or accounts were accessed.
The Windows launcher passed PowerShell syntax parsing; actual daemon/broker startup
remains unqualified until a dedicated paper account is configured locally.

Five UI states were checked at 1440, 768, 390 and 320 pixels using mocked status responses;
the actual local endpoint was then checked separately. Evidence lives under
`.qualification/operator-ui-smoke` and `.qualification/operator-ui-actual`. Public
product claims and remaining deployment gates are in [the updated plan](automated-trading-plan.md).


## Windows paper credential setup — September 18, 2026

A real read-only probe established that both configured Windows User variables exist,
but the Codex command process retained an older environment. The broker now reads
that exact User-variable pair when both process values are absent. A partial process
pair is rejected rather than combined with registry credentials. The Windows launcher
uses the same resolver through client construction, without making an API request.
CLI tracebacks no longer render local variables, so incomplete credential setup cannot
print a key through Typer's exception renderer. No credentials are written to artifacts.

Validation: **47 targeted broker/operator/CLI tests passed in 14.79 seconds**, Ruff
passed, and independent review found no remaining issue in this patch. Tests use a
fake Windows registry, and a dummy partial credential pair exercises the real CLI
failure path. A separate real paper GET snapshot then authenticated successfully
through the application resolver with both process variables absent: ACTIVE, USD,
US$100,000 simulated cash, no holdings and no open orders. Account validation passed;
no initialization, order submission, account reset or runner activation occurred.
The local connection-status update followed a verified SQLite backup and integrity
check. Sanitized probe evidence is saved in `artifacts/paper-operator/connection-check.json`.
