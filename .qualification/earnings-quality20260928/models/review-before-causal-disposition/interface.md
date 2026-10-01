# Fixed two-output earnings model adapter

This is a local, synthetic-tested connection to the predeclared earnings comparison.
No original-cohort model fits or economic account results have been produced by this work.
The frozen specification is `cohort/model-specification.json`, SHA-256
`7e837043e034305fe3aa15aefd3d28d8389f63e923fc7ef0739d1883e8a30ffb`.

## API

Import `earnings_models.py` from this directory.

- `fit_family_fold(family, rows, labels, fold, calendar_sessions)` returns one
  `FittedEarnings` bundle, including explicit insufficient-sample or failed attempts.
  `fit_fold(...)` returns both fixed families keyed by name. Neither accepts money,
  fees, outcome-selected parameters or family-selection inputs.
- `predict_events(bundle, rows)` accepts **no labels** and returns a dictionary with
  `family`, `test_decision_year`, `model_attempt_id`, `forecasts` and `warnings`.
  Every input must exactly match a saved historical prepared row; duplicate, altered
  and unknown rows are refused. Each forecast preserves `event_id`, `cik`,
  `prepared_row_sha256`, `raw`, `uncalibrated`, `corrected`,
  `status` and `reasons`. Usable status is **predicted**; other rows are
  **unavailable**, including calibrated return <= -1. All provided rows are retained.
  Raw nonfinite values are literal strings `nan`, `inf` or `-inf`, never replaced
  with finite estimates. Shape failures retain every requested event and the error.
- `save_bundle(bundle, new_directory)` refuses an existing directory. It writes the
  fitted sklearn model (also retaining a model whose calibration failed), full supplied
  source rows, preprocessing/sample/calibration audit, runtime and byte identities.
  Completed models are checked for exactly equal raw calibration forecasts after reload.
  `load_bundle(directory)` validates saved hashes, current adapter/shared implementation identities and the
  frozen specification before trusted-local joblib loading.
  Do not deserialize artifacts obtained from untrusted external sources.

Rows are JSON-serializable dictionaries with unique nonempty `event_id`, exact ten-digit
`cik`, offset-aware `decision_timestamp` at 09:00 America/New_York,
`planned_label_end_session`, `model_input_status` and ordered five-element
`model_inputs`. `accession`, source fields and unavailability reasons are preserved.
The five inputs are S, Q, prior five-session stock return less SPY return,
prior dollar activity divided by the prior-20-session median, and prior SPY distance
from its 200-session mean. The adapter does not calculate or substitute source features.

Labels are a separate mapping from event ID to
`{"status": "qualified", "targets": [return_5, downside_5]}`,
or an unavailable record with reasons. Labels are read only for causal, non-purged
fitting/calibration rows. Test labels and purged-row labels are never accessed.
The two targets retain their original fractional units; no target scaling or clipping.

`fold` must equal one of the five frozen 2021-2025 test-fold dictionaries.
`calendar_sessions` is the complete ordered unique list of ISO exchange-session dates,
whose identity is retained. Purge fitting labels reaching the first calibration-year
session and calibration labels reaching the first test-year session. Fitting requires
256 rows/25 CIKs and calibration 64 rows/16 CIKs **after** causal qualification,
purging and joint-label validation. All dispositions, unavailable rows, original
source-row digests and actual retained IDs remain in the audit. The caller must supply
the frozen exchange calendar and preserve its original file identity in the study definition.

## Reused fitting and calibration

Both families call the existing `frontier.conditional_models._fit_family` with n-by-2
targets and its fixed seed 1729, training-only preprocessing, thread limit and presets.
Predictions call the fitted estimator directly; no six-head target or prediction wrapper
is used. Each actual family/year bundle must be fitted once and shared across the four
capital/fee accounts. This historical interface binds forecasts to the saved prepared
source rows; forecasting newly arriving rows requires a separately bound operator
interface. Insufficient folds never reuse another year or family.

The raw downside head is clipped at zero **before** fitting pooled calibration mean
residuals. Corrected downside is clipped at zero again; corrected return is unbounded.
Fitting-only mean targets are saved for later baseline-error comparison. Calibration
predictions and residual bias are saved separately from future forecast records.
Quantile cutpoints are computed separately for raw and corrected forecasts, for each
head, from calibration rows only. The 20/40/60/80-percent cuts collapse duplicates and
discard cuts equal to the minimum/maximum; constant predictions form one bin.
Bins use `searchsorted(interior_edges, value, side="right")` and include forecasts
outside the calibration range. No test outcome changes edges or bias.

For the account adapter, collect one family's five test-year forecast lists into a
unique `event_id -> full forecast record` mapping and bind its full artifact digest
as `forecast_identity`. The account adapter must match each event ID, CIK and
`prepared_row_sha256` to its prepared source row. Row hashes use sorted-key compact
JSON with `allow_nan=False` and default ASCII escaping. Only downstream cash sizing/utility uses capital or costs.
Run any later label-based error/bin summaries separately, after forecasts are preserved.

## Validation

`test_earnings_models.py` uses generated synthetic rows only. It checks both actual
sklearn families, two-head shape, exact presets, fitting-only preprocessing/baselines,
calibration arithmetic, negative raw downside, quantile collapse, future-label access
isolation, actual-calendar boundary purging, all four fixed sample gates, retained
unavailable rows, warnings/failures, invalid forecasts, saved source identity,
exact model reload, artifact corruption, code-drift refusal, altered/unbound forecast
input refusal and overwrite refusal.
The adjacent verification JSON records the exact source hashes and captured test log.
These checks establish adapter behavior; they do not validate profitability.
