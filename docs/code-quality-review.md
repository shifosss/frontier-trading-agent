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


## Authorized paper activation - September 18, 2026

The owner chose the existing US$100,000 simulated balance. A SQLite backup passed
its integrity check before initialization. The actual paper account matched its
pinned ID, ACTIVE status, USD cash and empty holdings/orders. Initialization and
the first real reconciliation passed. The hidden five-minute worker then recorded
a successful independent cycle, with no stderr output; its executable and command
line matched this workspace. The initialized code identity matched the current
source. Activation evidence is local under `artifacts/paper-operator/`. These are
startup and reconciliation observations, not an order-fill trial or evidence of
profitability. No execution code or frozen policy changed during activation.


## Broad research and durable workers - September 18, 2026

Applied source-loaded Ponytail full/standard and independent correctness review.
Discovery uses official listing files and the standard library XLSX reader; no
new runtime dependency, agent framework or order adapter was added. Historical
and prospective cohorts share cash/cost arithmetic. Existing normalization,
calendars, HTTP handling and UI primitives are reused. The redundant derived-data
cache was removed after review reproduced a completion-cutoff collision. Raw
sources are hash-checked and normalized at their recorded availability.

Review also fixed source-version pinning across long captures, reused-PID status
confusion (SQLite ownership is authoritative), saved prospective-plan tampering,
and interrupted snapshot publication. Full-payload validation and exclusive atomic
publication preserve those plans. Windows subprocess checks explicitly decode
UTF-8. Research remains isolated from the frozen paper journal and financial files.

A measured 0.187-second single-name normalization bottleneck justified four bounded
standard-library process workers for broad captures. A 100-history comparison took
3.627 seconds and three sampled outputs exactly matched serial normalization.
Both the web and paper launchers now return while their workers continue, and
later scheduled paper observations verified survival. Repeated launches reuse the
existing worker; old log bytes are retained.

Final scripts/verify.ps1: **231 tests passed in 92.57 seconds**, Ruff passed, and
TypeScript/Vite build passed. The 96 warnings are existing upstream deprecations.
Strategy lab mock and actual browser evidence is under
`.qualification/broad-research-ui/`; four widths had no errors or horizontal
overflow. Independent final source review reported no remaining material findings.
The [first broad study](broad-research-results.md) records actual coverage and
research findings separately from software validation and paper-account results.

Final completed-study browser checks matched 16 currency/budget/horizon/cost views
against the real saved API, with all four strategy families visible. Full and
forward downloads returned 11,840 historical cohorts and 96 pending plans. Evidence:
`.qualification/broad-research-ui/completed-actual-report.json`.


## Historical-first expansion - September 18, 2026

Ponytail full/standard and independent financial correctness review were applied. The new historical path reuses existing HTTP, calendars, numerical tools, UI tables/charts and durable launcher; no dependency or broker adapter was added. Source collection, job orchestration and portfolio simulation have separate responsibilities. Large audit JSON is streamed to disk, while the UI receives a separately saved compact summary and monthly chart samples.

Reviews found and fixed: a callback-signature mismatch, omitted CAD benchmarks/instrument audit records when combining books, pre-2017 cash settlement assumptions, settlement across annual folds, invalidating zero-filled holdings for missing future marks, treating an unknown market regime as bearish cash, and relabeling already-loaded orchestration with newly edited source. Final loaded-code regression verifies publication stops while raw data remains reusable. Historical price reconstruction was independently checked against Longbridge's January 2000 AAPL quotes, and calendar optimization retained exact output on sampled histories.

The final full project suite passed **262 tests in 116.40 seconds**, Ruff and TypeScript/Vite build. A separate targeted run passed **35 historical/discovery tests**, including the added provenance regression. Existing upstream deprecation warnings remain. Economic tests cover daily unrealized losses, fees, gap sizing, missing data, split continuity, settlement, rolling selection causality, recent-month exclusion, benchmark/cash comparisons and per-stock warmup. Browser checks and actual study findings are recorded separately from software correctness.


The first long run exposed a real Windows file-sharing failure while replacing a progress snapshot. A narrowly bounded PermissionError retry now preserves atomic replacement without hiding persistent write failures. Six orchestration regressions pass, including preservation of the old status until successful replacement. An independent real-kernel check held a destination without FILE_SHARE_DELETE for 120 ms; the writer completed correctly after 153 ms. Captured histories and the completed preliminary US report were retained, and both books were rerun under the final source identity. This is an observed runtime fix, not speculative exception handling.


The completed full-data audit independently compared all 792 portfolio/reference rows with their compact API representations, recomputed ending equity, total return and daily maximum drawdown for all 683 complete rows, and confirmed that all 109 incomplete rows retain null aggregate metrics. Sample USD and CAD trades were reconstructed from frozen raw sources with exact notional, fee and cash agreement. The saved financial source identity matches the implementation. Evidence: `.qualification/historical-source-probes/independent-final-reproducibility.json`.

The final report preserves the negative US findings and all incomplete Canadian attempts; see [extended historical study](historical-research-results.md). Browser review caught a full-period benchmark displayed beside an incomplete Canadian path. The interface now suppresses that comparison for incomplete accounts, labels the usable prefix and identifies missing held prices. The archived financial results remain unchanged.


Completed-study Chrome verification passed 48 real currency/budget/cost views against saved API values. The incomplete CAD warning, exact missing dates and partial chart were checked at 1440, 768, 390 and 320 pixels; its full-period benchmark is absent, while complete US comparisons remain available. There were no JavaScript errors, page overflow or mutating API calls. A one-byte ranged download returned HTTP 206 with the correct filename and 503,091,620-byte total. Desktop/mobile screenshots were visually inspected. Final TypeScript/Vite build passed. Evidence: `.qualification/historical-ui/actual-report.json` and `actual-incomplete-report.json`.


The separate Wajax issuer-data sensitivity was also independently audited. Exactly three absent rows were added; all original observations, the base report, main latest pointer and frozen model remained unchanged. All 396 sensitivity rows match their compact summary, and all 321 complete results reproduce ending equity, return and daily drawdown. The 75 incomplete rows retain null aggregate metrics. Two annual reports corroborate the 1:1 conversion, issuer quote HTML verifies HLCV, and the derived adjusted-close factor is explicit. Attempt 01's pre-evaluation timestamp-dtype assertion failure is retained; corrected attempt 02 and its source/script hashes are separately frozen. Evidence: `.qualification/historical-source-probes/independent-supplement-reproducibility.json`. No application dependency, production overlay, live trading action or favorable-result promotion was added.


## Daily short-hold study - September 18, 2026

Applied source-loaded Ponytail at full/standard and an independent financial correctness review. The new lane reuses feature/ranking, market calendars, legacy metric primitives, durable launch/publication and existing frontend components. No runtime dependency, broker route or general framework was added. Date-specific cash settlement is isolated in a small calendar helper. Large fixed-grid trade-event retention is avoided; full rolling events and deterministic single-view replay preserve targeted auditability.

Review caught a truncated reused source index that could silently reduce the stock universe. Reuse now checks the completed capture count and membership, and new definitions freeze and validate the index SHA256. Legacy captures without an original frozen index digest carry an explicit weaker-provenance label. Every raw history is still hash-verified. Archived artifacts and frozen paper modules remain unchanged.

Fresh `scripts/verify.ps1` passed **307 tests in 105.28 seconds**, Ruff and TypeScript/Vite build. Its 96 upstream deprecation warnings remain. Twelve independent randomized USD/CAD cases reconstructed **5,231 trades** and every daily cash, settled-cash and equity point within 1e-8. Tests cover idle-day rescreening, next-close entry, independent exits, gap sizing, settlement transitions/holidays, receivables across folds, missing marks and detailed-view replay. The real 13-name smoke completed 99 portfolio/reference paths in 24.68 seconds with 412 MB peak working set; its all-cash rolling choice is not an edge claim.

Synthetic browser checks covered 192 filter combinations across four viewport widths plus default/legacy launch, explicit saved-history reuse, old-result retention, completion publication, incomplete-metric masking and empty/error states. Actual full-run verification is recorded with the completed study report. Independent source review found no remaining material financial or maintainability issue.


Final completed short-hold run `90af4c840aad48f7ab58fba7a682f96a` passed independent reproduction of all 792 full/compact account/reference rows. All 24 rolling cash/settled/equity ledgers and 1,344 completed trades reconcile to immutable source prices and independently calculated settlement dates; all 8,234 raw hashes and frozen identities match. All 211 incomplete Canadian fixed portfolios retain null profitability aggregates. Actual browser checks passed 96 filter combinations across four widths, matched saved API values and verified a one-byte ranged download. A final frontend-only fix displays the actual running mode and stage while suppressing stale cumulative budget/date fields; the production build and four targeted status-state checks passed after that change. Evidence and limitations are in [the completed short-hold report](short-hold-research-results.md).


## September 19: learned-model expansion

Applied the locally retained Ponytail skill at full intensity: reused the existing market preparation, daily cash ledger, settlement and reporting; added focused feature/model/study modules instead of a second execution framework. Extracted forecast scoring, latest-candidate formatting and per-account fold evaluation to keep the study loop readable.

Implemented four fitted predictors (Ridge, ExtraTrees, HistGradientBoosting and shared-hidden six-output MLP), two forecast ensembles and a separate correlation-constrained variant. Model preprocessing is fitted only on earlier rows. Purged chronological calibration sets ensemble weights. Independent review corrected a small forecast fee-basis mismatch before economic evaluation and bounded detailed trade records to the declared 42-account subset.

Validation: full repository lint, 347 tests and TypeScript/Vite build passed. The 49 focused feature/model/engine checks passed. An independent comparison established exact previous-version equality for 360 ledger cases and 35,011 trades, default market preparation and complete retained study fixtures. A saved-data operational smoke verified 360 accounts, 12 references, 1,777 detailed trades and 3,554 fee legs; all accounting checks passed. Its six MLP convergence warnings remain recorded. No model was silently removed or tuned from the sample's performance.

Evidence under `.qualification/multi-model-review/`, `.qualification/multi-model-smoke/` and `.qualification/historical-ui/`. Browser checks cover legacy and multi-model filters, missing/incomplete/zero-trade states, calibration weights, forecasts and source-reuse controls. The historical worker additionally freezes dependency versions and manifest hashes. The frozen paper policy and journal are unchanged. Full-capture economic findings are reported separately.


### Completed multi-model capture and independent audit

Full run `814780d48b4141b9a82a3fb917d1b85a` completed on September 19 using the unchanged frozen financial identity. The independent audit passed exact full/compact equality for all 720 accounts and 24 references; verified all 8,234 raw files (2.934 GB) and the capture-index digest; reconstructed 4,463 instruments and all 42 retained daily account ledgers; and reconciled 192,113 completed trades, proportional fees, whole-share sizing, entry caps and dated settlement across annual folds. All 151 incomplete paths retain null profitability aggregates. Sampling digests and purge boundaries were checked; exact full feature-matrix sampling membership and completeness of provider corporate actions are outside that audit. Evidence: `.qualification/multi-model-review/full-audit-814780d48b4141b9a82a3fb917d1b85a.json`.

Actual completed-report browser verification passed 48 filter contexts at four widths, checking all 720 account rows at each width (2,880 row checks), references, trade and weekly/monthly metrics, missing-path masking, 23 CAD diagnostic windows and research forecasts. The review caught structured model warnings displayed as `[object Object]`; the frontend now renders the model, category and message and retains compatibility with older string warnings. Fresh TypeScript/Vite build and structured/legacy warning fixtures passed. No page errors, overflow or mutating API calls occurred. A one-byte HTTP range download verified the 691,108,930-byte result. Evidence: `.qualification/historical-ui/multi-model-actual-completed-report.json`.

A separate source-tail review found that an exceptional TPX-B.TO trade contributes 34% of one profitable Canadian account's net gain. The recorded price discontinuity is not economically qualified by the accounting pass. Primary SEC documents corroborate a nearby merger with share-exchange and cash terms; exact source/issuer mapping remains unresolved. The original capture and results remain intact. See [the results](multi-model-research-results.md) and [the source-continuity review](tpx-source-continuity.md). Historical market-data and quote probes also established existing-access paths for subsequent hourly and execution-cost work without changing this study's assumptions or the paper account.
