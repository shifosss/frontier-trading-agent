# Multi-model daily stock research: declared experiment

Declared 2026-09-19 following the owner's request for broader and more complex strategies. This expands the earlier three-rule declaration; the earlier v1 and declaration remain retained. Status: implementation in progress, no results inspected. No live or paper policy migration.

## Decisions and reasons

Use the frozen 90af4c840aad48f7ab58fba7a682f96a capture (cutoff September 18, 2026), all declared US/Canadian members and original capture failures. Available price/volume history permits nonlinear and shared multi-output prediction now without waiting for future data. Current membership and adjusted data vintage remain biased; chronological evaluation is retrospective research, not an untouched holdout.

Reuse the validated daily cash engine: close signal, next-session-close entry, independent 1/3/5-session exits, whole shares, five positions, 20% entry cap, 0.5% of equity divided by two ATR for sizing, calendar settlement. Sizing is not a guaranteed stop. Required missing entry/held prices invalidate a path. Preserve historical artifacts and the frozen paper transport/policy.

Compare four independently fitted predictors: standardized Ridge(alpha=100); 48 ExtraTrees with depth 8, leaf size 64, feature fraction 0.8; HistGradientBoosting per target (60 iterations,15 leaves,learning rate0.05,L2=10,min leaf64,no early stopping), then shared-hidden MLP(32,16) with six output units, 60 maximum iterations, no random early-stopping holdout. Six targets are next-close-to-exit adjusted gross returns for 1/3/5 sessions and maximum positive downside magnitudes from intermediate completed closes over those same trades. This is multi-output learning, not transformer attention, intraday drawdown, probabilities or guaranteed loss bounds. Use scikit-learn 1.7.2, seed 1729. Training-only median imputation/missing indicators, standardization, and MLP target scaling.

Features cover multiple return horizons, market-relative returns, trend distances, breakout distance, realized volatility, drawdown, ATR/price, dollar activity, liquidity and cross-sectional strength. No unverified sector histories, news, fundamentals, option chains, shorting or fabricated hourly bars. Features use completed data only. Stock eligibility uses 201 valid observations, USD5m/CAD1m trailing dollar volume, positive ATR/volatility. Optional longer features can be missing and imputed using training only; future labels never determine prediction eligibility.

## Chronological design

First test index 956 (200 warmup + 756 prior sessions); subsequent folds 252 sessions. Prior 756 sessions split first 504 for fitting and last 252 for calibration. Fit outcomes must end strictly before calibration begins; calibration outcomes strictly before test begins. The longest six-session signal-to-exit interval is purged at both boundaries. Models never train on test outcomes, nor refit on calibration after choosing weights. Refit once per annual fold for a controlled comparison with the existing cadence; holdings still change daily. Monthly refitting is a separately declared later comparison.

Uniform deterministic sampling without replacement is capped per session: at most 96 fit and 96 calibration eligible examples per date (maximum 48,384 fit / 24,192 calibration before purging). The sample considers only completed valid labels available at each training boundary; record eligible and excluded-label counts, seeds and sample digests. Predict every eligible stock each test day without future-label filtering. Large test predictions are batched, with fixed 2-thread model computation. Missing required benchmark windows invalidate affected screening decisions; they are not cash signals.

Equal ensemble averages all four models. Calibrated ensemble weights each horizon by positive calibration-MSE improvement over the training-mean prediction; its matching downside head shares those weights. If all improvements are nonpositive, weights fall back explicitly to equal and report that fact. These are pooled predictive diagnostics, not significance tests or proof of net trading edge. Correlated targets and repeated model comparisons are disclosed.

Learned candidates require predicted gross return times (1-half-cost) minus two times half-cost minus0.5 times predicted close-path downside to be positive; rank separately for each cost by that same score. Here half-cost=cost_bps/20,000: the exit fee is charged on predicted exit notional, exactly matching the simulator. Coefficient 0.5 is predeclared, not tuned to profitable outcomes. Negative downside predictions are floored at zero. Compare a separate diversified calibrated ensemble with a 0.85 trailing-60-session positive correlation ceiling versus already-held/planned positions; require at least 40 paired observations to assess a pair. This adds a portfolio constraint and is reported separately from the forecast comparison.

## Every declared comparison

Ten existing rule variants (five families with/without a market-trend filter), three declared relative reversal/continuation rules, four fitted models, equal ensemble, calibrated ensemble and diversified calibrated ensemble: 20 strategies x three horizons x two balances (2,000 / 10,000 native units) x three proportional costs (20/40/100 bps) x two markets = 720 continuous account attempts, plus matched buy/hold and cash references. Accounts carry cash and unsettled receivables across folds, while no position is opened if it would cross the current fold boundary. Old rule controls use the same evaluation interval and fold-close convention. This is not the old rule-selector study rerun.

Detailed trade records are retained for all seven learned variants at 2,000 native capital and40bps (42 accounts across currencies/horizons); the remaining accounts retain aggregate trade metrics and full daily curves. This bounded-audit choice was fixed during pre-run review before economic results. Full comparisons can be reproduced from the frozen data/configuration; model calculations are reproducible to floating tolerance, not promised bitwise identical across parallel math libraries.

Keep all model convergence warnings, exclusions, failed accounts, fold definitions, sample identities and model configuration. Model failure fails the study rather than silently dropping a losing model. Report trade/weekly/monthly/yearly behavior, costs, exposure, drawdown, expectancy and profit concentration. Costs are controlled proportional sensitivity assumptions; fixed broker tariffs, FX, subscription fees, taxes and interest are not included. Broker-specific execution calibration remains unfinished and prevents live qualification.

## Validation and delivery

Test feature/label timing, future-price mutation invariance, missing label independence, train-only preprocessing, deterministic calibration weights, six-head shapes, fold purging, settled-cash accounting, correlation decisions and unchanged v1 outputs. Run a saved-data smoke before the full frozen capture, perform independent code and accounting review, then publish all results in the existing Strategy lab. No automatic winner promotion. A failed simple baseline does not block testing a richer model; complexity earns inclusion through measured comparisons.

Primary implementation references: https://scikit-learn.org/1.7/modules/generated/sklearn.neural_network.MLPRegressor.html ; https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.ExtraTreesRegressor.html ; https://scikit-learn.org/1.7/modules/generated/sklearn.linear_model.Ridge.html


## Dated outcome record

September 19, 2026: the implementation and saved-data qualification completed, followed by full run `814780d48b4141b9a82a3fb917d1b85a` on the predeclared frozen capture. The declaration above is retained as written before economic results. See [all findings](../../multi-model-research-results.md): 569 complete and 151 incomplete accounts, independent accounting verification, model warnings and a subsequently identified issuer/action continuity concern. No historical winner was promoted to the paper policy. Subsequent source or model corrections require their own declared comparisons.
