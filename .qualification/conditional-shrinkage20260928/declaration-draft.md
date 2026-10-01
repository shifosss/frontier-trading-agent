# Conditional return shrinkage: bounded comparison

This draft specifies one calibration change for root review and freezing before execution. It contains no new account results. The completed source study remains immutable.

The preceding saved forecast diagnostic found that return MSE was 1.07%, 2.95% and 8.98% worse than fitting-only setup means at 1, 3 and 5 sessions, while the corresponding downside MSE improved. Forecasts in the highest calibration-defined return interval averaged 0.73%, 1.94% and 2.94%, against later observed gross returns of 0.09%, 0.25% and 0.40%. These overlapping candidate observations motivate testing calibration magnitude; they do not establish an investable edge. All periods were previously researched, so this is an explicitly exploratory follow-up.

## One change, six account paths

For each of the 11 existing model blocks and each return horizon, fit an affine attenuation using only its saved, purged calibration raw forecasts and targets:

```
s = clip(mean((x - mean(x)) * (y - mean(y))) / mean((x - mean(x))**2), 0, 1)
b = mean(y) - s * mean(x)
new_return = b + s * raw_return
```

For an exactly constant raw calibration head, use `s=0` and `b=mean(y)`. Exact equality of all values identifies this case, including nonbinary floating values such as 0.1; no epsilon or fitted variance cutoff is introduced. Nonconstant moment underflow, overflow or nonfinite coefficients fail explicitly. Moments use equally weighted calibration rows, not reference-notional or test weights. The zero-to-one constraint tests attenuation only: it cannot reverse or amplify a return signal. A positive slope preserves within-horizon raw-return ordering. The original mean-bias correction is the slope-one treatment, subject to ordinary floating summation differences.

Only the three return heads change. Each candidate's existing corrected downside forecasts are copied byte-for-byte from the original float64 array. Raw predictions, model families, training features, model fits, candidate rows and columns, source prices, date boundaries and requested universe remain identical. The same three coefficients per block apply to both cost profiles. Neither calibration nor transformation reads test labels.

Run only `conditional_net_dollars` at holding periods 1, 3 and 5 sessions under the existing proportional 40-bps and Moomoo Canada US explicit-fee plus 40-bps profiles: **six additional paths**. Their controls are the corresponding six already completed original net-dollar accounts, selected by this economic allocation question rather than by which arm won. Reuse USD2,000 starting cash, original whole-share sizing, position and risk caps, settled cash, every-session screening, next-close timing and the existing simulated contingent-fill utility guard. Each account continues across all model boundaries with positions and scheduled exits intact. Do not add a threshold sweep, change a fee assumption, refit a model, remove an instrument or repair a source price in this comparison. All-cash and failed outcomes remain reportable.

## Source and invalid-data rule

Use only complete original `blocks/block-*.json` manifests from `conditional-selection20260928`, verifying each recorded file hash. Read `model/calibration-predictions.npz` (`raw`, `targets`, `rows`, `columns`) and its paired `sample-arrays.npz`. Require exact saved row/column/target pairing and calibration label-end boundaries strictly before that block's test start. The completed source has 23,616 purged calibration rows per block, 259,776 in total, and 3,133,575 test candidate rows. These are retained observations, not unique independent samples.

The calibration API requires matching, nonempty `(N,6)` arrays whose values are entirely finite; any violation fails the block rather than silently dropping or replacing rows. Saved test predictions may contain NaN, which remains unavailable after the rowwise return transformation. Infinite saved predictions fail explicitly. The current verified source test forecasts are finite. No test-label availability gate, candidate resampling or post-outcome source exclusion is permitted. Root's runner retains every original candidate row and the original source limitations, including current-member survivorship, mixed instrument types and unresolved corporate-action/price-unit concerns.

## Minimal artifacts and interfaces

`fit_return_shrinkage(raw_calibration, targets, *, source_identity=None)` returns a JSON-safe parameter dictionary; `apply_return_shrinkage(parameters, raw_test, original_corrected)` returns a float64 six-column array. Ordered heads are `return_1`, `return_3`, `return_5`, `downside_1`, `downside_3`, `downside_5`.

Each per-block saved parameter object has:

- `schema: conditional-return-shrinkage-v1`, `head_names`, `calibration_rows`.
- `calibration_arrays.raw` and `.targets`, each recording shape, dtype and SHA-256 of contiguous C-order float64 bytes.
- `source_identity`, supplied by the runner with block number, original calibration/sample file hashes and temporal bounds.
- `returns`, three ordered records containing `head`, `index`, `count`, `mean_raw`, `mean_target`, `variance_raw`, `covariance_raw_target`, `unconstrained_slope`, `slope`, `intercept`, `zero_variance`.

Root's runner additionally freezes request/code/source identities, saves all transformed test forecasts and coefficient artifacts, preserves failures and verifies immutable artifacts on resume. Model artifacts and original controls are reused rather than overwritten. Test-target diagnostics run only after coefficients and predictions are fixed.

## Assessment and refutation

Compare all six paired continuous accounts for ending equity, net expectancy per trade, total fees, trade count, invested exposure, maximum drawdown and annual stability, alongside calibration coefficients, admissions and all-cash outcomes. Recheck return error and calibration tails as supporting diagnostics with explicit matched and unavailable denominators; do not substitute lower prediction error for economic improvement. Independently verify coefficients, transformed returns, unchanged downside/candidate membership and account arithmetic.

If attenuation improves prediction error but does not improve net expectancy, drawdown and dated stability, it does not repair allocation economically. If it merely stops trading and preserves cash, report abstention rather than an alpha discovery. Even improvement over losing controls does not establish profitability, qualification or justify paper promotion. This bounded comparison tests whether inflated return magnitudes were causing poor admissions; it cannot manufacture a new return-ranking signal or resolve source completeness.
