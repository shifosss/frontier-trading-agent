# Independent core review: Tasks 1 and 2

Reviewed 2026-09-19 against `docs/superpowers/specs/2026-09-19-daily-model-bridge-design.md` and its implementation plan. Scope: `model-review.diff`, `policy-review.diff`, current corresponding source/tests, model implementation report, exact policy differential evidence, and the candidate caller at the model boundary. No production edits or test reruns performed by this reviewer. Candidate integration and cost evidence require their separate reviews.

## Spec compliance

**Task 1: changes required before integration qualification.** The split fit/predict API, train-only preprocessing, six outputs, calibration audit, empty prediction support, immutable destination rule, and trusted-local artifact integrity checks satisfy the intended core design. The loader checks schema, exact dependency runtime, declared ordered features/heads/models, metadata and payload hashes before deserializing the exact verified bytes. Post-load payload metadata/count/weights checks add useful consistency validation. The checksum limitation is stated correctly; this is not authentication or a loader for uploads. Chronological boundaries and sample provenance are intentionally caller-owned and require Task 3 validation.

Exact repeat/reload prediction reproducibility is not established by the current Task 1 tests: the roundtrip test allows tolerances, and the implementation report records parallel ExtraTrees reduction differences. This conflicts with the actual candidate caller's exact parity requirement; see P1 below.

**Task 2: compliant within reviewed scope.** Forecast scoring and reference-price planning are shared by the historical and forward callers. Whole-share size is the minimum of entry-notional-plus-fee cap, ATR risk cap and available cash. Holdings/reservations are excluded, duplicate rankings cannot open duplicate positions, default capacity deducts both, explicit capacity supports caller-known exits, and correlation sees both existing and newly planned positions. The simulator still computes settlement availability and re-sizes at the next close. The reviewed diff adds no broker submission path and does not touch frozen paper modules or existing study output artifacts.

Evidence inspected rather than rerun: model report records 31 passing focused tests and numerical baseline comparison; root reports 34 passing policy-focused tests; `daily-policy-differential.json` records exact equality of arrays, trades, fees, activities, cash state and metrics over 240 cases / 69,491 trades. This supports unchanged historical behavior for the exercised cases, not an economic qualification claim.

## Code quality findings

### P1: Make model inference deterministic before requiring exact reload parity

Locations: `src/frontier/ensemble_models.py:34`, `src/frontier/ensemble_models.py:176`, `src/frontier/ensemble_models.py:270`; integration trigger `src/frontier/candidate_daily.py:214`.

ExtraTrees retains `n_jobs=2` from fitting and `predict_heads` calls its parallel predictor. Parallel tree accumulation can change the final few floating-point bits between calls. The supplied model implementation report already observes a maximum ExtraTrees delta of 1.39e-17 and corresponding ensemble deltas. `tests/test_model_artifact.py` uses tolerant `assert_allclose`, so its passing roundtrip does not establish the exact property required by `candidate_daily`, which uses `np.array_equal` and raises when any output differs. A valid frozen build can therefore fail after training and saving its model solely because scheduling changed the reduction order.

Use deterministic inference, including calibration predictions, and explicitly test exact repeated predictions and reload predictions. Sequential ExtraTrees prediction after parallel fitting is a narrow option. Calibration must also be deterministic if repeated fits are expected to preserve weights/model identity. Keep audit/config reporting accurate about fitting versus prediction parallelism. Recheck numerical compatibility against the original with a documented floating-point tolerance and retain historical policy differential evidence.

No additional material cash, policy-drift, serialization-integrity, or maintainability defects were identified in the reviewed core diff. The planner contract clearly delegates account reconciliation and settled-by-fill availability to its caller. The model loader's feature-order check establishes consistency with its declared metadata; the feature-producing caller remains responsible for supplying that order.

## Disposition

Core cash-policy extraction is approved. Model artifact integration is pending resolution and focused re-verification of the deterministic inference finding. Full candidate cutoff/provenance/intent review, real frozen-build evidence, and integration suite remain root/Task 3 responsibilities.
