# Conditional strategy selection: follow-up design

**Execution request frozen; the historical study is running.** See [current study status](conditional-strategy-selection-results.md). Reuse frozen historical data and existing/free access. New forward observations are not a prerequisite. This asks a new economic question; it does not rerun the unchanged strategy grid or change the active paper policy. The working evidence is under `.qualification/conditional-selection20260928`.

## Question and fixed scope

Can learned stock/setup/market conditions identify when reversal, continuation or compression is worth trading, and can expected dollars improve on percentage ranking? The [completed interaction study](strategy-interaction-results.md) found no profitable account. Its reversal and compression cohorts varied by state, while one reversal account had a positive mean percentage trade but lost actual dollars. These observations motivate a test, not a hand-picked regime gate.

Keep **next-close entry**: the separately declared timing diagnostic found negative mean next-open entry effects in all nine primary comparisons. Propose **three policies × 1/3/5-session holds × two unchanged cost scenarios = 18 accounts**, each starting with USD 2,000. Scenarios remain proportional 40 bps and the declared Moomoo Canadian-US tariff plus 40 bps. They are sensitivities, not calibrated minimum costs or proof about a commission-free USD route. No fees, holds or thresholds are selected from profitable outcomes.

Reuse source run `814780d48b4141b9a82a3fb917d1b85a` and its original capture. Load frozen history from **January 4, 2010**, and verify the 756 prior fitting/calibration sessions plus feature warmup needed for the **January 4, 2016–September 18, 2026** comparison before declaring the execution request. Preserve the full comparison period; missing early data must not silently shorten it. Preserve missing sources, current-member survivorship, revised vintages and unresolved actions. No future action list screens historical signals; future observations are not needed.

## Three policy comparisons

All arms share the union of eligible reversal5, volume-continuation5 and compression-continuation5 candidates. A stock appears once. The new static three-way control is separately declared; it does not overwrite the old two-way blend.

| Policy | Decision | Purpose |
|---|---|---|
| `static_setup_rank` | Average the three same-date percentile ranks, unavailable components zero; require one available setup. Use the existing rank-driven planner. | Same candidate-pool/account control. |
| `conditional_net_fraction` | Predict gross return and downside; rank only positive estimated utility per dollar of proposed notional. | Test conditional forecasts plus economic abstention together. This does not isolate learning from abstention. |
| `conditional_net_dollars` | Reuse exactly those forecasts and qualification rules; rank estimated utility in dollars at proposed whole-share quantities. | Test ranking units while retaining the same sizing/risk constraints. |

Use stable alphabetical ties and one five-slot account. No fallback forces rejected candidates into empty slots. Keep all earlier rule results visible as references. Empty accounts, failed fits and losing variants are reportable results.

## Learning and chronological evaluation

Reuse existing feature/target, preprocessing, learner-preset and saved-model support. Predict the same six outputs: gross returns and completed-close downside at 1/3/5 sessions after next-close entry. Downside is not an intraday stop or loss guarantee. A unique stock/date row carries setup memberships and ranks so overlapping nominations do not duplicate targets.

Proposed inputs: the existing 27 causal features, three setup indicators, three same-date percentile ranks, benchmark distance from MA200, benchmark RV20, RV20 relative to its preceding 252-observation median, and stock RV5/RV20. Freeze exact ordered definitions before fitting. This lets a model learn interactions; it does not impose the profitable state observed in this study. Sample at most 96 unique rows per date with seed 1729 and recorded identities, before checking future label availability; retain unavailable labels and predict every eligible test candidate.

Use rolling outer blocks: 504 fitting sessions, 252 later calibration sessions, then 252 test sessions. Every six-head label must end strictly before the next boundary, accounting for next-close entry and the longest five-session hold. Annual model refits still make daily decisions. Never reuse the September 18 model as though it existed earlier. Each account runs continuously across model switches; existing positions, orders, exits and settlement retain their history. The completed coverage preflight has 2,693 test sessions in 11 blocks and 754 sessions before the earliest fitting window, exceeding the 273-session feature warmup requirement.

**Nested selection stays inside fitting data.** Compare only existing Ridge and boosted-tree presets using three expanding chronological folds inside the 504 sessions, with purged label boundaries. Fit imputation/scaling separately inside each fold. Select the learner by a **cost-neutral common reference dollar-utility loss**: average across sampled stocks within each date, then equally across dates and horizons, the quantity `[N_ref*((r_hat - 0.5*d_hat) - (r - 0.5*d))]^2`. Here `N_ref` comes from the causal USD 2,000 proportional-40-bps reference quantity, independent of future account cash. The same loss and chosen family serve both fee scenarios; there is no fee-specific model selection. Also retain percentage errors and unconditional setup-mean baselines. No architecture or threshold grid. Freeze the tie/failure fallback before running.

Refit on the purged fitting window, then calibrate using only the later calibration window. Calibration uses a pooled per-row mean-error correction per output, with nonnegative downside before and after correction. Exact selection ties choose Ridge. A family must complete all three inner folds to be eligible; a failed final fit or unavailable calibration causes block-wide abstention, with no alternate-family retry. No test outcome chooses models, correction, fees or entry cutoff. Preserve raw/corrected predictions and assess reliability on the next test block using each output's calibration quintiles, collapsing duplicate edges and retaining missing-target counts. Compare errors with fitting-only setup means; overlapping memberships contribute once to each setup, and the baseline averages a candidate's active setup means. An absent setup mean falls back to the pooled fitting mean for diagnostics only. Save exact samples, windows, preprocessing, parameters, warnings and reload identities.

## Economic decision and unchanged risk

Let q be the allowed whole-share quantity, N its reference notional, mu predicted gross return and d predicted downside. Proposed utility is:

`U = N*mu - projected_entry_cost(q,N) - projected_exit_cost(q,N*(1+mu)) - 0.5*N*d`

Both learned arms require `U > 0`; one ranks `U/N`, the other ranks `U`. The inherited downside weight is 0.5. Costs include the declared quantity/notional-specific tariff. Projected exit-notional fees and a flat round-trip-bps approximation are distinct; no exact equivalence to an existing score is assumed. Projected fees are estimates, with realized-fee error reported. Invalid forecasts remain explicit abstentions.

Keep five positions, 20% entry cap, 0.5% NAV/two-ATR sizing, reserved and settled cash, independent positions and fixed next-close exits. This study does not enforce the owner's 30% account stop; catastrophic drawdowns are not deployable policies. When reserved cash or affordability reduces q, recompute the projected fee burden at that quantity. Use only decision-available prices for ranking. An actual-fill-price utility recheck is a **simulated contingent-fill convention**: it does not mean the closing-auction price was known before an order. Keep it separately identified in reports and qualify its executable order/price-guard interpretation before any deployment; do not silently credit retrospective closing-price knowledge.

## Report and decision

Freeze the 18-attempt request, features, folds, sampling, calibration and cost identities before running; retain every failure and abstention. The learned arms must consume identical frozen forecasts. Report all paired account deltas, net dollars/return, drawdown, percentage versus dollar expectancy, actual notionals, cost burden, turnover/exposure, weekly/monthly/yearly/state stability and concentration. Include forecast error against setup priors and known action-crossing attribution without deleting trades. Reconcile complete flat NAV to initial capital plus all net trade P&L.

Smaller losses, favorable percentage averages or a single strong period do not meet the economic objective. An all-cash path is an acceptable decision, not a profitable trading agent. If dollar ranking does not improve its matched conditional-percent arm, report that refutation. Do not change source treatment, cutoff, fee scenario or hold to manufacture a winner. All dates have already been studied; even positive results would require further qualification rather than automatic paper promotion.

The exact feature schemas, chronological folds, calibration and deterministic failure behavior were frozen in `request.json` before fitting. Definition SHA256: `27bc563d3a65af1328155d917e4ef673fd2f52c892c9d258f33f8d691a7230fc`. These implementation details do not authorize an expanded search. No production cleanup, new spending or broker operation is part of this design.
